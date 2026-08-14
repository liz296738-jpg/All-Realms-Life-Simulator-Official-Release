"""结算防护测试：options 缺失 / JSON 截断 → 自愈重试；token 预算充足；提示词契约优先。

背景：自建世界"只剩一个选项"——真实回合结算输出（丰富 state_template 的 options+
state_delta+notes+event）接近 600 token 上限，模型稍啰嗦就截断成非法 JSON；
或规则书契约未要求 options → 合法 JSON 却缺 options。旧 _call_settle 只在"抛异常"时
重试，这两类都静默落到单选项兜底。修复：SETTLE_MAX_TOKENS 600→1200 + 两类失败
都带纠偏重试一次。
"""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from llm import deepseek_client
from game import worlds
from game.prompt_builder import build_settle_messages
from game.state_schema import default_state


def _fake_client(contents):
    """返回 (client, calls)；create 依序消费 contents，超出用最后一条。"""
    calls = {"n": 0}

    def _create(**kwargs):
        calls["n"] += 1
        idx = min(calls["n"] - 1, len(contents) - 1)
        msg = Mock()
        msg.content = contents[idx]
        ch = Mock()
        ch.message = msg
        resp = Mock()
        resp.choices = [ch]
        return resp

    client = Mock()
    client.chat.completions.create.side_effect = _create
    return client, calls


def _patch_client(monkeypatch, contents):
    client, calls = _fake_client(contents)
    monkeypatch.setattr(deepseek_client, "_client_for", lambda api_key: client)
    return calls


_OPTIONS_JSON = json.dumps({
    "options": [
        {"label": "A", "text": "去藏经阁查线索", "recommended": True},
        {"label": "B", "text": "向玄机真人请教", "recommended": False},
    ],
    "state_delta": {"resources": {"灵石": -10}},
    "event": "你进入藏经阁。",
}, ensure_ascii=False)

_TRUNCATED_JSON = '{"options": [{"label": "A", "text": "去藏经阁查线索", "reco'   # 非法 JSON（截断）
_NO_OPTIONS_JSON = json.dumps({"state_delta": {}, "event": "无选项的合法结算"}, ensure_ascii=False)


def _settle_msgs():
    world = worlds.get_world("douluo")
    state = default_state({"character": {"name": "测试"}}, world)
    return build_settle_messages(state, [], "一段测试叙述。", world)


# ── _call_settle 自愈重试 ─────────────────────────────────────
def test_settle_returns_immediately_when_valid(monkeypatch):
    """一次成功：合法 JSON 且带 options → 不重试。"""
    calls = _patch_client(monkeypatch, [_OPTIONS_JSON, "unused"])
    result = deepseek_client._call_settle(_settle_msgs(), api_key="sk-test")
    assert calls["n"] == 1
    assert len(result["options"]) == 2


def test_settle_retries_when_options_missing(monkeypatch):
    """合法 JSON 缺 options → 带纠偏重试一次，第二次带 options 则采用。"""
    calls = _patch_client(monkeypatch, [_NO_OPTIONS_JSON, _OPTIONS_JSON])
    result = deepseek_client._call_settle(_settle_msgs(), api_key="sk-test")
    assert calls["n"] == 2                       # 触发重试
    assert len(result["options"]) == 2           # 用第二次的结果


def test_settle_retries_when_json_truncated(monkeypatch):
    """截断成非法 JSON → 带纠偏重试一次，第二次正常则恢复。"""
    calls = _patch_client(monkeypatch, [_TRUNCATED_JSON, _OPTIONS_JSON])
    result = deepseek_client._call_settle(_settle_msgs(), api_key="sk-test")
    assert calls["n"] == 2
    assert len(result["options"]) == 2


def test_settle_falls_back_empty_on_double_failure(monkeypatch):
    """两次都失败 → 兜底 {}（由 _normalize_options 兜底单选项，不崩）。"""
    calls = _patch_client(monkeypatch, [_TRUNCATED_JSON, _TRUNCATED_JSON])
    result = deepseek_client._call_settle(_settle_msgs(), api_key="sk-test")
    assert calls["n"] == 2
    assert result == {}


def test_settle_retry_appends_correction_nudge(monkeypatch):
    """重试时确实把纠偏指令追加到了用户消息末尾（验证自愈生效而非空转）。"""
    seen_msgs = {}

    def _create(**kwargs):
        seen_msgs["last_user"] = kwargs["messages"][-1]["content"]
        msg = Mock()
        msg.content = _TRUNCATED_JSON
        ch = Mock()
        ch.message = msg
        resp = Mock()
        resp.choices = [ch]
        return resp

    client = Mock()
    client.chat.completions.create.side_effect = _create
    monkeypatch.setattr(deepseek_client, "_client_for", lambda api_key: client)
    deepseek_client._call_settle(_settle_msgs(), api_key="sk-test")

    assert "options 字段不可缺少" in seen_msgs["last_user"]
    assert seen_msgs["last_user"].count("options 字段不可缺少") == 1  # 只纠偏一次


# ── token 预算与提示词契约 ─────────────────────────────────────
def test_settle_max_tokens_gives_headroom():
    """回归护栏：结算 token 预算必须留足余量，防止截断再触发。"""
    assert deepseek_client.SETTLE_MAX_TOKENS >= 1000


def test_build_settle_messages_options_mandatory_overrides_rulebook():
    """结算提示词显式声明 options 必不可少、优先于规则书契约。"""
    world = worlds.get_world("douluo")
    state = default_state({"character": {"name": "测试"}}, world)
    msgs = build_settle_messages(state, [], "一段测试叙述。", world)
    user = msgs[-1]["content"]
    assert "必不可少" in user and "优先于任何规则书" in user
    assert "options 必须给出 3-4 个" in user


def test_build_settle_messages_state_delta_nested_example():
    """结算提示词含按世界字段生成的嵌套 state_delta 示例，防扁平键漂移。"""
    world = {
        "id": "w", "name": "测试界", "summary": "generic", "rulebook": "测试规则书。",
        "state_template": {
            "character": {"name": "主角"},
            "level_field": "修为",
            "resources": {"灵石": {"init": 100, "min": 0}},
            "stats": {"修为": {"init": 1, "min": 1, "max": 100, "max_step": 2}},
            "affection_chars": ["大师姐"],
        },
    }
    state = default_state({"character": {"name": "主角"}}, world)
    msgs = build_settle_messages(state, [], "一段测试叙述。", world)
    user = msgs[-1]["content"]
    assert "严禁平铺到顶层" in user
    assert '"resources": {"灵石": -10}' in user
    assert '"stats": {"修为": 1}' in user
    assert '"affection": {"大师姐": 5}' in user
