""""订阅门禁（微信收款 · 服务器端码池）端到端测试。

码池：每个码对应一年中的一个日子（MM-DD，每年循环复用），从对应日起 SUB_DAYS
天内任意一天都能激活；订阅到期固定为"对应日 + SUB_DAYS 天"。测试用 fixture
在临时目录写一份码池（今天-35 ~ 今天+60，每日子一个确定性测试码），再验证
窗口内激活 / 窗口外拒绝 / 无效码 / 循环复用 / 闰日补全 / 试玩门禁 / 镜像持久化等行为。

TestClient + monkeypatch 把两次 LLM 调用替换为固定返回，不触网、不耗额度。
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import main
from api import routes
from auth import subscription
from game import activation_codes
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


# 测试码池范围：今天-35 ~ 今天+60，每日期一个确定性测试码（覆盖 30 天窗口边界）
_RANGE_LO, _RANGE_HI = -35, 60


def _seed_code(days: int) -> str:
    """为"今天 + days 天"生成确定性的测试码（仅测试用，与线上生成器无关）。"""
    return f"TEST-{days:04d}-{abs(days * 7) % 10}{abs(days * 13) % 10}{abs(days * 31) % 10}"


def _seed_codes() -> dict:
    return {
        (date.today() + timedelta(days=i)).strftime("%m-%d"): _seed_code(i)
        for i in range(_RANGE_LO, _RANGE_HI + 1)
    }


def _code(days: int) -> str:
    """码池中"今天 + days 天"那个日期绑定的码。"""
    return _seed_code(days)


def _expiry_end(days: int) -> str:
    """_code(days) 对应到期日 23:59:59 的 iso（对应日 + SUB_DAYS，与 _verify_code 一致）。"""
    expiry = date.today() + timedelta(days=days) + timedelta(days=subscription.SUB_DAYS)
    return (datetime.combine(expiry, datetime.min.time()) + timedelta(days=1) - timedelta(seconds=1)).isoformat()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(sm, "ACTIVATIONS_PATH", tmp_path / "activations.json")
    monkeypatch.setattr(activation_codes, "CODES_PATH", tmp_path / "activation_codes.json")
    activation_codes.save_codes(_seed_codes())
    session_manager._SESSIONS.clear()
    monkeypatch.setattr(routes, "_call_turn", _fake_call_turn)
    return TestClient(main.app)


def _delta_of(resp_text):
    for block in resp_text.split("\n\n"):
        if block.startswith("event: delta"):
            for line in block.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
    return None


def _new_game(c, sid="e1", cid="dev", code=None):
    body = {
        "archive": {"character": {"name": "门禁", "innate_soul_power": 5, "origin": "平民"}},
        "session_id": sid, "client_id": cid,
    }
    if code:
        body["code"] = code
    resp = c.post("/api/new-game", json=body)
    assert resp.status_code == 200, resp.text
    return _delta_of(resp.text)


def _act(c, sid, cid="dev", code=None):
    body = {"session_id": sid, "action": "行动", "client_id": cid}
    if code:
        body["code"] = code
    resp = c.post("/api/act", json=body)
    assert resp.status_code == 200, resp.text
    return _delta_of(resp.text)


# ── 码池校验单元 ─────────────────────────────────────
def test_registry_roundtrip_and_verify_today(client):
    """码池可查：今天的码 → 今天校验通过，到期 = 今天 + SUB_DAYS 23:59:59。"""
    c = _code(0)
    assert activation_codes.find_day_by_code(c) == date.today().strftime("%m-%d")
    ok, until, err = subscription._verify_code(c)
    assert ok is True
    assert until == _expiry_end(0)
    assert err is None


def test_verify_is_case_and_dash_insensitive(client):
    c = _code(0).lower()
    messy = f"{c[:4]} -{c[4:8]} {c[8:]}\t"
    ok, until, _ = subscription._verify_code(messy)
    assert ok is True
    assert until == _expiry_end(0)


def test_verify_invalid_code(client):
    ok, _, err = subscription._verify_code("XXXX-1234-AAAA")
    assert ok is False
    assert err and "无效" in err


def test_verify_future_code_rejected_today(client):
    ok, _, err = subscription._verify_code(_code(1))   # 明天的码今天不能激活
    assert ok is False
    assert err and "激活码错误或已过期" in err


def test_wrong_date_error_does_not_leak_code_date(client):
    """非当天激活的提示不得泄露码对应的日期（隐私）：只说"码不对"。"""
    ok, _, err = subscription._verify_code(_code(1))   # 明天的码今天不能激活
    assert ok is False
    assert err
    assert not re.search(r"\d+月\d+号", err)   # 不告诉玩家这个码是哪天的
    assert "今天" not in err


def test_today_follows_beijing_not_utc(monkeypatch, tmp_path):
    """服务器跑 UTC 时，北京 0:00-8:00 已进入新的一天：'今天'必须按北京墙钟算。

    同一时刻 UTC 仍停在 8/10、北京已是 8/11 —— 8/11 的码应能正常激活（今天码），
    8/10 的码在 30 天窗口内也应能激活（昨天码）——旧逻辑只有今天码有效。
    31 天前的码在窗口外应被拒。
    """
    monkeypatch.setattr(sm, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(sm, "ACTIVATIONS_PATH", tmp_path / "activations.json")
    monkeypatch.setattr(activation_codes, "CODES_PATH", tmp_path / "activation_codes.json")
    activation_codes.save_codes({"07-05": "CN-0505-OLD", "08-10": "CN-1010-CODE", "08-11": "CN-1111-CODE"})
    # 服务器系统时刻（UTC）= 2026-08-10 16:30；同一时刻北京 = 2026-08-11 00:30
    bj_now = datetime(2026, 8, 11, 0, 30)
    monkeypatch.setattr(subscription, "_cn_now", lambda: bj_now)

    # 今天的码：窗口从今天开始 → 激活成功
    ok, until, _ = subscription._verify_code("CN-1111-CODE")
    assert ok is True
    assert until is not None
    exp_day = (datetime(2026, 8, 11) + timedelta(days=subscription.SUB_DAYS)).strftime("%Y-%m-%d")
    assert until.startswith(exp_day)   # 到期日锚定码日期 08-11 + 30 = 09-10

    # 昨天的码：仍在 30 天窗口内 → 激活成功，到期日锚定码日期（08-10 + 30 = 09-09）
    ok2, until2, _ = subscription._verify_code("CN-1010-CODE")
    assert ok2 is True
    assert until2 is not None
    exp_day2 = (datetime(2026, 8, 10) + timedelta(days=subscription.SUB_DAYS)).strftime("%Y-%m-%d")
    assert until2.startswith(exp_day2)

    # 31 天前的码（07-05）：在 30 天窗口之外 → 拒绝
    ok3, _, _ = subscription._verify_code("CN-0505-OLD")
    assert ok3 is False


def test_verify_code_outside_window_rejected(client):
    ok, _, err = subscription._verify_code(_code(-31))  # 31 天前的码，在 30 天窗口之外
    assert ok is False
    assert err


def test_verify_past_code_within_window_succeeds(client):
    """昨天的码在 30 天窗口内 → 激活成功，到期锚定码日期而非今天。"""
    ok, until, err = subscription._verify_code(_code(-1))
    assert ok is True
    assert err is None
    # 到期 = 码日期 + 30，即 (today-1) + 30 = today+29
    assert until == _expiry_end(-1)


def test_verify_edge_of_window(client):
    """码日期 + 30 天（窗口最后一天，含）仍可激活；码日期 + 31 天被拒。"""
    ok_last, _, _ = subscription._verify_code(_code(-30))  # 30 天前 = 窗口最后一天
    assert ok_last is True
    ok_expired, _, _ = subscription._verify_code(_code(-31))  # 31 天前 = 刚好过期
    assert ok_expired is False


def test_activate_past_code_in_window_succeeds(client):
    """昨天的码通过 /api/activate 激活成功，paid_until 锚定码日期。"""
    r = client.post("/api/activate", json={"code": _code(-1), "client_id": "dev"})
    assert r.status_code == 200
    d = r.json()
    assert d["paid"] is True
    assert d["paid_until"] == _expiry_end(-1)


def test_new_device_with_past_code_in_window(client):
    """浏览器清空 / 新设备：在窗口期内带着旧码也能玩。"""
    # dev 激活码后不写 paid_until（模拟：只用码传递，不靠镜像）
    r = client.post("/api/activate", json={"code": _code(0), "client_id": "dev"})
    assert r.status_code == 200
    # 另一台设备 new_device 在窗口内带着同一个码 → 直接放行
    delta = _new_game(client, sid="s2", cid="new_device", code=_code(0))
    assert delta is not None


def test_code_recycles_yearly(client):
    """同一个码每年对应同一天：任意年份的同月同日都查回同一个码（无需重新生成）。

    锚定闰年 2028（含所有日期，含 02-29），避免今天恰逢闰日时跨年构造失败。
    """
    c = _code(0)
    assert activation_codes.find_day_by_code(c) == date.today().strftime("%m-%d")
    same_day_leap_year = date(2028, date.today().month, date.today().day)
    assert activation_codes.find_code_for_date(same_day_leap_year) == c


def test_full_pool_covers_every_day_including_leap_day(monkeypatch, tmp_path):
    """补齐码池 → 覆盖一年 366 天（含闰日 02-29），且幂等不覆盖已有码。"""
    monkeypatch.setattr(activation_codes, "CODES_PATH", tmp_path / "activation_codes.json")
    assert activation_codes.ensure_full_pool() == 366
    mapping = activation_codes.load_codes()
    assert len(mapping) == 366
    assert "02-29" in mapping
    assert "01-01" in mapping and "12-31" in mapping
    # 幂等：再跑一次不新增、不改动
    assert activation_codes.ensure_full_pool() == 0
    assert activation_codes.load_codes() == mapping


# ── 激活端点 ─────────────────────────────────────────
def test_activate_sets_paid_until(client):
    d = client.post("/api/activate", json={"code": _code(0), "client_id": "dev"}).json()
    assert d["paid"] is True
    assert d["paid_until"] == _expiry_end(0)

    ent = client.post("/api/entitlement", json={"client_id": "dev"}).json()
    assert ent["paid"] is True
    assert ent["paid_until"] == d["paid_until"]
    assert ent["trial_limit"] == 5


def test_activate_normalizes_input(client):
    """小写 / 带连字符与空白的码也能识别（前端复制的格式可能五花八门）。"""
    c = _code(0).lower()
    messy = f"{c[:4]} -{c[4:8]} {c[8:]}\t"
    d = client.post("/api/activate", json={"code": messy, "client_id": "dev"}).json()
    assert d["paid"] is True
    assert d["paid_until"] == _expiry_end(0)


def test_activate_requires_client_id(client):
    r = client.post("/api/activate", json={"code": _code(0)})
    assert r.status_code == 400
    assert "设备标识" in r.json()["detail"]


def test_activate_invalid_code_400(client):
    r = client.post("/api/activate", json={"code": "XXXX-1234-AAAA", "client_id": "dev"})
    assert r.status_code == 400
    assert "无效" in r.json()["detail"]


def test_activate_future_code_rejected_400(client):
    r = client.post("/api/activate", json={"code": _code(1), "client_id": "dev"})
    assert r.status_code == 400
    assert "激活码错误或已过期" in r.json()["detail"]
    assert not re.search(r"\d+月\d+号", r.json()["detail"])   # 不泄露码的日期


def test_activate_code_outside_window_rejected_400(client):
    r = client.post("/api/activate", json={"code": _code(-31), "client_id": "dev"})
    assert r.status_code == 400


# ── 试玩门禁 / 订阅行为 ─────────────────────────────
def test_free_trial_counts_turns_and_gates(client, monkeypatch):
    monkeypatch.setattr(subscription, "FREE_TRIAL_TURNS", 2)
    _new_game(client)      # 试玩 1/2
    _act(client, "e1")     # 试玩 2/2 → 已用尽
    r = client.post("/api/act", json={"session_id": "e1", "action": "再来", "client_id": "dev"})
    assert r.status_code == 403
    assert "免费试玩" in r.json()["detail"]

    # 激活今天的码后立即可继续
    client.post("/api/activate", json={"code": _code(0), "client_id": "dev"})
    r2 = client.post("/api/act", json={"session_id": "e1", "action": "订阅后行动", "client_id": "dev"})
    assert r2.status_code == 200
    assert _delta_of(r2.text)["state"]["meta"]["turn"] == 3


def test_new_game_blocked_when_no_trial(client, monkeypatch):
    monkeypatch.setattr(subscription, "FREE_TRIAL_TURNS", 0)
    r = client.post("/api/new-game", json={
        "archive": {"character": {"name": "X", "innate_soul_power": 5, "origin": "平民"}},
        "session_id": "z1", "client_id": "dev",
    })
    assert r.status_code == 403

    # 激活今天的码后放行
    client.post("/api/activate", json={"code": _code(0), "client_id": "dev"})
    r2 = client.post("/api/new-game", json={
        "archive": {"character": {"name": "X", "innate_soul_power": 5, "origin": "平民"}},
        "session_id": "z1", "client_id": "dev",
    })
    assert r2.status_code == 200


def test_paid_user_exempt_from_trial(client, monkeypatch):
    monkeypatch.setattr(subscription, "FREE_TRIAL_TURNS", 1)
    client.post("/api/activate", json={"code": _code(0), "client_id": "dev"})
    _new_game(client)
    _act(client, "e1")   # 超过试玩上限仍放行（已激活）
    _act(client, "e1")
    assert client.post("/api/entitlement", json={"client_id": "dev"}).json()["paid"] is True


def test_code_works_on_any_device_same_day(client, monkeypatch):
    """码对应日当天，任意设备带着同一码直接可用；不带码无试玩 → 403。"""
    monkeypatch.setattr(subscription, "FREE_TRIAL_TURNS", 0)
    c = _code(0)
    client.post("/api/activate", json={"code": c, "client_id": "dev1"})
    # dev2 从未激活，但请求带码（今天的码）→ 放行
    _new_game(client, sid="d2", cid="dev2", code=c)
    # dev2 不带码、无试玩 → 403
    r = client.post("/api/new-game", json={
        "archive": {"character": {"name": "Z", "innate_soul_power": 5, "origin": "平民"}},
        "session_id": "d2b", "client_id": "dev2",
    })
    assert r.status_code == 403


def test_code_passed_in_act_body_skips_gate(client, monkeypatch):
    """带码的 act 请求直接放行，且不消耗试玩次数。"""
    monkeypatch.setattr(subscription, "FREE_TRIAL_TURNS", 1)
    c = _code(0)
    _new_game(client, sid="g1", cid="dev")   # 消耗 1 次试玩 → 已用尽
    r = client.post("/api/act", json={"session_id": "g1", "action": "带码行动", "client_id": "dev", "code": c})
    assert r.status_code == 200
    assert _delta_of(r.text)["state"]["meta"]["turn"] == 2
    ent = client.post("/api/entitlement", json={"client_id": "dev", "code": c}).json()
    assert ent["paid"] is True
    assert ent["trial_used"] == 1  # 已订阅不计试玩


def test_entitlement_verifies_stored_code(client):
    """查询接口带 code 时按码池校验；不带 code 时读登记表镜像（激活后已写盘）。"""
    c = _code(0)
    d = client.post("/api/activate", json={"code": c, "client_id": "dev"}).json()
    ent = client.post("/api/entitlement", json={"client_id": "dev"}).json()
    assert ent["paid"] is True
    assert ent["paid_until"] == d["paid_until"]
    # 同一天另一设备带同一码查询 → 同样判定已订阅
    ent2 = client.post("/api/entitlement", json={"client_id": "other", "code": c}).json()
    assert ent2["paid"] is True


def test_activate_does_not_downgrade_existing_subscription(client):
    """已订阅更长期限（镜像）后当天再激活今天的码 → 保留更长的到期日，不降级。"""
    future = (datetime.now() + timedelta(days=40)).isoformat()
    sm.ACTIVATIONS_PATH.write_text(json.dumps({"dev": {"paid_until": future}}), encoding="utf-8")
    d = client.post("/api/activate", json={"code": _code(0), "client_id": "dev"}).json()
    assert d["paid_until"] == future


def test_legacy_paid_record_still_honored(client):
    """登记表（只有 paid_until）兼容：仍视为已订阅。"""
    future = (datetime.now() + timedelta(days=20)).isoformat()
    sm.ACTIVATIONS_PATH.write_text(json.dumps({"dev1": {"paid_until": future}}), encoding="utf-8")
    ent = client.post("/api/entitlement", json={"client_id": "dev1"}).json()
    assert ent["paid"] is True
    assert ent["paid_until"] == future


def test_malformed_record_does_not_500(client):
    """activations.json 里 paid_until 结构异常时按未激活处理，不 500。"""
    sm.ACTIVATIONS_PATH.write_text(json.dumps({"dev": {"paid_until": "x"}}), encoding="utf-8")
    ent = client.post("/api/entitlement", json={"client_id": "dev"}).json()
    assert ent["paid"] is False
    r = client.post("/api/new-game", json={
        "archive": {"character": {"name": "X", "innate_soul_power": 5, "origin": "平民"}},
        "session_id": "m1", "client_id": "dev",
    })
    assert r.status_code == 200


def test_activation_persists_across_restart(client):
    """激活成功把 paid_until 镜像写盘，服务重启（清内存）后本机仍视为已订阅。"""
    client.post("/api/activate", json={"code": _code(0), "client_id": "dev"})
    session_manager._SESSIONS.clear()
    ent = client.post("/api/entitlement", json={"client_id": "dev"}).json()
    assert ent["paid"] is True


def test_failed_turn_does_not_consume_trial(client, monkeypatch):
    """回合生成失败（error 事件）不记试玩次数。"""
    monkeypatch.setattr(subscription, "FREE_TRIAL_TURNS", 1)

    def boom(messages, api_key=None, max_tokens=2800):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "_call_turn", boom)
    r = client.post("/api/new-game", json={
        "archive": {"character": {"name": "X", "innate_soul_power": 5, "origin": "平民"}},
        "session_id": "f1", "client_id": "dev",
    })
    assert r.status_code == 200
    assert "event: error" in r.text
    ent = client.post("/api/entitlement", json={"client_id": "dev"}).json()
    assert ent["trial_used"] == 0  # 失败回合不扣次数
