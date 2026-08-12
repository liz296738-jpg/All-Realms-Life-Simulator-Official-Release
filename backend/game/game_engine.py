"""状态应用引擎：把清洗后的 delta 落账，并驱动被动机制。"""
from __future__ import annotations

import re
from typing import Any

from .state_schema import template_of, validate_delta


def _guess_season(date: str) -> str:
    s = date or ""
    # 关键词日期（如「入冬后」「春日」）：按出现的中文季节词直接判定
    for kw, season in (("春", "春"), ("夏", "夏"), ("秋", "秋"), ("冬", "冬")):
        if kw in s:
            return season
    m = re.search(r"(\d{1,2})月", s)
    if m:
        mo = int(m.group(1))
        if mo in (12, 1, 2):
            return "冬"
        if 3 <= mo <= 5:
            return "春"
        if 6 <= mo <= 8:
            return "夏"
        return "秋"
    return "春"


def apply_delta(state: dict, raw_delta: dict, world=None) -> dict:
    """校验 → 落账 → 好感衰减 → 季节 → 回合自增。就地修改 state。

    world 决定等级字段名与好感钳制区间；缺省按魂兽大陆处理（内部 id 为 douluo，向后兼容）。
    """
    t = template_of(world)
    delta = validate_delta(raw_delta, state, world)

    # 资源：通用 dict 增量（validate_delta 已把旧键 gold/silver/copper 并入）
    for name, inc in delta.get("resources", {}).items():
        state["resources"][name] = state["resources"].get(name, 0) + inc
    # 属性：通用 stats 增量
    for name, inc in delta.get("stats", {}).items():
        state.setdefault("stats", {})[name] = state["stats"].get(name, 0) + inc

    # 等级字段（魂兽大陆 soul_level）：validate_delta 输出已是钳制后的绝对目标
    lf = t.get("level_field")
    if lf and lf in state["character"] and lf in delta:
        state["character"][lf] = delta[lf]

    # 先推进月份，再标记本回合见过的人，避免刚见面的角色被误判为长期未见面
    md = delta.get("month_delta", 0)
    if md > 0:
        state["meta"]["month"] += md

    touched = set()
    for name, val in delta.get("affection", {}).items():
        state.setdefault("affection", {})[name] = val
        state.setdefault("affection_last_seen", {})[name] = state["meta"]["month"]
        touched.add(name)

    # 势力声望：通用 dict 增量（validate_delta 已把未知势力剔除并钳制）
    for name, inc in delta.get("faction", {}).items():
        state["faction"][name] = state["faction"].get(name, 0) + inc

    if delta.get("soul_ring_add"):
        state.setdefault("soul_rings", []).append(delta["soul_ring_add"])

    for item in delta.get("inventory_add", []):
        if item not in state["inventory"]:
            state["inventory"].append(item)
    for item in delta.get("inventory_remove", []):
        if item in state["inventory"]:
            state["inventory"].remove(item)
    for note in delta.get("notes_add", []):
        if note not in state["notes"]:
            state["notes"].append(note)

    # npcs：增量合并（AI 只能增/改，不能删；删除由前端手动操作）
    for name, profile in delta.get("npcs", {}).items():
        existing = state.setdefault("npcs", {}).get(name, {})
        merged = {**existing, **profile}
        state["npcs"][name] = merged

    state["location"]["place"] = delta.get("location", state["location"]["place"])
    state["location"]["date"] = delta.get("date", state["location"]["date"])
    state["location"]["season"] = _guess_season(state["location"]["date"])

    # 好感衰减：本月推进后，未在本回合见面的角色按未见面月数衰减
    if md > 0:
        aff = state.setdefault("affection", {})
        last_seen = state.setdefault("affection_last_seen", {})
        for name in aff:
            if name in touched:
                continue
            last = last_seen.get(name, 0)
            gap = state["meta"]["month"] - last
            if gap >= 1:
                aff[name] = max(t.get("affection_min", -100), aff[name] - min(gap, 3))
                last_seen[name] = state["meta"]["month"]

    state["meta"]["turn"] += 1
    return state
