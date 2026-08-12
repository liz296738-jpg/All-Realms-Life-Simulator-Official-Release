"""剧情导出：叙述正文 → Markdown 小说。

导出只保留 AI 叙述正文：去掉每回合开头的【地点·场景·季节·时段】标注与结尾
的【选项】块，用 --- 作场景分隔；标题带世界名与主角名，文件名可跨平台。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.exporter import _safe_filename_part, _strip_meta, build_novel_markdown


def _state(name="林栀", world_id="gebi", world_name="隔壁的租客"):
    return {"character": {"name": name},
            "meta": {"world_id": world_id, "world_name": world_name}}


def test_strip_meta_removes_location_header_and_options():
    text = "【老城区·旧居民楼顶楼·夏夜·晚上十点】\n\n雨点敲窗，楼下早餐铺的灯还亮着。\n\n【选项】\nA. 隔着门递过去一碗粥\nB. 装作没听见"
    out = _strip_meta(text)
    assert out == "雨点敲窗，楼下早餐铺的灯还亮着。"
    assert "【" not in out
    assert "选项" not in out


def test_strip_meta_without_meta_returns_prose():
    assert _strip_meta("就是一段平平常常的正文。") == "就是一段平平常常的正文。"


def test_empty_turns_returns_zero():
    r = build_novel_markdown(_state(), [])
    assert r["turns"] == 0
    assert r["content"] == ""
    assert r["filename"] == ""


def test_single_turn_forms_title_and_prose():
    turns = [{"narrative": "【顶楼·秋夜·晚上十点】\n\n雨点敲窗。\n\n【选项】\nA. 递粥"}]
    r = build_novel_markdown(_state(), turns)
    assert r["turns"] == 1
    assert r["title"] == "《隔壁的租客》——林栀的一段旅程"
    assert "雨点敲窗" in r["content"]
    assert "【选项】" not in r["content"]
    assert "林栀" in r["content"]
    assert r["filename"].endswith(".md")
    assert ".." not in r["filename"].replace("……", "")  # 无连续点（防目录穿越误判）
    assert r["chars"] == len(r["content"])


def test_multiple_turns_separated_by_hr():
    turns = [
        {"narrative": "【顶楼·秋夜】\n\n第一段。"},
        {"narrative": "【顶楼·次日清晨】\n\n第二段。"},
    ]
    r = build_novel_markdown(_state(), turns)
    assert r["turns"] == 2
    assert r["content"].count("\n---\n") == 1  # 恰一段场景分隔
    assert r["content"].index("第一段") < r["content"].index("第二段")


def test_missing_name_falls_back_to_unknown():
    """state 缺角色名/世界元数据时：主角名回落"无名"，世界回落魂兽大陆（douluo 兜底），不崩。"""
    r = build_novel_markdown({}, [{"narrative": "正文。"}])
    assert r["title"].endswith("无名的一段旅程")
    assert r["filename"].startswith("魂兽大陆-无名-")


def test_filename_safe_part_sanitizes():
    assert _safe_filename_part('隔壁/的:*租客?') == "隔壁-的-租客"
    assert _safe_filename_part('   ') == "旅程"


# ── 超算审查确认的边界：前导空白 / 正文开篇标签 / 中途选项字样 / 自定义世界 ──

def test_strip_meta_with_leading_whitespace_still_removes_header():
    """正文前带空行/空格/BOM 时，【地点…】头仍要被剥掉，不能漏进正文。"""
    out = _strip_meta("\n\n【地点·秋夜】\n\n正文。")
    assert out == "正文。"
    out2 = _strip_meta("  【老城区·夏夜】\n\n正文。")
    assert out2 == "正文。"


def test_strip_meta_preserves_non_location_bracket_opening():
    """只剥含「·」的场景标注；【雨声】【内心独白】这类正文开篇标签保留。"""
    assert _strip_meta("【雨声】窗外下起雨。") == "【雨声】窗外下起雨。"


def test_strip_meta_keeps_prose_after_mid_text_options():
    """正文中途出现「选项」字样不截断；只裁掉最后一个【选项】块。"""
    out = _strip_meta("前半正文【选项】A.甲\nB.乙\n然后还有后续正文？【选项】\nA. 真选项")
    assert "前半正文" in out
    assert "然后还有后续正文？" in out
    assert "真选项" not in out  # 真正的选项尾巴被裁掉


def test_strip_meta_custom_world_option_tail():
    """自定义世界没有【选项】标记：末尾 ≥2 行的 A./B./C. 连排块被去掉。"""
    out = _strip_meta("正文一段。\n\nA. 去图书馆\nB. 回宿舍\nC. 去食堂")
    assert out == "正文一段。"


def test_strip_meta_single_option_looking_line_kept():
    """单行"对白/引用"形似选项（不足 2 行）应保留。"""
    out = _strip_meta("正文。\n\nA. 你先走，我留下。")
    assert out.endswith("A. 你先走，我留下。")


def test_strip_meta_removes_stray_hr_before_options():
    """douluo 规则书用 --- 分隔正文与选项：尾部残留的 --- 行要去掉。"""
    out = _strip_meta("正文。\n\n---\n\n【选项】\nA. 走\nB. 留")
    assert out == "正文。"


def test_no_dangling_separator_when_last_turn_strips_empty():
    """末回合是纯元信息（无正文）时，导出不能以悬空 --- 结尾，turns 按实际场景计。"""
    turns = [
        {"narrative": "【老城区·秋夜】\n\n有正文。\n\n【选项】\nA. 走"},
        {"narrative": "【老城区·秋夜】\n\n【选项】\nA. 走"},  # 剥完是空
    ]
    r = build_novel_markdown(_state(), turns)
    assert r["turns"] == 1
    assert not r["content"].rstrip().endswith("---")
    assert r["content"].count("\n---\n") == 0


def test_all_meta_turns_returns_empty():
    """所有回合都是纯元信息：无可导出正文，turns=0、content 为空。"""
    turns = [{"narrative": "【老城区·秋夜】\n\n【选项】\nA. 走"}]
    r = build_novel_markdown(_state(), turns)
    assert r["turns"] == 0
    assert r["content"] == ""


def test_non_dict_character_does_not_crash():
    """state['character'] 为脏类型（字符串）时按"无名"兜底，不 500。"""
    r = build_novel_markdown({"character": "Alice", "meta": {}},
                             [{"narrative": "正文。"}])
    assert r["title"].endswith("无名的一段旅程")
    assert "正文。" in r["content"]
