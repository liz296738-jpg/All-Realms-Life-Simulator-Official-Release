import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.state_schema import default_state, validate_delta


def make_archive(**kw):
    base = {"character": {"name": "测试", "gender": "男", "age": 12,
            "wuhun": "白灵藤", "innate_soul_power": 5, "talent_tier": "普通魂师档",
            "origin": "平民", "initial_gold": 8}}
    base.update(kw)
    return base


def test_default_state_starts_at_innate():
    s = default_state(make_archive())
    assert s["character"]["soul_level"] == 5
    assert s["soul_rings"] == []
    assert s["resources"]["gold"] == 8
    assert s["affection"]["云昊"] == 0


def test_initial_gold_at_archive_root():
    # 前端 CreationWizard 把 initial_gold 放在档案顶层 → 应从档案根层读取
    a = make_archive()
    del a["character"]["initial_gold"]
    a["initial_gold"] = 88
    s = default_state(a)
    assert s["resources"]["gold"] == 88


def test_validate_clamps_gold_non_negative():
    s = default_state(make_archive())
    d = validate_delta({"gold": -999}, s)
    # 只能花到 0
    assert d["gold"] == -8


def test_validate_clamps_affection():
    s = default_state(make_archive())
    s["affection"]["云昊"] = 99
    d = validate_delta({"affection": {"云昊": 5}}, s)
    assert d["affection"]["云昊"] == 100


def test_validate_caps_soul_level_delta():
    s = default_state(make_archive())
    d = validate_delta({"soul_level": 30}, s)  # 目标30，现5
    assert d["soul_level"] <= 7  # 单轮最多+2


def test_validate_ring_year_cap():
    s = default_state(make_archive())
    d = validate_delta({"soul_ring_add": {"years": 9000, "beast": "X", "skill": "S"}}, s)
    assert d["soul_ring_add"]["slot"] == 1
    assert d["soul_ring_add"]["years"] == 423  # 第一环上限


def test_validate_rejects_skipping_ring():
    s = default_state(make_archive())
    s["soul_rings"] = [{"slot": 1, "years": 400, "beast": "a", "skill": "b", "attribute": "c"}]
    d = validate_delta({"soul_ring_add": {"years": 400, "beast": "X", "skill": "S"}}, s)
    assert d["soul_ring_add"]["slot"] == 2
