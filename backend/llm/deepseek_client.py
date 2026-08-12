"""DeepSeek LLM 通信与错误处理。"""
from __future__ import annotations

import json
import os

from openai import OpenAI

_key = os.getenv("DEEPSEEK_API_KEY")
# 服务端 key 可选：未配置时纯 BYOK（每位玩家填自己的 key）。
_client = OpenAI(api_key=_key, base_url="https://api.deepseek.com") if _key else None
MODEL = "deepseek-chat"
# 输出 token 上限：限长既控成本又控延迟——叙述/结算无限长是"生成慢"的主因之一。
NARRATIVE_MAX_TOKENS = 1200
# 结算 JSON 的 max_tokens。实测真实回合（丰富 state_template）结算输出 650~900 字 ≈ 500~680 token，
# 600 上限贴得太紧——模型稍啰嗦就截断成非法 JSON，_call_settle 双次失败后静默落到单选项兜底
# （玩家表现为"只剩一个选项"）。提高到 1200 给足余量，彻底消除截断这条失败路径。
SETTLE_MAX_TOKENS = 1200

# 叙述正文下限：低于此长度视为生成退化（如模型只吐出"叙述。"占位词），触发带纠偏的一次重试。
# 真实正文几乎不会低于该值（各档位字数要求最低 120 字起），故误触发概率极低、成本可忽略。
NARRATIVE_MIN_CHARS = 30


def _client_for(api_key: str | None):
    """BYOK：玩家自带 key 时用玩家 key 调 DeepSeek，否则回落服务端 key。"""
    if api_key and api_key.strip():
        return OpenAI(api_key=api_key.strip(), base_url="https://api.deepseek.com")
    if _client is not None:
        return _client
    raise RuntimeError("NO_SERVER_KEY")


def _friendly_err(e: Exception) -> str:
    """把 DeepSeek 错误映射成对玩家友好的中文提示。"""
    if isinstance(e, RuntimeError) and "NO_SERVER_KEY" in str(e):
        return "站点未配置默认额度。请回到创建角色第一步，填写你自己的 DeepSeek API Key。"
    status = getattr(e, "status_code", None)
    code = getattr(e, "code", None)
    if status == 401 or code == "invalid_api_key":
        return "DeepSeek API Key 无效或已过期。请回到创建页，填写你自己申请的有效 Key（platform.deepseek.com → API Keys）。"
    if status == 429 or code in ("insufficient_quota", "rate_limit_exceeded"):
        return "DeepSeek 额度不足或触发限流。若用的是别人的 Key，请换一个；或稍等片刻再试。"
    return f"DeepSeek 调用失败：{e}"


def _stream_narrative(messages: list[dict], api_key: str | None = None, flush: int = 48,
                      max_tokens: int = NARRATIVE_MAX_TOKENS):
    """真流式叙述：边从 DeepSeek 收 token 边 yield 文本块，结束后 yield 余量。

    create() 在本生成器的首次迭代时执行——鉴权/额度错误在这里抛出，由调用方
    （_run_turn.gen）捕获并下发 event: error 事件。max_tokens 随自由度档位变化：
    档位越高，生成越长的叙述。
    """
    client = _client_for(api_key)
    stream = client.chat.completions.create(
        model=MODEL, messages=messages, temperature=0.85,
        max_tokens=max_tokens, stream=True,
    )
    buf = ""
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            buf += chunk.choices[0].delta.content
            if len(buf) >= flush:
                yield buf
                buf = ""
    if buf:
        yield buf


def _call_settle(messages: list[dict], api_key: str | None = None) -> dict:
    """结算 JSON 调用：解析失败或缺少可用 options 时带纠偏指令重试一次，最终兜底 {}。

    修复：旧实现只在"抛异常"时重试——截断成非法 JSON（SETTLE_MAX_TOKENS 不够）或
    返回合法 JSON 但缺 options（规则书契约未要求选项）都会静默落到单选项兜底，
    玩家表现为"只剩一个选项"。现在两类失败都会在重试时明确要求 options 字段。
    """
    client = _client_for(api_key)
    settle = {}
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL, messages=messages, temperature=0.3,
                max_tokens=SETTLE_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            parsed = json.loads(text)
            opts = parsed.get("options")
            if isinstance(opts, list) and len(opts) > 0:
                return parsed
            settle = parsed  # 合法 JSON 但缺可用 options → 重试时纠偏
        except Exception:
            settle = {}      # 解析失败（如截断）→ 重试时纠偏
        if attempt == 0:
            nudge = ("\n\n（注意：你的结算 JSON 必须包含 options 数组，列出 3-4 个不同的行动选项，"
                     "每个选项含 label（A/B/C/D）、text、recommended 三字段。上一轮你没有给出可用的 "
                     "options 或输出被截断——请忽略上一轮，重新输出完整的结算 JSON，options 字段不可缺少。）")
            messages = list(messages)
            if messages and messages[-1].get("role") == "user":
                messages[-1] = {**messages[-1],
                                "content": messages[-1].get("content", "") + nudge}
    return settle


def _call_turn(messages: list[dict], api_key: str | None = None,
               max_tokens: int = 2800) -> dict:
    """单次非流式结构化调用：返回 {narrative, options, state_delta, notes, event}。

    旧架构：_stream_narrative（自由文本→strip→重试→兜底）+ _call_settle（JSON）两次调用。
    新架构：一次 response_format=json_object 调用同时产出 narrative + options + state_delta，
    JSON 结构本身保证 narrative 和 options 物理隔离——绝不可能混在一起。

    失败时有界重试（1次纠偏），彻底失败返回 {}，调用方走 fallback。
    """
    client = _client_for(api_key)
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            data = json.loads(text)
            narrative = data.get("narrative", "")
            opts = data.get("options")
            if (isinstance(narrative, str) and len(narrative) >= NARRATIVE_MIN_CHARS
                    and isinstance(opts, list) and len(opts) > 0):
                return data
        except Exception:
            pass
        # 纠偏重试
        if attempt == 0:
            messages = list(messages)
            if messages and messages[-1].get("role") == "user":
                nudge = (
                    "\n\n（你上一次输出的 JSON 不满足要求——narrative 字段缺少有效叙述，"
                    "或 options 数组为空/缺失。请重新输出完整 JSON，确保 narrative 是"
                    "充实的叙述正文，options 包含 3-4 个不同选项。这是最后一次机会。）"
                )
                messages[-1] = {**messages[-1],
                                "content": messages[-1].get("content", "") + nudge}
    return {}
