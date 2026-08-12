import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.state_schema import default_state
from game.game_engine import apply_delta


def make():
    return default_state({"character": {"name": "A", "innate_soul_power": 5,
        "talent_tier": "普通魂师档", "origin": "平民", "initial_gold": 10}})


def test_applies_money_and_affection():
    s = make()
    apply_delta(s, {"gold": -3, "silver": 2, "affection": {"云昊": 5}})
    assert s["resources"]["gold"] == 7
    assert s["resources"]["silver"] == 2
    assert s["affection"]["云昊"] == 5


def test_applies_soul_level_and_ring():
    s = make()
    apply_delta(s, {"soul_level": 7, "soul_ring_add": {"years": 400, "beast": "曼陀罗蛇", "skill": "缠绕"}})
    assert s["character"]["soul_level"] == 7
    assert s["soul_rings"][0]["slot"] == 1


def test_affection_decay_when_month_passes():
    s = make()
    s["affection"]["云昊"] = 30
    s["affection_last_seen"]["云昊"] = 0
    apply_delta(s, {"month_delta": 2, "affection": {"苏灵儿": 3}})
    # 云昊 2 个月未见 → 每月-1 共-2；苏灵儿刚见面不衰减
    assert s["affection"]["云昊"] == 28
    assert s["affection"]["苏灵儿"] == 3


def test_season_inferred_from_date():
    s = make()
    apply_delta(s, {"date": "第2年7月"})
    assert s["location"]["season"] == "夏"
