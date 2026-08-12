"""世界系统端点测试：列表可见性 / 权限 404 / 建世界流水线 / 删除。"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import main
from game import save_manager as sm
from game import world_builder
from game import worlds


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
    main._SESSIONS.clear()
    return TestClient(main.app)


def test_list_worlds_builtin_visible_to_all(client):
    r = client.get("/api/worlds?client_id=u1")
    assert r.status_code == 200
    data = r.json()
    assert any(w["id"] == "douluo" for w in data["builtin"])
    assert data["mine"] == []


def test_custom_world_visible_only_to_owner(client):
    worlds.save_custom_world(_spec("u1"))
    mine = client.get("/api/worlds?client_id=u1").json()["mine"]
    assert any(w["id"] == "abc123" for w in mine)
    other = client.get("/api/worlds?client_id=u2").json()["mine"]
    assert all(w["id"] != "abc123" for w in other)


def test_new_game_with_foreign_custom_world_404(client):
    worlds.save_custom_world(_spec("u1"))
    r = client.post("/api/new-game", json={
        "world_id": "abc123", "archive": {"character": {}}, "client_id": "u2",
    })
    assert r.status_code == 404


def test_new_game_with_own_custom_world_roundtrip(client, monkeypatch):
    worlds.save_custom_world(_spec("u1"))

    def fake_call_turn(messages, api_key=None, max_tokens=2800):
        return {
            "narrative": "自定义世界开场。晨光初现，阿灵站在山门前，望着远处连绵的群山，心中涌起无限期待。",
            "options": [],
            "state_delta": {"stats": {"修为": 1}},
            "notes": [],
            "event": "",
        }

    monkeypatch.setattr(main, "_call_turn", fake_call_turn)

    r = client.post("/api/new-game", json={
        "world_id": "abc123", "session_id": "cw1",
        "archive": {"character": {"name": "阿灵"}}, "client_id": "u1",
    })
    assert r.status_code == 200, r.text
    assert "event: text" in r.text
    assert '"world_id": "abc123"' in r.text

    r2 = client.post("/api/act", json={"session_id": "cw1", "action": "修炼", "client_id": "u1"})
    assert r2.status_code == 200, r2.text
    # 开场回合也结算 +1，act 再 +1 → 修为 3
    assert '"修为": 3' in r2.text  # 通用 stats 落账生效


def test_douluo_default_when_no_world_id(client, monkeypatch):
    def fake_call_turn(messages, api_key=None, max_tokens=2800):
        return {
            "narrative": "魂兽大陆开场。晨光穿过云层洒在云溪镇的青石路上，远处武魂殿的钟声悠悠回荡在山谷之间。",
            "options": [],
            "state_delta": {},
            "notes": [],
            "event": "",
        }

    monkeypatch.setattr(main, "_call_turn", fake_call_turn)
    r = client.post("/api/new-game", json={
        "session_id": "dl1", "archive": {"character": {"name": "云昊", "innate_soul_power": 5}},
    })
    assert r.status_code == 200
    assert '"world_id": "douluo"' in r.text


def test_delete_custom_world_owner_only(client):
    worlds.save_custom_world(_spec("u1"))
    r = client.post("/api/worlds/delete", json={"world_id": "abc123", "client_id": "u2"})
    assert r.status_code == 404
    r2 = client.post("/api/worlds/delete", json={"world_id": "abc123", "client_id": "u1"})
    assert r2.status_code == 200
    assert worlds.get_world("abc123") is None


def test_delete_builtin_rejected(client):
    r = client.post("/api/worlds/delete", json={"world_id": "douluo", "client_id": "u1"})
    assert r.status_code == 400


def test_build_world_endpoint(client, monkeypatch):
    _fake_build_openai(monkeypatch, _spec("u1"))
    r = client.post("/api/worlds/build",
                    files={"file": ("novel.txt", "第一章 开始\n正文内容。".encode("utf-8"),
                                    "text/plain")},
                    data={"api_key": "sk-test", "client_id": "u1"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "我的世界"
    assert data["owner"] == "u1"
    assert data["id"] != "abc123"  # 重新生成独立 id


def test_build_world_requires_api_key(client):
    r = client.post("/api/worlds/build",
                    files={"file": ("novel.txt", b"abc", "text/plain")},
                    data={"client_id": "u1"})
    assert r.status_code == 400
    assert "API Key" in r.json()["detail"]


def test_build_world_rejects_doc(client):
    r = client.post("/api/worlds/build",
                    files={"file": ("old.doc", b"abc", "application/msword")},
                    data={"api_key": "sk-test", "client_id": "u1"})
    assert r.status_code == 400


def test_build_world_oversize_rejected(client):
    big = b"a" * (30 * 1024 * 1024 + 1)
    r = client.post("/api/worlds/build",
                    files={"file": ("big.txt", big, "text/plain")},
                    data={"api_key": "sk", "client_id": "big1"})
    assert r.status_code == 400
    assert "30MB" in r.json()["detail"]


def _fake_build_openai(monkeypatch, payload):
    good = json.dumps(payload, ensure_ascii=False)

    class _Completions:
        def create(self, **kw):
            msg = type("M", (), {"content": good})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    class _FakeOpenAI:
        def __init__(self, *a, **kw):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    monkeypatch.setattr(world_builder, "OpenAI", _FakeOpenAI)


def test_build_world_rate_limit(client, monkeypatch):
    # 5 次/小时；第 6 次触发 429
    _fake_build_openai(monkeypatch, _spec("u1"))
    for _ in range(5):
        r = client.post("/api/worlds/build",
                        files={"file": ("n.txt", b"abc", "text/plain")},
                        data={"api_key": "sk", "client_id": "rl1"})
        assert r.status_code == 200
    r6 = client.post("/api/worlds/build",
                     files={"file": ("n.txt", b"abc", "text/plain")},
                     data={"api_key": "sk", "client_id": "rl1"})
    assert r6.status_code == 429
