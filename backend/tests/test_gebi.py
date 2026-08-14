"""隔壁的租客世界：规格加载 / 广场排序 / 初始状态 / 心动值·属性·好感结算 / 摘要渲染。

隔壁的租客是内置世界（backend/worlds/gebi.json），现代都市慢热甜文。
它的等级字段是 heart（心动值 0-100，绝对目标、max_step=8、min/max 钳制），
资源是"元"，属性有灵感/精力/心情，无势力声望（factions 缺省为空）。
文件名 gebi.json 排序在 douluo.json 与 wanwusheng.json 之间，广场显示为
魂兽大陆 → 隔壁的租客 → 万物生。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import worlds
from game.game_engine import apply_delta
from game.prompt_builder import state_summary
from game.state_schema import default_state, validate_delta


def test_gebi_world_loaded():
    w = worlds.get_world("gebi")
    assert w is not None
    assert w["name"] == "隔壁的租客"
    assert w["kind"] == "builtin"
    assert w["owner"] is None  # 创作者出品，对所有人可见
    assert w["summary"] == "gebi"
    assert len(w["rulebook"]) > 200  # 规则书完整解析
    t = w["state_template"]
    assert t["level_field"] == "heart"
    assert t["character"]["heart"]["max"] == 100
    assert t["resources"]["元"]["init"] == 800
    assert "沈砚" in t["affection_chars"]
    assert "factions" not in t  # 情感世界无势力声望


def test_plaza_order_douluo_gebi_wanwusheng():
    """文件名字典序 douluo < gebi < wanwusheng：魂兽大陆 → 隔壁的租客 → 万物生。"""
    ids = [w["id"] for w in worlds.builtin_worlds()]
    assert ids.index("douluo") < ids.index("gebi") < ids.index("wanwusheng")


def test_default_state():
    w = worlds.get_world("gebi")
    s = default_state({"character": {"name": "林栀", "job": "自由插画师", "traits": ["懒散但心软"]}}, w)
    assert s["meta"]["world_id"] == "gebi"
    assert s["character"]["name"] == "林栀"
    assert s["character"]["heart"] == 0  # 开局心动值为零
    assert s["resources"]["元"] == 800
    assert s["stats"]["灵感"] == 60
    assert s["stats"]["精力"] == 60
    assert s["stats"]["心情"] == 50
    assert s["affection"]["沈砚"] == 0
    assert s["faction"] == {}
    assert s["location"]["place"] == "老城区·旧居民楼顶楼"


def test_heart_progresses_and_caps_at_100():
    """心动值是绝对目标：每回合最多 ±8，且钳在 0-100 不溢出。"""
    w = worlds.get_world("gebi")
    s = default_state({"character": {}}, w)
    d = validate_delta({"heart": 999}, s, w)  # 越权冲到 999 → 只允许 +8
    assert d["heart"] == 8
    apply_delta(s, d, w)
    assert s["character"]["heart"] == 8
    # 从 96 起一次最多推到 100，不会溢出
    s["character"]["heart"] = 96
    d2 = validate_delta({"heart": 999}, s, w)
    assert d2["heart"] == 100
    apply_delta(s, d2, w)
    assert s["character"]["heart"] == 100
    # 已满再冲也不溢出
    d3 = validate_delta({"heart": 200}, s, w)
    assert d3["heart"] == 100
    apply_delta(s, d3, w)
    assert s["character"]["heart"] == 100


def test_stats_clamped_to_max_step_and_bounds():
    w = worlds.get_world("gebi")
    s = default_state({"character": {}}, w)
    d = validate_delta({"stats": {"灵感": 999}}, s, w)
    assert d["stats"]["灵感"] == 15  # max_step=15
    apply_delta(s, d, w)
    assert s["stats"]["灵感"] == 75


def test_affection_and_money():
    w = worlds.get_world("gebi")
    s = default_state({"character": {}}, w)
    d = validate_delta({"affection": {"沈砚": 5}, "resources": {"元": -50}}, s, w)
    apply_delta(s, d, w)
    assert s["affection"]["沈砚"] == 5
    assert s["resources"]["元"] == 750


def test_summary_shows_heart_and_cast():
    w = worlds.get_world("gebi")
    s = default_state({"character": {"name": "林栀", "gender": "女", "age": 25}}, w)
    apply_delta(s, {"affection": {"沈砚": 5}}, w)  # 好感度非零才会进入摘要
    txt = state_summary(s, w)
    assert "heart：0" in txt
    assert "沈砚(5)" in txt
    assert "老城区" in txt
