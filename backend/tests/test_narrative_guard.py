"""叙述生成测试：单次结构化 JSON 调用（_call_turn）替代旧架构（_stream_narrative + _call_settle）。

旧架构根因：自由文本→strip_options_block→重试→兜底——依赖正则剥离选项，不可靠。
新架构：一次 response_format=json_object 调用，narrative 和 options 在 JSON 层物理隔离。

所有 LLM 调用均替换为固定返回值，不触网、不耗额度。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import main
from game import save_manager as sm
from game import worlds
from game.prompt_builder import (
    build_unified_messages,
    build_unified_opening_messages,
)
from game.state_schema import default_state

_PROSE = ("晨光穿过青云宗大殿的窗棂，落在一个白发老者的肩头。他看着林晚，缓缓开口："
          "\"你终于来了。天澜秘境的钥匙，在你身上吧。\"林晚握紧怀中的半块玉牌，点了点头。")

_ARCHIVE = {"character": {"name": "林晚", "gender": "男", "age": 18, "identity": "青云宗弟子"}}


def _fake_turn_ok(messages, api_key=None, max_tokens=2800):
    """正常 unified 调用返回值。"""
    return {
        "narrative": _PROSE,
        "options": [
            {"label": "A", "text": "测试A", "recommended": True},
            {"label": "B", "text": "测试B"},
        ],
        "state_delta": {"gold": 10},
        "notes": ["一条测试笔记"],
        "event": "测试事件",
    }


def _fake_turn_empty(messages, api_key=None, max_tokens=2800):
    """API 彻底失败返回 {}。"""
    return {}


def _fake_turn_no_options(messages, api_key=None, max_tokens=2800):
    """返回合法 JSON 但缺 options。"""
    return {
        "narrative": _PROSE,
        "state_delta": {"gold": 5},
        "notes": [],
        "event": "",
    }


def _fake_turn_short_narrative(messages, api_key=None, max_tokens=2800):
    """narrative 过短（< NARRATIVE_MIN_CHARS）。"""
    return {
        "narrative": "。",
        "options": [{"label": "A", "text": "继续", "recommended": True}],
        "state_delta": {},
        "notes": [],
        "event": "",
    }


@pytest.fixture()
def M(monkeypatch, tmp_path):
    """隔离真实数据：临时数据目录 + 固定 unified 调用替换。"""
    monkeypatch.setattr(sm, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(sm, "ACTIVATIONS_PATH", tmp_path / "activations.json")
    main._SESSIONS.clear()
    return main


def _new_session(M, sid="s1"):
    world = worlds.get_world("douluo")
    state = default_state(_ARCHIVE, world)
    M._SESSIONS[sid] = M._new_session(state, [], _ARCHIVE)
    return state


def _run_turn_sse(M, sid="s1", action="去藏经阁查玉牌线索", opening=False):
    """驱动 _run_turn，收集全部 SSE 事件，返回 (narrative, options, error)。"""
    gen = M._run_turn(sid, action, opening=opening, api_key="sk-test",
                      freedom=3, client_id="test")
    texts, delta, error = [], None, None
    for ev in gen:
        evt = ev.split("\n", 1)[0].replace("event: ", "")
        if "\ndata: " in ev:
            data = json.loads(ev.split("\ndata: ", 1)[1])
        else:
            data = {}
        if evt == "text":
            texts.append(data.get("content", ""))
        elif evt == "delta":
            delta = data
        elif evt == "error":
            error = data
    return "".join(texts), (delta or {}).get("options", []), error


# ── 正常流程 ─────────────────────────────────────

def test_normal_turn_produces_narrative_and_options(M, monkeypatch):
    """正常 JSON 返回 → narrative 逐段推送 + delta 包含 options + 落盘。"""
    monkeypatch.setattr(M, "_call_turn", _fake_turn_ok)
    _new_session(M)

    narrative, options, error = _run_turn_sse(M, opening=True)

    assert error is None
    assert _PROSE in narrative                  # narrative 被逐段 SSE 推送
    assert len(options) == 2
    assert options[0]["label"] == "A"
    # 落盘验证
    sess = M._SESSIONS["s1"]
    assert json.loads(sess["history"][-1])["content"] == _PROSE
    assert sess["turns"][-1]["narrative"] == _PROSE
    assert sess["turns"][-1]["notes"] == ["一条测试笔记"]
    assert sess["turns"][-1]["event"] == "测试事件"


def test_normal_turn_non_opening(M, monkeypatch):
    """非开场回合同样正常产出。"""
    monkeypatch.setattr(M, "_call_turn", _fake_turn_ok)
    state = _new_session(M)
    # 给一个已存在的 history 模拟非开场场景
    M._SESSIONS["s1"]["history"] = [
        json.dumps({"role": "user", "content": "去修炼"}),
        json.dumps({"role": "assistant", "content": "你走向修炼场。"}),
    ]

    narrative, options, error = _run_turn_sse(M, opening=False)

    assert error is None
    assert len(options) == 2
    assert _PROSE in narrative


# ── 退化/fallback ────────────────────────────────

def test_empty_response_uses_fallback(M, monkeypatch):
    """_call_turn 返回 {} → 模板叙述 + 默认选项，不崩溃。"""
    monkeypatch.setattr(M, "_call_turn", _fake_turn_empty)
    _new_session(M)

    narrative, options, error = _run_turn_sse(M, opening=True)

    assert error is None
    assert "环顾四周" in narrative              # fallback 模板
    assert len(options) == 1                     # _normalize_options 兜底
    assert options[0]["text"] == "继续前行"


def test_short_narrative_uses_fallback(M, monkeypatch):
    """narrative 过短（"。"→ < 30 chars）→ fallback 模板。"""
    monkeypatch.setattr(M, "_call_turn", _fake_turn_short_narrative)
    _new_session(M)

    narrative, options, error = _run_turn_sse(M, opening=True)

    assert error is None
    assert "环顾四周" in narrative              # fallback 覆盖了短 narrative


def test_missing_options_gets_default(M, monkeypatch):
    """合法 JSON 但缺 options → _normalize_options 返回兜底单选项。"""
    monkeypatch.setattr(M, "_call_turn", _fake_turn_no_options)
    _new_session(M)

    narrative, options, error = _run_turn_sse(M, opening=True)

    assert error is None
    assert _PROSE in narrative                  # narrative 正常
    assert len(options) == 1                     # options 兜底
    assert options[0]["text"] == "继续前行"


# ── 提示词验证 ──────────────────────────────────

def test_unified_messages_forbids_mixing():
    """统一提示词明确要求 narrative 和 options 在 JSON 中分离。"""
    world = worlds.get_world("douluo")
    state = default_state(_ARCHIVE, world)
    msgs = build_unified_messages(state, [], "去藏经阁", 1000, world)
    user = msgs[-1]["content"]
    assert "JSON 对象" in user
    assert "narrative（字符串）" in user
    assert "options（数组）" in user
    assert "绝不包含选项列表" in user
    assert "JSON 结构" in user


def test_unified_opening_messages_forbids_mixing():
    """开场提示词同样要求 JSON 结构化输出。"""
    world = worlds.get_world("douluo")
    state = default_state(_ARCHIVE, world)
    msgs = build_unified_opening_messages(state, _ARCHIVE, 1000, world)
    user = msgs[-1]["content"]
    assert "JSON 对象" in user
    assert "narrative（字符串）" in user
    assert "options（数组）" in user


def test_unified_opening_messages_custom_world():
    """自定义世界（generic）的开场 JSON 提示词。"""
    world = worlds.get_world("douluo")
    world["summary"] = "generic"
    world["name"] = "青云界"
    state = default_state(_ARCHIVE, world)
    msgs = build_unified_opening_messages(state, _ARCHIVE, 1000, world)
    user = msgs[-1]["content"]
    assert "青云界" in user


# ── _call_turn 重试逻辑 ──────────────────────────

class _FakeCompletions:
    """可替换的 chat.completions 对象，支持 create() 方法。"""
    def __init__(self, create_fn):
        self.create = create_fn


class _FakeClient:
    """可替换的 OpenAI client，只暴露 chat.completions。"""
    def __init__(self, create_fn):
        self.chat = type("chat", (), {"completions": _FakeCompletions(create_fn)})()


def test_call_turn_retries_on_empty_narrative(M, monkeypatch):
    """_call_turn：narrative 为空 → 重试 1 次。"""
    calls = {"n": 0}

    def fake_create(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            content = '{"narrative": "", "options": [], "state_delta": {}}'
        else:
            content = json.dumps({
                "narrative": _PROSE,
                "options": [{"label": "A", "text": "测试A", "recommended": True},
                            {"label": "B", "text": "测试B"}],
                "state_delta": {"gold": 10},
                "notes": ["一条测试笔记"],
                "event": "测试事件",
            }, ensure_ascii=False)
        return _make_resp(content)

    monkeypatch.setattr(M, "_client_for", lambda api_key=None: _FakeClient(fake_create))
    result = M._call_turn([{"role": "user", "content": "test"}], api_key="sk-test")
    assert calls["n"] == 2
    assert result["narrative"] == _PROSE


def test_call_turn_retries_on_missing_options(M, monkeypatch):
    """_call_turn：缺 options → 重试 1 次。"""
    calls = {"n": 0}

    def fake_create(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            content = '{"narrative": "' + _PROSE + '", "state_delta": {}}'
        else:
            content = json.dumps({
                "narrative": _PROSE,
                "options": [{"label": "A", "text": "测试A", "recommended": True},
                            {"label": "B", "text": "测试B"}],
                "state_delta": {"gold": 10},
                "notes": ["一条测试笔记"],
                "event": "测试事件",
            }, ensure_ascii=False)
        return _make_resp(content)

    monkeypatch.setattr(M, "_client_for", lambda api_key=None: _FakeClient(fake_create))
    result = M._call_turn([{"role": "user", "content": "test"}], api_key="sk-test")
    assert calls["n"] == 2
    assert len(result["options"]) == 2


def test_call_turn_returns_empty_on_total_failure(M, monkeypatch):
    """_call_turn：两次都返回无效 JSON → 返回 {}。"""
    calls = {"n": 0}

    def fake_create(*args, **kwargs):
        calls["n"] += 1
        return _make_resp("not valid json at all {{{")

    monkeypatch.setattr(M, "_client_for", lambda api_key=None: _FakeClient(fake_create))
    result = M._call_turn([{"role": "user", "content": "test"}], api_key="sk-test")
    assert calls["n"] == 2
    assert result == {}


# ── helpers ─────────────────────────────────────

class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMsg(content)


class _FakeMsg:
    def __init__(self, content):
        self.content = content


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _make_resp(content):
    return _FakeResp(content)
