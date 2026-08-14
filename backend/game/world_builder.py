"""建世界流水线：抽样文本 → 玩家 DeepSeek Key → 世界框架 JSON。

站点零成本：全程用玩家自己的 Key 调用；不落盘小说原文，只存生成的世界规格。
产出必须走 validate_world_spec 校验（含一次自动重试），失败给友好中文提示。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from openai import OpenAI

from . import worlds

MODEL = "deepseek-chat"
BUILD_MAX_TOKENS = 3000

BUILD_PROMPT = """你是「世界观建构师」。用户提供一本小说的抽样片段（开头、中段、结尾），你要为它建立一套可游玩的文字 RPG 世界框架。

硬性要求：
1. 必须输出严格 JSON（除 JSON 外不要任何文字），结构如下：
{
  "name": "世界名（小说名或核心设定名，不超过 12 字）",
  "desc": "一句话简介（不超过 30 字，用于广场卡片）",
  "rulebook": "完整规则书（供 AI 在游玩时扮演主神/引导者，300~700 字）",
  "state_template": {
    "character": {"name": "无名", "gender": "?", "age": 0, ...你设计的基础角色字段（标量默认值）},
    "level_field": "你指定的等级字段名（如 境界/修为/等级，须与 stats 中的键对应）",
    "resources": {"资源名1": {"init": 10, "min": 0}, "资源名2": {"init": 0, "min": 0}},
    "stats": {"等级字段名": {"init": 1, "min": 1, "max": 100, "max_step": 2}, "其他属性": {"init": 0, "min": 0, "max": 100, "max_step": 5}},
    "affection_chars": ["重要角色名..."],
    "affection_min": -100, "affection_max": 100,
    "factions": ["势力名..."],
    "inventory": [],
    "start_location": "开局地点"
  },
  "creation_schema": {
    "steps": [{"step": "身份", "fields": [{"key": "name", "label": "姓名", "type": "text", "required": true}, {"key": "gender", "label": "性别", "type": "select", "options": ["男", "女", "神秘"], "required": true}, {"key": "age", "label": "年龄", "type": "number", "required": false}, {"key": "identity", "label": "你的身份", "type": "select", "options": ["穿越者", "正典角色", "原创角色"], "required": true}]}, {"step": "背景", "fields": [{"key": "custom_setting", "label": "自定义附加设定", "type": "textarea", "required": false}, ...]}]
  }
}

2. 规则书 (rulebook) 必须复刻以下结构，用中文书写：
   - 世界观设定：一句话点明世界核心法则与基调
   - 世界地图/区域：列出 3~5 个主要地点及其特色
   - 核心机制：修炼/战斗/势力/好感等如何运作；明确"每轮先写足 150~250 字连贯的叙事正文（场景/人物/行动/对白）——正文必须是故事本身，严禁只写'叙述'、'……'等占位词或纯选项清单；正文之后再给出 3-4 个行动选项，并标注一个系统推荐选项（recommended: true，即最符合该世界剧情大纲走向与玩家当前行为路径的选项）。叙述与结算分离：选项最终以结算 JSON 的 options 字段落账，正文里的选项只作提示。"
   - 创建选项解读：说明每个创建字段如何影响开局
   - 输出契约：明确 AI 每回合输出的固定键（严格遵守）
     state_delta 必须是这些键：
     {"resources": {"资源名": 增量}, "stats": {"属性名": 增量}, "affection": {"角色名": 增量},
      "location": "新地点", "date": "日期文本", "month_delta": 0~24,
      "inventory_add": [], "inventory_remove": [], "notes_add": []}
     resources/stats/affection 一律是"增量"（正负均可），不是绝对值；等级类属性用 stats 增量表达。
     禁止使用 gold/silver/copper/soul_level/soul_ring_add 这些旧键。

3. 严禁逐字复制小说原文或大段改写原文剧情——只提炼世界观框架、设定与规则。引用具体设定时用概括性语言。

4. creation_schema 的字段类型只能是 text / number / select / multiselect / textarea。至少 2 个步骤，字段总数 4~8 个。字段 key 用英文小写下划线，label 用中文。
   【绝对约束·基础字段必填】creation_schema 的「第一个步骤」必须以这三个字段开头（缺一不可，否则玩家创角会显示"无名"、"?"）：
     - {"key": "name", "label": "姓名", "type": "text", "required": true}
     - {"key": "gender", "label": "性别", "type": "select", "options": ["男", "女", "神秘"], "required": true}
     - {"key": "age", "label": "年龄", "type": "number", "required": false}
   并且必须在任意一个步骤中包含这个字段（供玩家填写自定义附加设定）：
     - {"key": "custom_setting", "label": "自定义附加设定", "type": "textarea", "required": false}

