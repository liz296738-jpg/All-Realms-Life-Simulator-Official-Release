""""后悔"（回合回退）功能端到端测试：new-game → act → undo → 状态/选项/回合记录还原。

用 TestClient + monkeypatch 把两次 LLM 调用（叙述流、结算 JSON）替换为固定返回，
不触网、不耗额度。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import main
from api import routes
from game import save_manager as sm
from game import session_manager


def _fake_call_turn(messages, api_key=None, max_tokens=2800):
    return {
        "narrative": "这是一段测试叙述，讲述主角此刻的处境。晨光穿过窗棂洒在大殿的青石地板上，远处传来弟子的晨练声。",
        "options": [{"label": "A", "text": "测试A"}, {"label": "B", "text": "测试B"}],
        "state_delta": {"resources": {"gold": 10}},
        "notes": ["一条测试笔记"],
        "event": "测试事件",
    }


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(sm, "ACTIVATIONS_PATH", tmp_path / "activations.json")
    session_manager._SESSIONS.clear()
    monkeypatch.setattr(routes, "_call_turn", _fake_call_turn)
    return TestClient(main.app)


def _delta_of(resp_text):
    """从 SSE 响应文本中取出 event: delta 的 data 对象。"""
    for block in resp_text.split("\n\n"):
        if block.startswith("event: delta"):
            for line in block.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
    return None


def _new_game(c, sid="t1"):
    resp = c.post("/api/new-game", json={
        "archive": {
            "character": {"name": "测试", "innate_soul_power": 5, "origin": "平民"},
            "start_location": "云溪镇",
        },
        "session_id": sid,  # session_id 在 body 顶层，服务端据此创建会话
    })
    assert resp.status_code == 200, resp.text
    return _delta_of(resp.text)


def _act(c, sid, action):
    resp = c.post("/api/act", json={"session_id": sid, "action": action})
    assert resp.status_code == 200, resp.text
    return _delta_of(resp.text)


def test_options_normalize_recommended():
    """结算选项规范化：AI 标了推荐则保留；没标则默认第一个；空则兜底单个。"""
    from api.routes import _normalize_options

    # AI 已标推荐 → 原样保留
    out = _normalize_options([
        {"label": "A", "text": "上前帮忙"},
        {"label": "B", "text": "转身离开", "recommended": True},
        {"label": "C", "text": "原地观察"},
    ])
    assert [o["recommended"] for o in out] == [False, True, False]

    # 没标 → 默认第一个为系统推荐
    out2 = _normalize_options([{"label": "A", "text": "x"}, {"label": "B", "text": "y"}])
    assert out2[0]["recommended"] is True and out2[1]["recommended"] is False

    # 空（自定义世界规则书偶发不产出选项）→ 兜底单个「继续前行」，仍带推荐
    out3 = _normalize_options([])
    assert out3 == [{"label": "A", "text": "继续前行", "recommended": True}]


def test_options_normalize_missing_label():
    """label 缺失按 ABCD 顺序补全。"""
    from api.routes import _normalize_options
    out = _normalize_options([{"text": "a"}, {"text": "b"}])
    assert [o["label"] for o in out] == ["A", "B"]


def test_new_game_has_no_undo(client):
    d = _new_game(client)
    assert d["can_undo"] is False  # 开场回合不可撤销
    r = client.post("/api/undo", json={"session_id": "t1"})
    assert r.status_code == 400


def test_undo_after_act_restores_previous_turn(client):
    d0 = _new_game(client)
    s0 = d0["state"]
    gold0 = s0["resources"]["gold"]
    turn0 = s0["meta"]["turn"]

    d1 = _act(client, "t1", "赚钱")
    assert d1["can_undo"] is True
    s1 = d1["state"]
    assert s1["meta"]["turn"] == turn0 + 1
    assert s1["resources"]["gold"] == gold0 + 10

    u = client.post("/api/undo", json={"session_id": "t1"})
    assert u.status_code == 200
    data = u.json()
    assert data["state"]["meta"]["turn"] == turn0
    assert data["state"]["resources"]["gold"] == gold0
    assert data["can_undo"] is False
    assert len(data["turns"]) == 1  # 只剩开场回合
    assert data["turns"][0]["choice"] is None

    # 已退无可退，再次后悔应 400
    r2 = client.post("/api/undo", json={"session_id": "t1"})
    assert r2.status_code == 400


def test_double_undo_back_to_opening(client):
    _new_game(client)
    _act(client, "t1", "第一次行动")
    d2 = _act(client, "t1", "第二次行动")
    assert d2["state"]["meta"]["turn"] == 3

    u1 = client.post("/api/undo", json={"session_id": "t1"}).json()
    assert u1["state"]["meta"]["turn"] == 2
    assert len(u1["turns"]) == 2

    u2 = client.post("/api/undo", json={"session_id": "t1"}).json()
    assert u2["state"]["meta"]["turn"] == 1
    assert len(u2["turns"]) == 1

    r = client.post("/api/undo", json={"session_id": "t1"})
    assert r.status_code == 400


def test_resume_returns_turns_and_can_undo(client):
    _new_game(client)
    _act(client, "t1", "行动")
    r = client.post("/api/resume", json={"session_id": "t1"})
    data = r.json()
    assert len(data["turns"]) == 2
    assert data["can_undo"] is True
    assert data["turns"][-1]["choice"] == "行动"
    # 规范化后带 recommended 标记：AI 未标 → 默认第一个为系统推荐
    assert data["turns"][-1]["options"] == [{"label": "A", "text": "测试A", "recommended": True},
                                            {"label": "B", "text": "测试B", "recommended": False}]


def test_cold_start_restores_turns_and_undo(client):
    _new_game(client)
    _act(client, "t1", "行动")
    # 模拟服务重启：清空内存会话，从磁盘恢复
    session_manager._SESSIONS.clear()
    r = client.post("/api/resume", json={"session_id": "t1"})
    data = r.json()
    assert len(data["turns"]) == 2
    assert data["can_undo"] is True  # undo_stack 也落盘了

    u = client.post("/api/undo", json={"session_id": "t1"}).json()
    assert len(u["turns"]) == 1


def test_cold_start_state_is_fresh(client):
    """每回合都落盘 state.json/history.jsonl，冷启动恢复不应拿到旧状态配新回合记录。"""
    d0 = _new_game(client)
    gold0 = d0["state"]["resources"]["gold"]
    turn0 = d0["state"]["meta"]["turn"]
    d1 = _act(client, "t1", "赚钱")
    assert d1["state"]["resources"]["gold"] == gold0 + 10

    session_manager._SESSIONS.clear()  # 模拟重启
    r = client.post("/api/resume", json={"session_id": "t1"})
    data = r.json()
    assert data["state"]["meta"]["turn"] == turn0 + 1
    assert data["state"]["resources"]["gold"] == gold0 + 10


def test_load_persists_state_to_disk(client):
    """读档要同步落盘 state.json，否则重启后冷启动仍读到读档前的旧状态。"""
    _new_game(client)
    _act(client, "t1", "行动")  # turn 2
    sp = client.post("/api/save", json={"session_id": "t1"}).json()["savepoint"]
    _act(client, "t1", "再行动")  # turn 3
    client.post("/api/load", json={"savepoint_id": sp["id"]})  # 回到 turn 2

    session_manager._SESSIONS.clear()
    data = client.post("/api/resume", json={"session_id": "t1"}).json()
    assert data["state"]["meta"]["turn"] == 2


def test_stream_error_yields_error_event(client, monkeypatch):
    """叙述流失败（如 key 无效）应下发 event: error，而不是被 Starlette 静默吞掉。"""
    def boom(messages, api_key=None, max_tokens=2800):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "_call_turn", boom)
    resp = client.post("/api/new-game", json={
        "archive": {"character": {"name": "E", "innate_soul_power": 5, "origin": "平民"}},
        "session_id": "e1",
    })
    assert resp.status_code == 200  # StreamingResponse 已回 200，错误靠 SSE 事件传达
    assert "event: error" in resp.text
    assert "event: done" not in resp.text  # 失败回合没有 done，前端会按中断处理

    # 失败回合不落账：回合记录为空
    data = client.post("/api/resume", json={"session_id": "e1"}).json()
    assert len(data["turns"]) == 0
    assert data["can_undo"] is False


def test_save_then_load_preserves_turns_resets_undo(client):
    _new_game(client)
    _act(client, "t1", "行动")
    sp = client.post("/api/save", json={"session_id": "t1"}).json()["savepoint"]
    r = client.post("/api/load", json={"savepoint_id": sp["id"]})
    data = r.json()
    assert len(data["turns"]) == 2
    assert data["can_undo"] is False  # 存档点恢复后撤销栈重新开始
    assert data["state"]["meta"]["turn"] == 2


def test_act_undo_act_again_roundtrip(client):
    """后悔后换个选项再走：快照栈应与新分支对齐。"""
    _new_game(client)
    _act(client, "t1", "行动A")
    d2 = _act(client, "t1", "行动B")
    assert d2["state"]["meta"]["turn"] == 3

    u = client.post("/api/undo", json={"session_id": "t1"}).json()
    assert u["state"]["meta"]["turn"] == 2
    assert u["options"][0]["text"] == "测试A"

    d3 = _act(client, "t1", "新行动")
    assert d3["state"]["meta"]["turn"] == 3

    # 再后悔应回到 turn 2，而不是 1（新的分支只叠了一层快照）
    u2 = client.post("/api/undo", json={"session_id": "t1"}).json()
    assert u2["state"]["meta"]["turn"] == 2
    assert len(u2["turns"]) == 2
