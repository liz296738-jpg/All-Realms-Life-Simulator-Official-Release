"""提取 NPC 情报接口：自定义世界兼容兜底回归测试。

Bug 背景：extract_npc_profiles 之前用 _resolve_world(world_id, None) 取 world context，
client_id 硬编码 None → 自定义世界作者校验 owner != _norm_cid(None)（= owner != ""）
恒成立 → 误抛 404「世界不存在」。修复后传入真实 client_id，并对世界丢失场景兜底 douluo。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import main
from api import routes as api_routes
from game import save_manager as sm
from game import worlds
from game import session_manager


def _spec(owner="u1"):
    return {
        "id": "abc123", "name": "我的世界", "desc": "自定义", "kind": "custom",
        "owner": owner, "summary": "generic", "rulebook": "规则" * 100,
        "state_template": {
            "character": {"name": "无名", "age": 0},
            "level_field": "修为",
            "resources": {"灵石": {"init": 10, "min": 0}},
            "stats": {"修为": {"init": 1, "min": 1, "max": 100, "max_step": 3}},
            "affection_chars": [], "factions": [],
            "inventory": [], "start_location": "青云宗",
        },
        "creation_schema": {"steps": [
            {"step": "身份", "fields": [
                {"key": "identity", "label": "你的身份", "type": "select",
                 "options": ["穿越者", "原创角色"], "required": True},
            ]},
        ]},
    }


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(sm, "ACTIVATIONS_PATH", tmp_path / "activations.json")
    monkeypatch.setattr(worlds, "CUSTOM_DIR", tmp_path / "custom_worlds")
    worlds._invalidate()
    session_manager._SESSIONS.clear()
    return TestClient(main.app)


def _fake_extract_client(monkeypatch, profiles):
    """把 extract 接口里的 DeepSeek 调用替换成返回固定 profiles 的假客户端。"""
    text = json.dumps({"profiles": profiles}, ensure_ascii=False)

    class _Completions:
        def create(self, **kw):
            msg = type("M", (), {"content": text})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _FakeClient:
        def __init__(self):
            self.chat = _Chat()

    monkeypatch.setattr(api_routes, "_client_for", lambda api_key=None: _FakeClient())


def _seed_session(session_id, world_id, world_name="未知世界"):
    state = {
        "meta": {"world_id": world_id, "world_name": world_name},
        "character": {"name": "阿灵"},
        "location": {"place": "青云宗", "date": "第1年1月"},
        "resources": {}, "stats": {}, "affection": {"李薇": 5}, "npcs": {},
    }
    sm.save_state(session_id, state, [])
    return state


def test_extract_npc_profiles_own_custom_world(client, monkeypatch):
    """自定义世界提取 NPC 情报不再 404「世界不存在」（核心回归）。"""
    worlds.save_custom_world(_spec("u1"))
    _seed_session("s1", "abc123", "我的世界")
    _fake_extract_client(monkeypatch, {"李薇": {"age": "25", "gender": "女", "background": "同门"}})

    r = client.post("/api/extract-npc-profiles", json={
        "session_id": "s1", "npc_names": ["李薇"], "client_id": "u1",
    })
    assert r.status_code == 200, r.text
    assert r.json()["profiles"]["李薇"]["background"] == "同门"


def test_extract_npc_profiles_builtin_world_still_works(client, monkeypatch):
    """内置世界（douluo）提取 NPC 情报不受影响。"""
    _seed_session("s2", "douluo", "魂兽大陆")
    _fake_extract_client(monkeypatch, {"李薇": {"age": "30", "background": "路人"}})

    r = client.post("/api/extract-npc-profiles", json={
        "session_id": "s2", "npc_names": ["李薇"], "client_id": "u1",
    })
    assert r.status_code == 200, r.text
    assert r.json()["profiles"]["李薇"]["age"] == "30"


def test_extract_npc_profiles_missing_world_falls_back(client, monkeypatch):
    """世界丢失（data/worlds 被清 / 世界被删）时兜底 douluo，不抛 404 阻断提取。"""
    _seed_session("s3", "gone123", "已删世界")
    _fake_extract_client(monkeypatch, {"李薇": {"age": "40", "background": "旧识"}})

    r = client.post("/api/extract-npc-profiles", json={
        "session_id": "s3", "npc_names": ["李薇"], "client_id": "u1",
    })
    assert r.status_code == 200, r.text
    assert r.json()["profiles"]["李薇"]["age"] == "40"