5. state_template.character 里每个字段给一个合理的标量默认值（数字给 0，文本给空串，列表给空数组）。【绝对约束】state_template.character 必须同步包含 name、gender、age、custom_setting 这四个键，默认值分别为 "无名"、"?"、0、""。"""


def _friendly_build_error(e: Exception) -> str:
    status = getattr(e, "status_code", None)
    code = getattr(e, "code", None)
    if status == 401 or code == "invalid_api_key":
        return "你的 DeepSeek API Key 无效或已过期。请在 platform.deepseek.com → API Keys 重新申请。"
    if status == 429 or code in ("insufficient_quota", "rate_limit_exceeded"):
        return "你的 DeepSeek 额度不足或触发限流。请检查余额（platform.deepseek.com → 用量信息）后稍后再试。"
    return f"建世界失败：{e}"


# ── 物理兜底：创角向导必须始终包含的通用基础字段，防 AI 幻觉漏字段（漏了会显示"无名"/"?"）──
_BASE_FIELDS = [
    {"key": "name", "label": "姓名", "type": "text", "required": True},
    {"key": "gender", "label": "性别", "type": "select", "options": ["男", "女", "神秘"], "required": True},
    {"key": "age", "label": "年龄", "type": "number", "required": False},
]
_CUSTOM_SETTING_FIELD = {"key": "custom_setting", "label": "自定义附加设定", "type": "textarea", "required": False}
_CHARACTER_DEFAULTS = {"name": "无名", "gender": "?", "age": 0, "custom_setting": ""}


def _ensure_base_fields(cs: dict, character: dict) -> None:
    """硬编码合并逻辑：补齐 name/gender/age/custom_setting，防止 AI 漏生成。"""
    existing = {f.get("key") for step in cs["steps"] for f in step.get("fields", [])}

    # 1) 基础三字段缺失则 insert 到第一页最前（reversed 保证最终顺序 name→gender→age）
    first_fields = cs["steps"][0].setdefault("fields", [])
    for base in reversed(_BASE_FIELDS):
        if base["key"] not in existing:
            first_fields.insert(0, dict(base))
            existing.add(base["key"])

    # 2) custom_setting 缺失则 append 到最后一页
    if "custom_setting" not in existing:
        cs["steps"][-1].setdefault("fields", []).append(dict(_CUSTOM_SETTING_FIELD))

    # 3) character 同步补齐四键默认值
    for k, v in _CHARACTER_DEFAULTS.items():
        character.setdefault(k, v)


def validate_world_spec(data: dict, client_id: str) -> dict:
    """校验并规整 DeepSeek 产物为可落盘的世界规格。非法抛 ValueError。"""
    if not isinstance(data, dict):
        raise ValueError("AI 未返回 JSON 对象")
    name = str(data.get("name", "")).strip()
    desc = str(data.get("desc", "")).strip()
    rulebook = str(data.get("rulebook", "")).strip()
    if not name or len(name) > 16:
        raise ValueError("世界名缺失或过长")
    if len(rulebook) < 200:
        raise ValueError("规则书内容不完整，请重试")
    st = data.get("state_template")
    if not isinstance(st, dict) or not isinstance(st.get("character"), dict):
        raise ValueError("状态模板缺失或格式错误")
    if not isinstance(st.get("stats"), dict) or not isinstance(st.get("resources"), dict):
        raise ValueError("状态模板缺少 resources/stats")
    cs = data.get("creation_schema")
    if not isinstance(cs, dict) or not isinstance(cs.get("steps"), list) or not cs["steps"]:
        raise ValueError("创建字段模板缺失")

    # 规整：字段 key 去空白；坏字段类型默认 text
    allowed = {"text", "number", "select", "multiselect", "textarea"}
    for step in cs["steps"]:
        for f in step.get("fields", []):
            f["key"] = str(f.get("key", "")).strip()
            f["label"] = str(f.get("label", f["key"])).strip() or f["key"]
            f["type"] = f.get("type") if f.get("type") in allowed else "text"
            f["required"] = bool(f.get("required"))
            if f["type"] == "select" and not isinstance(f.get("options"), list):
                f["options"] = []
            if f["type"] in ("select", "multiselect") and not f.get("options"):
                raise ValueError("下拉/多选字段缺少选项")

    # 物理兜底：补齐 name/gender/age/custom_setting（提示词之外的代码级保险）
    _ensure_base_fields(cs, st["character"])

    level_field = str(st.get("level_field", "")).strip()
    if level_field and level_field not in st.get("stats", {}):
        # 等级字段必须对应 stats 里的一个键；没有则忽略
        st.pop("level_field", None)

    return {
        "id": worlds.new_world_id(),
        "name": name,
        "desc": desc,
        "kind": "custom",
        "owner": client_id,
        "rulebook": rulebook,
        "summary": "generic",
        "state_template": {
            "character": {k: st["character"].get(k) for k in st["character"]},
            "level_field": st.get("level_field", ""),
            "resources": {k: {"init": int(v.get("init", 0)), "min": int(v.get("min", 0))}
                          for k, v in st["resources"].items()},
            "stats": {k: {
                "init": int(v.get("init", 0)),
                "min": int(v.get("min", 0)),
                "max": int(v.get("max", 10**9)),
                "max_step": int(v.get("max_step", 10**9)),
            } for k, v in st["stats"].items()},
            "affection_chars": [str(x) for x in st.get("affection_chars", [])],
            "affection_min": int(st.get("affection_min", -100)),
            "affection_max": int(st.get("affection_max", 100)),
            "factions": [str(x) for x in st.get("factions", [])],
            "inventory": [],
            "start_location": str(st.get("start_location", "起始之地")),
        },
        "creation_schema": cs,
        "created_at": datetime.now().isoformat(),
    }


def build_world(sample: str, api_key: str, client_id: str) -> dict:
    """用玩家 Key 调用 DeepSeek 建世界框架；失败自动重试一次。"""
    client = OpenAI(api_key=api_key.strip(), base_url="https://api.deepseek.com")
    messages = [
        {"role": "system", "content": BUILD_PROMPT},
        {"role": "user", "content": f"小说的抽样片段如下（节选）：\n\n{sample[:35000]}"},
    ]
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL, messages=messages, temperature=0.6,
                max_tokens=BUILD_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            data = json.loads(_strip_code_fence(text))
            return validate_world_spec(data, client_id)
        except Exception as e:  # 校验失败或 JSON 畸形都走重试
            last_err = e
    raise last_err if last_err is not None else ValueError("建世界失败")


def _strip_code_fence(text: str) -> str:
    """去掉 AI 偶尔包裹的 ```json ``` 围栏。"""
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    return m.group(1) if m else text
