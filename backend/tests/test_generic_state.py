"""通用世界状态：default_state / validate_delta / apply_delta 按世界规格驱动。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.game_engine import apply_delta
from game.state_schema import default_state, validate_delta

CUSTOM = {
    "id": "w1", "name": "青云志", "desc": "", "kind": "custom", "owner": "u1",
    "summary": "generic", "rulebook": "规则" * 100,
    "state_template": {
        "character": {"name": "无名", "identity": "穿越者"},
        "level_field": "修为",
        "resources": {"灵石": {"init": 10, "min": 0}},
        "stats": {"修为": {"init": 1, "min": 1, "max": 10, "max_step": 2}},
        "affection_chars": ["林晚"], "factions": ["青云宗"],
        "inventory": [], "start_location": "青云宗",
    },
    "creation_schema": {"steps": []},
}


def test_generic_default_state():
    s = default_state({"character": {"name": "阿灵"}}, CUSTOM)
    assert s["meta"]["world_id"] == "w1"
    assert s["character"]["name"] == "阿灵"
    assert s["resources"]["灵石"] == 10
    assert s["stats"]["修为"] == 1
    assert s["affection"]["林晚"] == 0
    assert "soul_rings" not in s  # 无 rings 世界不建魂环


def test_generic_resources_clamped_to_min():
    s = default_state({"character": {}}, CUSTOM)
    d = validate_delta({"resources": {"灵石": -999}}, s, CUSTOM)
    assert d["resources"]["灵石"] == -10  # 最多扣到 min=0
    apply_delta(s, {"resources": {"灵石": -999}}, CUSTOM)
    assert s["resources"]["灵石"] == 0


def test_generic_stats_max_step_and_bounds():
    s = default_state({"character": {}}, CUSTOM)
    d = validate_delta({"stats": {"修为": 100}}, s, CUSTOM)
    assert d["stats"]["修为"] == 2  # max_step=2
    apply_delta(s, d, CUSTOM)
    assert s["stats"]["修为"] == 3


def test_generic_dynamic_affection_add():
    s = default_state({"character": {}}, CUSTOM)
    d = validate_delta({"affection": {"新角色": 5}}, s, CUSTOM)
    assert d["affection"]["新角色"] == 5
    apply_delta(s, d, CUSTOM)
    assert s["affection"]["新角色"] == 5


def test_no_rings_world_ignores_soul_ring_add():
    s = default_state({"character": {}}, CUSTOM)
    d = validate_delta({"soul_ring_add": {"years": 999}}, s, CUSTOM)
    assert "soul_ring_add" not in d


def test_legacy_keys_ignored_in_generic():
    s = default_state({"character": {}}, CUSTOM)
    d = validate_delta({"gold": -5, "silver": 1, "soul_level": 30}, s, CUSTOM)
    assert d["resources"] == {}
    assert "soul_level" not in d
    assert d["gold"] == 0  # 镜像键按 0 处理，不会误扣


def test_unknown_stats_ignored():
    s = default_state({"character": {}}, CUSTOM)
    d = validate_delta({"stats": {"不存在": 50}}, s, CUSTOM)
    assert d["stats"] == {}


def test_world_without_resources_stats_is_empty():
    """手建规格可缺 resources/stats，default_state 兜底为空 dict 而不报错。"""
    w = {"id": "x", "name": "x", "kind": "custom", "summary": "generic",
         "rulebook": "r", "state_template": {"character": {"name": "无名"}}}
    s = default_state({"character": {}}, w)
    assert s["meta"]["world_id"] == "x"
    assert s["resources"] == {}
    assert s["stats"] == {}
    assert s["affection"] == {}
    assert s["faction"] == {}
