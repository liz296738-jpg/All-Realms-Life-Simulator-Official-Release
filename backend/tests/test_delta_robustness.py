"""Delta 鲁棒性回归测试：AI 结算偶尔吐 null/脏类型，后端必须兜底不崩、不脏库。

覆盖超算工作流（wf_77838ab0）审查确认的三处真实缺陷：
- location/date 为 null 时 dict.get 返回 None → str(None) 把状态写坏
- inventory_add/inventory_remove/notes_add 为 null 时遍历 None → TypeError
- level_field / stats 的 max_step、min、max 配置非数字时 int() 直接 ValueError
- _guess_season 对"入冬后"这类关键词日期误判为"春"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import worlds
from game.game_engine import _guess_season, apply_delta
from game.state_schema import default_state, validate_delta


def _gebi_state():
    w = worlds.get_world("gebi")
    return default_state({"character": {"name": "林栀"}}, w), w


def test_null_location_and_date_keep_previous_value():
    """delta 里 location/date 显式写 null：不能变成 'None' 污染状态。"""
    s, w = _gebi_state()
    apply_delta(s, {"location": None, "date": None}, w)
    assert s["location"]["place"] == "老城区·旧居民楼顶楼"  # 保持旧值
    assert s["location"]["date"] == "第1年1月"


def test_null_inventory_notes_lists_do_not_crash():
    """delta 里 inventory_add/inventory_remove/notes_add 为 null：不能 TypeError。"""
    s, w = _gebi_state()
    # 未包 try/except 的路径（apply_delta 之外也调用 validate_delta 单测）
    d = validate_delta({"inventory_add": None, "inventory_remove": None, "notes_add": None}, s, w)
    assert d["inventory_add"] == []
    assert d["inventory_remove"] == []
    assert d["notes_add"] == []
    apply_delta(s, {"inventory_add": None, "notes_add": None}, w)
    assert s["inventory"] == []
    assert s["notes"] == []


def test_unguarded_int_in_stats_max_step():
    """stats 配置 max_step 为脏类型（None/字符串）时不崩。"""
    w = worlds.get_world("gebi")
    spec = w["state_template"]["stats"]["灵感"].copy()
    spec["max_step"] = None  # 模拟脏配置
    w["state_template"]["stats"]["灵感"] = spec
    s = default_state({"character": {}}, w)
    d = validate_delta({"stats": {"灵感": 50}}, s, w)
    apply_delta(s, d, w)
    assert s["stats"]["灵感"] >= 50  # 无上限钳制时如实落账


def test_guess_season_keyword_dates():
    """关键词日期（入冬后/春日/盛夏）应按季节词判定，而非回退到"春"。"""
    assert _guess_season("入冬后") == "冬"
    assert _guess_season("春分前后") == "春"
    assert _guess_season("盛夏") == "夏"
    assert _guess_season("深秋") == "秋"


def test_guess_season_numeric_dates_unchanged():
    """数字月份路径保持原行为：9月→秋，12月→冬。"""
    assert _guess_season("9月") == "秋"
    assert _guess_season("12月") == "冬"
    assert _guess_season("4月") == "春"
    assert _guess_season("7月") == "夏"


def test_null_delta_object_treated_as_empty():
    """整个 state_delta 为 null 时按空变动处理，不崩。"""
    s, w = _gebi_state()
    apply_delta(s, None, w)
    assert s["character"]["name"] == "林栀"
