"""世界规格加载 / 校验 / 落盘 / 删除测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game import worlds


def custom_spec(owner="u1"):
    return {
        "id": "abc123", "name": "测试世界", "desc": "测试", "kind": "custom",
        "owner": owner, "summary": "generic", "rulebook": "规则" * 100,
        "state_template": {
            "character": {"name": "无名", "age": 0},
            "level_field": "修为",
            "resources": {"灵石": {"init": 10, "min": 0}},
            "stats": {"修为": {"init": 1, "min": 1, "max": 100, "max_step": 3}},
            "affection_chars": [], "factions": [],
            "inventory": [], "start_location": "青云宗",
        },
        "creation_schema": {"steps": []},
    }


def test_douluo_world_loaded_from_spec():
    w = worlds.get_world("douluo")
    assert w is not None
    assert w["name"] == "魂兽大陆"
    assert w["kind"] == "builtin"
    assert len(w["rulebook"]) > 1000  # 规则书完整解析（来自 system_prompt.txt）
    t = w["state_template"]
    assert t["level_field"] == "soul_level"
    assert t["rings"]["cap_slots"][0] == 423
    assert t["resources"]["gold"]["from_archive"] == "initial_gold"


def test_unknown_world_returns_none():
    assert worlds.get_world("nope") is None


def test_custom_world_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(worlds, "CUSTOM_DIR", tmp_path)
    worlds._invalidate()
    spec = worlds.save_custom_world(custom_spec())
    assert spec["kind"] == "custom"
    loaded = worlds.get_world("abc123")
    assert loaded is not None
    assert loaded["name"] == "测试世界"
    assert loaded["owner"] == "u1"
    assert worlds.delete_custom_world("abc123") is True
    assert worlds.get_world("abc123") is None


def test_invalid_spec_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(worlds, "CUSTOM_DIR", tmp_path)
    worlds._invalidate()
    with pytest.raises(ValueError):
        worlds.save_custom_world({"id": "x", "name": "y", "desc": "",
                                  "kind": "custom", "owner": "u1"})  # 缺 state_template


def test_world_summary_omits_rulebook():
    w = worlds.get_world("douluo")
    s = worlds.world_summary(w)
    assert "rulebook" not in s
    assert s["id"] == "douluo"
    assert s["summary"] == "douluo"
