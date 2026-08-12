"""万物生世界：规格加载 / 广场排序 / 初始状态 / 境界·势力·属性结算 / 摘要渲染。

万物生是内置世界（backend/worlds/wanwusheng.json），出现在世界广场"创作者已开发的世界"
中、魂兽大陆之下（builtin_worlds() 按文件名排序，douluo.json < wanwusheng.json）。
它的等级字段是 realm（1 吐纳→7 无上），资源是"元"，属性有灵力/神识/体魄，
并首次用上 faction（势力声望）增量。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import worlds
from game.game_engine import apply_delta
from game.prompt_builder import state_summary
from game.state_schema import default_state, validate_delta


def test_wanwusheng_world_loaded():
    w = worlds.get_world("wanwusheng")
    assert w is not None
    assert w["name"] == "万物生"
    assert w["kind"] == "builtin"
    assert w["owner"] is None  # 创作者出品，对所有人可见
    assert w["summary"] == "wanwusheng"
    assert len(w["rulebook"]) > 200  # 规则书完整解析
    t = w["state_template"]
    assert t["level_field"] == "realm"
    assert t["resources"]["元"]["init"] == 300
    assert "姜夜阑" in t["affection_chars"]
    assert "镇灵司" in t["factions"]


def test_plaza_order_douluo_then_wanwusheng():
    """万物生排在魂兽大陆下面（文件名字典序 douluo < wanwusheng）。"""
    ids = [w["id"] for w in worlds.builtin_worlds()]
    assert ids.index("douluo") < ids.index("wanwusheng")


def test_default_state():
    w = worlds.get_world("wanwusheng")
    s = default_state({"character": {"name": "陈熵", "traits": ["吞噬亲和"], "identity": "外卖员"}}, w)
    assert s["meta"]["world_id"] == "wanwusheng"
    assert s["character"]["name"] == "陈熵"
    assert s["character"]["realm"] == 1  # 开局吐纳
    assert s["resources"]["元"] == 300
    assert s["stats"]["灵力"] == 20
    assert s["stats"]["神识"] == 5
    assert s["stats"]["体魄"] == 20
    assert s["affection"]["姜夜阑"] == 0
    assert s["faction"]["镇灵司"] == 0
    assert s["location"]["place"] == "锦官城"


def test_realm_breakthrough_clamped():
    """境界是绝对目标，一次最多 +1：越权冲级会被钳制回合法进度。"""
    w = worlds.get_world("wanwusheng")
    s = default_state({"character": {}}, w)
    d = validate_delta({"realm": 9}, s, w)
    assert d["realm"] == 2
    apply_delta(s, d, w)
    assert s["character"]["realm"] == 2


def test_stats_inc_clamped_to_max_step():
    w = worlds.get_world("wanwusheng")
    s = default_state({"character": {}}, w)
    d = validate_delta({"stats": {"灵力": 999}}, s, w)
    assert d["stats"]["灵力"] == 30  # max_step=30
    apply_delta(s, d, w)
    assert s["stats"]["灵力"] == 50


def test_faction_and_affection_deltas():
    w = worlds.get_world("wanwusheng")
    s = default_state({"character": {}}, w)
    d = validate_delta({"faction": {"镇灵司": 10, "不存在": 5}, "affection": {"姜夜阑": 3}}, s, w)
    assert d["faction"]["镇灵司"] == 10
    assert "不存在" not in d["faction"]  # 未知势力忽略
    assert d["affection"]["姜夜阑"] == 3
    apply_delta(s, d, w)
    assert s["faction"]["镇灵司"] == 10
    assert s["affection"]["姜夜阑"] == 3


def test_money_and_inventory():
    w = worlds.get_world("wanwusheng")
    s = default_state({"character": {}}, w)
    d = validate_delta({"resources": {"元": -50}, "inventory_add": ["饕餮牙坠"]}, s, w)
    apply_delta(s, d, w)
    assert s["resources"]["元"] == 250
    assert s["inventory"] == ["饕餮牙坠"]


def test_summary_shows_realm_name():
    """专属摘要把境界数值渲染成中文境界名，而不是裸数字。"""
    w = worlds.get_world("wanwusheng")
    s = default_state({"character": {"name": "陈熵", "gender": "男", "age": 22}}, w)
    txt = state_summary(s, w)
    assert "境界：吐纳" in txt
    assert "锦官城" in txt
    assert "元" in txt
