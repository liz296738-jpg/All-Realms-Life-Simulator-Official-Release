"""太上浮黎世界：规格加载 / 广场排序 / 初始状态 / 境界·势力·属性结算 / 摘要渲染 / 正典完整性。

太上浮黎是内置世界（backend/worlds/taishangfuli.json），出现在世界广场"创作者已开发的世界"
中。它的等级字段是 realm（1 炼气→7 合道），资源是"灵石"，属性有灵力/神识/体魄，
与万物生共用通用 stats/faction 体系；正典大纲（谢尘天命线）内嵌在规则书中。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import worlds
from game.game_engine import apply_delta
from game.prompt_builder import state_summary
from game.state_schema import default_state, validate_delta


def test_taishangfuli_world_loaded():
    w = worlds.get_world("taishangfuli")
    assert w is not None
    assert w["name"] == "太上浮黎"
    assert w["kind"] == "builtin"
    assert w["owner"] is None  # 创作者出品，对所有人可见
    assert w["summary"] == "taishangfuli"
    assert len(w["rulebook"]) > 200  # 规则书完整解析
    t = w["state_template"]
    assert t["level_field"] == "realm"
    assert t["resources"]["灵石"]["init"] == 50
    assert "谢尘" in t["affection_chars"]
    assert "苏清月" in t["affection_chars"]
    assert "太虚剑宗" in t["factions"]


def test_plaza_order_douluo_before_taishangfuli():
    """太上浮黎排在魂兽大陆下面（文件名字典序 douluo < taishangfuli）。"""
    ids = [w["id"] for w in worlds.builtin_worlds()]
    assert ids.index("douluo") < ids.index("taishangfuli")


def test_rulebook_covers_seventy_days_of_canon():
    """规则书内嵌正典大纲：四幕事件、天命之子、核心人物与输出契约一个不少。"""
    rb = worlds.get_world("taishangfuli")["rulebook"]
    for beat in ("后山看云", "浮黎仙墟", "万妖山脉", "归墟渊", "风隙十三式",
                 "玄冥老祖", "青璇", "桂花茶", "有云从后山来",
                 "归尘", "青鸾涅槃丹", "本命羽", "余生都教你", "第十三式", "我在上面等你"):
        assert beat in rb
    # 输出契约关键约束
    assert "realm" in rb and "recommended" in rb
    assert "1 炼气" in rb and "7 合道" in rb
    assert "灵石" in rb
    # 契约澄清：realm 未突破必须写 JSON 原生 null，绝不能写 0
    assert "JSON 原生 null" in rb and "绝不能写 0" in rb


def test_rulebook_factions_include_qingluan():
    """七脉妖王列举与青鸾王并存，不矛盾：青鸾一脉明列在势力节。"""
    rb = worlds.get_world("taishangfuli")["rulebook"]
    assert "青鸾王" in rb
    assert "青鸾一脉" in rb


def test_default_state():
    w = worlds.get_world("taishangfuli")
    s = default_state({"character": {"name": "顾长生", "traits": ["风隙天资"], "identity": "散修少年"}}, w)
    assert s["meta"]["world_id"] == "taishangfuli"
    assert s["character"]["name"] == "顾长生"
    assert s["character"]["realm"] == 1  # 开局炼气
    assert s["resources"]["灵石"] == 50
    assert s["stats"]["灵力"] == 20
    assert s["stats"]["神识"] == 5
    assert s["stats"]["体魄"] == 20
    assert s["affection"]["谢尘"] == 0
    assert s["faction"]["太虚剑宗"] == 0
    assert s["location"]["place"] == "太虚剑宗·山门"


def test_realm_breakthrough_clamped():
    """境界是绝对目标，一次最多 +1：越权冲级会被钳制回合法进度。"""
    w = worlds.get_world("taishangfuli")
    s = default_state({"character": {}}, w)
    d = validate_delta({"realm": 9}, s, w)
    assert d["realm"] == 2
    apply_delta(s, d, w)
    assert s["character"]["realm"] == 2


def test_realm_zero_clamped_to_one():
    """AI 误把 realm 写成 0 时，min=1 兜底把它钳回炼气，绝不跌破境界。"""
    w = worlds.get_world("taishangfuli")
    s = default_state({"character": {}}, w)
    d = validate_delta({"realm": 0}, s, w)
    assert d["realm"] == 1  # min=1：压零被钳回
    apply_delta(s, d, w)
    assert s["character"]["realm"] == 1


def test_stats_inc_clamped_to_max_step():
    w = worlds.get_world("taishangfuli")
    s = default_state({"character": {}}, w)
    d = validate_delta({"stats": {"灵力": 999}}, s, w)
    assert d["stats"]["灵力"] == 30  # max_step=30
    apply_delta(s, d, w)
    assert s["stats"]["灵力"] == 50


def test_faction_and_affection_deltas():
    w = worlds.get_world("taishangfuli")
    s = default_state({"character": {}}, w)
    d = validate_delta({"faction": {"太虚剑宗": 10, "不存在": 5}, "affection": {"谢尘": 3}}, s, w)
    assert d["faction"]["太虚剑宗"] == 10
    assert "不存在" not in d["faction"]  # 未知势力忽略
    assert d["affection"]["谢尘"] == 3
    apply_delta(s, d, w)
    assert s["faction"]["太虚剑宗"] == 10
    assert s["affection"]["谢尘"] == 3


def test_money_and_inventory():
    w = worlds.get_world("taishangfuli")
    s = default_state({"character": {}}, w)
    d = validate_delta({"resources": {"灵石": -50}, "inventory_add": ["风隙十三式·残卷"]}, s, w)
    apply_delta(s, d, w)
    assert s["resources"]["灵石"] == 0
    assert s["inventory"] == ["风隙十三式·残卷"]


def test_summary_shows_realm_name():
    """专属摘要渲染境界字段（realm 键 + 数值），由 world spec 驱动、无硬编码中文境界名。"""
    w = worlds.get_world("taishangfuli")
    s = default_state({"character": {"name": "顾长生", "gender": "男", "age": 18,
                                     "root": "中品金灵根", "direction": "剑修"}}, w)
    txt = state_summary(s, w)
    assert "realm：1" in txt
    assert "灵石" in txt
    assert "太虚剑宗·山门" in txt
    assert "剑修" in txt
