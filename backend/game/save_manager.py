"""会话持久化与存档点。状态 + 对白历史 落盘为 JSON。"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
SAVES_DIR = BASE_DIR / "data" / "saves"

# 会话/存档点 id 只允许字母数字与 - _ .，防止 ../ 之类路径穿越。
# 会话 id 由 uuid.hex[:12] 或测试短名（如 cwsm）生成；存档点 id = 会话 id + 时间戳。
_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SAFE_SAVEPOINT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _assert_safe_id(value, pattern: re.Pattern, kind: str) -> None:
    """id 不匹配安全白名单即拒绝——防用户提供的 id 拼进文件系统路径穿越。"""
    if not isinstance(value, str) or not pattern.match(value):
        raise ValueError(f"非法{kind}: {value!r}")
# 订阅/免费试玩登记表：按 client_id（浏览器 localStorage）记录 paid_until 与 trial_used。
# 独立于存档目录，但同一 data/ 下；测试用 monkeypatch 重定向此路径。
ACTIVATIONS_PATH = BASE_DIR / "data" / "activations.json"


def load_activations() -> dict:
    """读取订阅登记表。文件不存在或损坏时返回空表（按未激活处理）。"""
    if ACTIVATIONS_PATH.exists():
        try:
            return json.loads(ACTIVATIONS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_activations(acts: dict) -> None:
    """写回订阅登记表（原子写：先写临时文件再 os.replace 替换）。

    登记表承载订阅到期日与已用码，若中断写进半截 JSON，load_activations 会
    把它当空表——所有订阅被打回未激活、已用码重新可兑。原子替换保证任何时刻
    读者要么看到旧表要么看到完整新表，不会读到半截内容。
    """
    ACTIVATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ACTIVATIONS_PATH.with_name(ACTIVATIONS_PATH.name + ".tmp")
    tmp.write_text(
        json.dumps(acts, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ACTIVATIONS_PATH)


def session_dir(session_id: str) -> Path:
    _assert_safe_id(session_id, _SAFE_SESSION_ID, "会话 id")
    d = SAVES_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_state(session_id: str, state: dict, history: list[str]) -> Path:
    d = session_dir(session_id)
    (d / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "history.jsonl").write_text(
        "\n".join(history) + ("\n" if history else ""), encoding="utf-8")
    return d


def load_state(session_id: str) -> tuple[dict, list[str]]:
    d = session_dir(session_id)
    state = json.loads((d / "state.json").read_text(encoding="utf-8"))
    raw = (d / "history.jsonl").read_text(encoding="utf-8") if (d / "history.jsonl").exists() else ""
    history = [l.strip() for l in raw.splitlines() if l.strip()]
    return state, history


def save_turns(session_id: str, turns: list, undo_stack: list) -> Path:
    """回合记录 + 撤销栈 落盘（turns 供回滚/续玩回放，undo_stack 供"后悔"回退）。"""
    d = session_dir(session_id)
    (d / "turns.json").write_text(
        json.dumps(turns, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "undo.json").write_text(
        json.dumps(undo_stack, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def load_turns(session_id: str) -> tuple[list, list]:
    d = session_dir(session_id)
    tp, up = d / "turns.json", d / "undo.json"
    turns = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else []
    undo = json.loads(up.read_text(encoding="utf-8")) if up.exists() else []
    return turns, undo


def create_savepoint(session_id: str, state: dict, history: list[str],
                     turns: list | None = None) -> dict:
    d = session_dir(session_id) / "savepoints"
    d.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    sp_id = f"{session_id}-{ts}"
    payload: dict = {"state": state, "history": history}
    if turns is not None:
        payload["turns"] = turns
    (d / f"{sp_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return {
        "id": sp_id, "time": ts, "turn": state["meta"]["turn"],
        "place": state["location"]["place"], "name": state["character"]["name"],
        "level": state["character"].get(state["meta"].get("level_field", "soul_level"), 0),
        "level_field": state["meta"].get("level_field", "soul_level"),
    }


def list_sessions(client_id: str | None = None) -> list[dict]:
    out = []
    if SAVES_DIR.exists():
        for d in SAVES_DIR.iterdir():
            p = d / "state.json"
            if d.is_dir() and p.exists():
                st = json.loads(p.read_text(encoding="utf-8"))
                # 按 client_id 隔离：已标记归属的存档只对拥有者可见
                owner = st.get("meta", {}).get("client_id", "")
                if client_id and owner and owner != client_id:
                    continue
                lf = st.get("meta", {}).get("level_field", "soul_level")
                out.append({
                    "session_id": d.name,
                    "name": st["character"]["name"],
                    "level": st["character"].get(lf, 0),
                    "level_field": lf,
                    "turn": st["meta"]["turn"],
                    "place": st["location"]["place"],
                    "date": st["location"]["date"],
                    "world_id": st["meta"].get("world_id", "douluo"),
                    "world_name": st["meta"].get("world_name", "魂兽大陆"),
                })
    return sorted(out, key=lambda x: x["session_id"], reverse=True)


def check_owner(session_id: str, client_id: str | None) -> None:
    """验证存档归属：已标记 owner 的会话只允许拥有者操作。client_id 为空则放行（兼容旧调用）。"""
    if not client_id:
        return
    try:
        st = json.loads((session_dir(session_id) / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    owner = st.get("meta", {}).get("client_id", "")
    if owner and owner != client_id:
        raise PermissionError("无权操作此存档")


def load_savepoint(savepoint_id: str) -> dict:
    _assert_safe_id(savepoint_id, _SAFE_SAVEPOINT_ID, "存档点 id")
    if SAVES_DIR.exists():
        for d in SAVES_DIR.iterdir():
            p = d / "savepoints" / f"{savepoint_id}.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"存档不存在: {savepoint_id}")
