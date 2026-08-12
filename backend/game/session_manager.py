"""会话内存缓存 — TTL 过期回收，防内存泄漏。

每个会话在内存中保留最多 SESSION_TTL 秒（默认 2 小时）；超时自动驱逐。
所有会话数据在每次回合结束时已落盘（state.json / history.jsonl / turns.json），
驱逐时不需要额外写盘——直接 pop 即可安全释放内存。
"""
from __future__ import annotations

import time

from fastapi import HTTPException

from game import save_manager as sm

SESSION_TTL = 7200  # 会话内存存活时间（秒）：2 小时

# {session_id: {"data": session_dict, "last_active": float}}
_SESSIONS: dict[str, dict] = {}


def _cleanup_stale() -> None:
    """驱逐超时会话。O(n) 遍历——会话数通常 < 1000，性能可接受。"""
    now = time.time()
    stale = [sid for sid, entry in _SESSIONS.items()
             if now - entry.get("last_active", 0) > SESSION_TTL]
    for sid in stale:
        _SESSIONS.pop(sid, None)


def _new_session(session_id: str, state: dict, history: list, archive: dict,
                 turns: list | None = None, undo_stack: list | None = None) -> dict:
    """构造会话对象，写入内存缓存，触发过期清理。

    返回的 dict 就是调用方需要的完整会话对象——调用方无需再手动塞 _SESSIONS。
    """
    _cleanup_stale()
    sess = {
        "state": state,
        "history": list(history),
        "archive": archive,
        "last_options": state.get("meta", {}).get("last_options") or [],
        "turns": turns if turns is not None else [],
        "undo_stack": undo_stack if undo_stack is not None else [],
    }
    _SESSIONS[session_id] = {"data": sess, "last_active": time.time()}
    return sess


def _load_session(session_id: str) -> dict:
    """从内存缓存或磁盘加载会话，刷新活跃时间，触发过期清理。"""
    _cleanup_stale()
    entry = _SESSIONS.get(session_id)
    if entry is not None:
        entry["last_active"] = time.time()
        return entry["data"]
    # 冷启动：从磁盘恢复
    try:
        state, history = sm.load_state(session_id)
        turns, undo_stack = sm.load_turns(session_id)
    except Exception:
        raise HTTPException(404, "会话不存在，请检查存档列表")
    sess = {
        "state": state,
        "history": list(history),
        "archive": {},
        "last_options": state.get("meta", {}).get("last_options") or [],
        "turns": turns if turns is not None else [],
        "undo_stack": undo_stack if undo_stack is not None else [],
    }
    _SESSIONS[session_id] = {"data": sess, "last_active": time.time()}
    return sess


def remove_session(session_id: str) -> None:
    """从内存缓存中移除会话（用于删除存档等场景）。"""
    _SESSIONS.pop(session_id, None)
