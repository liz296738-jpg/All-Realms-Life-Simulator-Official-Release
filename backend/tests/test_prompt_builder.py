import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.state_schema import default_state
from game.prompt_builder import (
    state_summary, build_narrative_messages, build_opening_messages, build_settle_messages,
)


def make_state():
    return default_state({"character": {"name": "林默", "innate_soul_power": 7,
        "talent_tier": "天才档", "origin": "平民", "initial_gold": 8,
        "secret": "背负家族复仇的执念"}, "direction": "自由/综合向"})


def test_state_summary_contains_key_fields():
    s = make_state()
    summary = state_summary(s)
    for key in ["林默", "魂力", "白灵藤", "云溪镇", "财富", "自由/综合向"]:
        assert key in summary


def test_narrative_messages_have_system_and_action():
    s = make_state()
    msgs = build_narrative_messages(s, [], "查看周围环境")
    assert msgs[0]["role"] == "system"
    assert "查看周围环境" in msgs[-1]["content"]


def test_history_replayed_in_order():
    s = make_state()
    hist = [
        json.dumps({"role": "user", "content": "行动1"}, ensure_ascii=False),
        json.dumps({"role": "assistant", "content": "叙述1"}, ensure_ascii=False),
    ]
    msgs = build_narrative_messages(s, hist, "行动2")
    contents = [m["content"] for m in msgs if m["role"] in ("user", "assistant")]
    assert "行动1" in contents[0]
    assert "叙述1" in contents[1]


def test_opening_and_settle_messages_build():
    s = make_state()
    assert len(build_opening_messages(s, {})) >= 3
    settle = build_settle_messages(s, [], "一段叙述文本")
    assert "JSON" in settle[-1]["content"]
