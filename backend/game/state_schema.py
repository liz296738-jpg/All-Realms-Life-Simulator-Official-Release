"""权威状态模型 + 变动单(delta)校验钳制。后端是唯一账本。

混合通用化（见 docs/superpowers/specs/2026-08-10-multi-world-platform-design.md）：
- 保留魂兽大陆字段路径（character.soul_level / resources.gold / soul_rings），
  同时新增通用 stats 字典，供自建世界使用。
- 默认世界 = 魂兽大陆（内部 id 为 douluo）：default_state(archive) /
  validate_delta(delta, state) / apply_delta(state, delta) 不带 world 时按
  魂兽大陆处理，旧调用与旧存档零改动。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import worlds


def template_of(world) -> dict:
    """把 world 参数解析成 state_template（world 可为 dict / id / None）。"""
    if isinstance(world, dict):
        return world.get("state_template", {})
    if isinstance(world, str):
        t = worlds.get_world_template(world)
        if t:
            return t
    t = worlds.get_world_template("douluo")
    return t or {}


def _clamp_int(value, floor=None, ceil=None) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 0
    if floor is not None and v < floor:
        v = floor
    if ceil is not None and v > ceil:
        v = ceil
    return v


def _coerce_scalar(val, default):
    """按默认值类型把创建档案的字段值规整成一致类型。"""
    if val is None:
        return default
    if isinstance(default, bool):
        return bool(val)
    if isinstance(default, int):
        return _clamp_int(val, floor=0)
    if isinstance(default, list):
        return list(val) if isinstance(val, list) else [val]
    return str(val)


def _character_field(ch: dict, key: str, spec) -> Any:
    """单个 character 字段：标量取档案值，dict 规格按 init/floor_from 求值。"""
    if isinstance(spec, dict):
        val = int(spec.get("init", 0))
        ff = spec.get("floor_from")
        if ff and ch.get(ff) is not None:
            try:
                val = int(ch[ff])
            except (TypeError, ValueError):
                pass
        return val
    return _coerce_scalar(ch.get(key), spec)


def _resource_init(spec: dict, archive: dict) -> int:
    """初始资源值：from_archive 优先（档案显式指定，character 内或档案顶层均可），
    其次 origin_defaults 映射，最后 init 兜底。"""
    init = int(spec.get("init", 0))
    ch = archive.get("character", {})
    fa = spec.get("from_archive")
    if fa:
        val = ch.get(fa) if ch.get(fa) is not None else archive.get(fa)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                return init
    of = spec.get("origin_field")
    if of and ch.get(of) in spec.get("origin_defaults", {}):
        return int(spec["origin_defaults"][ch[of]])
    return init


def default_state(archive: dict[str, Any], world=None) -> dict[str, Any]:
    """根据创建档案卡 + 世界规格生成初始权威状态。"""
    t = template_of(world)
    ch = archive.get("character", {})

    character = {}
    for key, spec in t.get("character", {}).items():
        character[key] = _character_field(ch, key, spec)

    resources = {
        name: _resource_init(spec, archive)
        for name, spec in t.get("resources", {}).items()
    }
    stats = {name: int(spec.get("init", 0)) for name, spec in t.get("stats", {}).items()}

    aff_chars = t.get("affection_chars", [])
    factions = t.get("factions", [])
    start_location = t.get("start_location", archive.get("start_location", "未知地点"))
    meta_rewind = t.get("meta", {}).get("rewind_left", 3)

    state: dict[str, Any] = {
        "character": character,
        "location": {"place": start_location, "season": "春", "date": "第1年1月"},
        "resources": resources,
        "stats": stats,
        "affection": {c: 0 for c in aff_chars},
        "affection_last_seen": {c: 0 for c in aff_chars},
        "faction": {f: 0 for f in factions},
        "inventory": list(ch.get("special_items", [])),
        "notes": [],
        "meta": {
            "turn": 0, "month": 0, "rewind_left": meta_rewind, "achievements": [],
            "direction": archive.get("direction", "自由/综合向"),
            "timeline_binding": archive.get("timeline_binding", "半绑定"),
            "session_id": archive.get("session_id", ""),
            "created_at": archive.get("created_at", ""),
            "world_id": (world.get("id") if isinstance(world, dict) else world) or "douluo",
            "world_name": world.get("name", "魂兽大陆") if isinstance(world, dict) else "魂兽大陆",
            "level_field": (world.get("state_template", {}).get("level_field", "soul_level") if isinstance(world, dict) else "soul_level"),
            "client_id": archive.get("client_id", ""),
        },
        "npcs": {},   # NPC 角色档案 {name: {description: str, first_met: str}}
    }
    if t.get("rings"):
        state["soul_rings"] = []
    return state


def validate_delta(delta: dict, state: dict, world=None) -> dict:
    """校验并钳制变动单，返回清洗后的 delta（不直接改 state）。

    同时接受通用键（resources/stats 增量）与魂兽大陆旧键（gold/silver/copper、
    soul_level 绝对目标、soul_ring_add）。输出保留旧键镜像以兼容旧调用。
    """
    t = template_of(world)
    out = deepcopy(delta) if isinstance(delta, dict) else {}

    # ── resources：通用 dict + 魂兽大陆旧键别名合并，钳到 min ──
    res = state["resources"]
    res_spec = t.get("resources", {})
    res_deltas: dict[str, int] = {}
    for k, v in (out.get("resources") or {}).items():
        if k in res:
            res_deltas[k] = res_deltas.get(k, 0) + _clamp_int(v)
    for legacy in ("gold", "silver", "copper"):
        if legacy in out and legacy in res:
            res_deltas[legacy] = res_deltas.get(legacy, 0) + _clamp_int(out[legacy])
    for name, inc in res_deltas.items():
        floor = res_spec.get(name, {}).get("min", 0) - res[name]  # 最多扣到 min
        res_deltas[name] = max(floor, inc)
    out["resources"] = res_deltas
    # 旧键镜像（兼容既有断言/旧代码读 out["gold"]）
    out["gold"] = res_deltas.get("gold", 0)
    out["silver"] = res_deltas.get("silver", 0)
    out["copper"] = res_deltas.get("copper", 0)

    # ── stats：通用属性增量，max_step 限步、min/max 限界 ──
    stats_spec = t.get("stats", {})
    stats_d: dict[str, int] = {}
    for k, v in (out.get("stats") or {}).items():
        if k not in state.get("stats", {}):
            continue  # 未知属性忽略（越权钳制）
        inc = _clamp_int(v)
        spec = stats_spec.get(k, {})
        ms = spec.get("max_step")
        if ms is not None:
            ms = _clamp_int(ms, floor=0)
            inc = max(-ms, min(ms, inc))
        cur = state["stats"][k]
        lo = spec.get("min", -10**9)
        hi = spec.get("max", 10**9)
        inc = max(lo - cur, min(hi - cur, inc))
        stats_d[k] = inc
    out["stats"] = stats_d

    # ── 等级字段（魂兽大陆旧键）：绝对目标，max_step 限步、floor_from 兜底 ──
    lf = t.get("level_field")
    if lf and lf in state["character"]:
        if lf in out and out[lf] is not None:
            target = _clamp_int(out[lf])
            cur = state["character"].get(lf, 0)
            char_spec = t.get("character", {}).get(lf)
            ms = _clamp_int(char_spec.get("max_step", 2), floor=0) if isinstance(char_spec, dict) else 2
            d = max(-ms, min(ms, target - cur))
            ff = char_spec.get("floor_from") if isinstance(char_spec, dict) else None
            floor = _clamp_int(state["character"].get(ff, 0)) if ff else 0
            out[lf] = max(floor, cur + d)
            # 等级字段上下限钳制（如心动值 0-100），douluo/万物生无 min/max 时为无操作
            if isinstance(char_spec, dict):
                lo = char_spec.get("min")
                if lo is not None:
                    out[lf] = max(_clamp_int(lo), out[lf])
                hi = char_spec.get("max")
                if hi is not None:
                    out[lf] = min(_clamp_int(hi), out[lf])
        else:
            out.pop(lf, None)
    # 魂兽大陆旧键 soul_level 只在命中 character 的等级字段上生效，否则丢弃
    if "soul_level" in out and (lf != "soul_level" or lf not in state["character"]):
        out.pop("soul_level", None)

    # ── affection：增量，钳到 [affection_min, affection_max]，允许动态新增角色 ──
    aff_min = t.get("affection_min", -100)
    aff_max = t.get("affection_max", 100)
    affection: dict[str, int] = {}
    for name, inc in (out.get("affection") or {}).items():
        cur = state["affection"].get(name, 0)
        affection[name] = max(aff_min, min(aff_max, cur + _clamp_int(inc)))
    out["affection"] = affection

    # ── faction：势力声望增量，钳到 [affection_min, affection_max]，未知势力忽略 ──
    faction: dict[str, int] = {}
    for name, inc in (out.get("faction") or {}).items():
        if name not in state["faction"]:
            continue  # 未知势力忽略（越权钳制）
        faction[name] = max(aff_min, min(aff_max, state["faction"].get(name, 0) + _clamp_int(inc)))
    out["faction"] = faction

    # ── rings（魂兽大陆专属进阶表）：按 cap_slots 上限钳制年限 ──
    ring_spec = t.get("rings")
    if ring_spec and out.get("soul_ring_add"):
        caps = ring_spec.get("cap_slots", [])
        slot = len(state.get("soul_rings", [])) + 1
        if slot <= len(caps):
            add = dict(out["soul_ring_add"])
            add["slot"] = slot
            add["years"] = _clamp_int(add.get("years"), floor=0, ceil=caps[slot - 1])
            add["beast"] = str(add.get("beast", "魂兽"))
            add["skill"] = str(add.get("skill", "未知魂技"))
            add["attribute"] = str(add.get("attribute", "无"))
            out["soul_ring_add"] = add
        else:
            out.pop("soul_ring_add", None)
    else:
        out.pop("soul_ring_add", None)

    out["inventory_add"] = [str(x) for x in (out.get("inventory_add") or []) if x]
    out["inventory_remove"] = [str(x) for x in (out.get("inventory_remove") or []) if x]
    out["notes_add"] = [str(x) for x in (out.get("notes_add") or []) if x]
    out["location"] = str(out.get("location") or state["location"]["place"])
    out["date"] = str(out.get("date") or state["location"]["date"])
    out["month_delta"] = _clamp_int(out.get("month_delta"), floor=0, ceil=24)

    # npcs：完整结构化 NPC 档案（AI 可增/改，按 name 增量合并）
    npcs_in = out.get("npcs")
    if isinstance(npcs_in, dict):
        cleaned = {}
        for name, profile in npcs_in.items():
            if not isinstance(profile, dict):
                continue
            cleaned[name] = {
                "age": str(profile.get("age", "")),
                "gender": str(profile.get("gender", "")),
                "background": str(profile.get("background", profile.get("description", ""))),
                "affection": str(profile.get("affection", "")),
                "personality": [str(p) for p in (profile.get("personality") or [])],
                "strength": str(profile.get("strength", "")),
                "preferences": str(profile.get("preferences", "")),
                "customNotes": str(profile.get("customNotes", "")),
                "first_met": str(profile.get("first_met", "")),
            }
        out["npcs"] = cleaned
    else:
        out.pop("npcs", None)
    return out
