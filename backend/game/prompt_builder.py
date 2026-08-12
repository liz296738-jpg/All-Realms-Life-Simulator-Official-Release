"""提示词组装：规则书 + 当前状态 + 历史 + 玩家行动。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import worlds

RULES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"
_SYSTEM = RULES_PATH.read_text(encoding="utf-8")
_DOULUO = worlds.get_world("douluo")  # 无 world 时的默认规则书来源

# 全局反水字数铁律：追加到所有 system prompt 末尾，防止模型复读/卡死在静态环境
_ANTI_LOOP_RULES = (
    "【🔥 最高优先级绝对规则（防卡死与强制破局）】\n"
    "1. 拒绝复读与水字数：绝对禁止使用“环顾四周”、“微风轻拂”、“深吸一口气”、“等待下一步行动”等无意义的静态占位废话！严禁重复上一回合已经描写过的动作、对话或场景！\n"
    "2. 惩罚敷衍输入：如果玩家的行动指令极短或无明确意义（例如只输入“A”、“看看”、“1”、“出门”等），你绝对不能顺着环境继续静止！必须立刻强制触发一个【突发危机或事件】（例如：敌人突袭、神秘人拦截、陷阱触发、甚至直接受到伤害）来强行打破僵局！\n"
    "3. 推动力：你的每一回合输出，都必须包含实质性的剧情推进、冲突升级或信息增量。"
)


def system_prompt(world: dict | None = None) -> str:
    """规则书全文：有世界取世界 rulebook，否则魂兽大陆默认。末尾追加全局反水字数铁律。"""
    base = world["rulebook"] if isinstance(world, dict) and world.get("rulebook") else _SYSTEM
    return base + "\n\n" + _ANTI_LOOP_RULES


def _world_or_douluo(world: dict | None) -> dict:
    return world if isinstance(world, dict) else _DOULUO


def _label_map(world: dict) -> dict:
    """creation_schema 字段 key → 中文 label，供通用摘要美化显示。"""
    labels: dict[str, str] = {}
    for step in world.get("creation_schema", {}).get("steps", []):
        for f in step.get("fields", []):
            if f.get("key"):
                labels[f["key"]] = f.get("label") or f["key"]
    return labels


# ═══════════════════════════════════════════════════════════════════════════════
#  通用状态摘要渲染器（零硬编码——所有差异化行为由 world spec 驱动）
# ═══════════════════════════════════════════════════════════════════════════════

def state_summary(state: dict, world: dict | None = None) -> str:
    """完全通用的状态摘要：根据 world spec 动态遍历 state 字典。

    严禁任何 ``if world_id == 'xxx'`` 形式的硬编码——世界间差异全部通过
    ``world["state_template"]`` 和 ``world["creation_schema"]`` 驱动。
    """
    world = _world_or_douluo(world)
    st = world.get("state_template", {}) or {}
    labels = _label_map(world)
    level_field = st.get("level_field")  # 等级字段名（如 "soul_level" / "realm" / "heart"）
    lines: list[str] = []

    # ── 1. 角色基础信息：动态遍历 character 字典 ──────────────────
    c = state.get("character", {})
    if isinstance(c, dict):
        for k, v in c.items():
            if isinstance(v, list):
                v = "、".join(str(x) for x in v)
            if v in (None, "", [], ()):
                continue
            label = labels.get(k, k)
            lines.append(f"{label}：{v}")

    # ── 2. 特殊顶层数组字段（如 soul_rings）：有则渲染，无则跳过 ──
    #     每个世界的 state_template 可声明 "summary_arrays" 列表来驱动此段。
    summary_arrays = st.get("summary_arrays") or []
    if not summary_arrays and "soul_rings" in state:
        # 向后兼容：魂兽大陆旧 spec 未显式声明 summary_arrays，
        # 但只要 state 里有 soul_rings 就默认渲染。
        summary_arrays = ["soul_rings"]
    for arr_key in summary_arrays:
        arr = state.get(arr_key)
        if not isinstance(arr, list) or not arr:
            continue
        arr_label = labels.get(arr_key, arr_key)
        parts: list[str] = []
        for item in arr:
            if isinstance(item, dict):
                parts.append("·".join(f"{fk}{fv}" for fk, fv in item.items()))
            else:
                parts.append(str(item))
        lines.append(f"{arr_label}：{'；'.join(parts)}")

    # ── 3. 位置 + 时间 ────────────────────────────────────────────
    loc = state.get("location", {})
    if isinstance(loc, dict):
        place = loc.get("place", "")
        date = loc.get("date", "")
        season = loc.get("season", "")
        if place or date:
            lines.append(f"所在地：{place} | 时间：{date}（{season}）")

    # ── 4. 资源 ───────────────────────────────────────────────────
    res = state.get("resources", {})
    if isinstance(res, dict) and res:
        parts = [f"{k}({v})" for k, v in res.items() if v != 0]
        if parts:
            lines.append("【资源】：" + "，".join(parts))

    # ── 5. 属性 ───────────────────────────────────────────────────
    stats = state.get("stats", {})
    if isinstance(stats, dict) and stats:
        parts = [f"{k}({v})" for k, v in stats.items() if v != 0]
        if parts:
            lines.append("【属性】：" + "，".join(parts))

    # ── 6. 好感度 ─────────────────────────────────────────────────
    aff = state.get("affection", {})
    if isinstance(aff, dict) and aff:
        parts = [f"{k}({v})" for k, v in sorted(aff.items(), key=lambda x: -x[1]) if v]
        if parts:
            lines.append("【好感度】：" + "，".join(parts))

    # ── 7. 势力声望 ───────────────────────────────────────────────
    fac = state.get("faction", {})
    if isinstance(fac, dict) and fac:
        parts = [f"{k}({v})" for k, v in fac.items() if v]
        if parts:
            lines.append("【势力声望】：" + "，".join(parts))

    # ── 8. 背包 ───────────────────────────────────────────────────
    inv = state.get("inventory", [])
    if inv:
        if isinstance(inv, list):
            lines.append(f"【道具】：{'、'.join(str(x) for x in inv)}")
        else:
            lines.append(f"【道具】：{inv}")

    # ── 9. 笔记 ───────────────────────────────────────────────────
    notes = state.get("notes", [])
    if notes:
        if isinstance(notes, list):
            lines.append(f"【笔记】：{'；'.join(str(x) for x in notes)}")
        else:
            lines.append(f"【笔记】：{notes}")

    # ── 10. 游玩元信息 ────────────────────────────────────────────
    meta = state.get("meta", {})
    if isinstance(meta, dict):
        direction = meta.get("direction", "")
        binding = meta.get("timeline_binding", "")
        turn = meta.get("turn", "")
        extra_parts = []
        if direction:
            extra_parts.append(f"游玩方向：{direction}")
        if binding:
            extra_parts.append(f"时间线绑定：{binding}")
        if turn:
            extra_parts.append(f"当前回合：{turn}")
        if extra_parts:
            lines.append(" | ".join(extra_parts))

    # ── 11. NPC 角色档案 ──────────────────────────────────────────
    npc_txt = _npcs_summary(state)
    if npc_txt:
        lines.append(npc_txt)

    return "\n".join(lines)


def _npcs_summary(state: dict) -> str:
    """NPC 角色档案摘要（完整结构化信息），供 AI 感知。"""
    npcs = state.get("npcs", {})
    if not npcs:
        return ""
    lines = ["", "【已知 NPC 角色档案】"]
    for name, prof in sorted(npcs.items()):
        age = prof.get("age", "")
        gender = prof.get("gender", "")
        bg = prof.get("background", prof.get("description", ""))  # 兼容旧 description 字段
        basic = f"{gender} {age}岁" if gender or age else ""
        if bg:
            basic = f"{basic} · {bg}" if basic else bg
        lines.append(f"- {name}：{basic}" if basic else f"- {name}")
        if prof.get("personality"):
            lines.append(f"  性格：{'、'.join(prof['personality'])}")
        if prof.get("strength"):
            lines.append(f"  实力：{prof['strength']}")
        if prof.get("affection"):
            lines.append(f"  好感：{prof['affection']}")
        if prof.get("preferences"):
            lines.append(f"  喜好：{prof['preferences']}")
        if prof.get("customNotes"):
            lines.append(f"  ⚠️ 玩家备注（最高优先级）：{prof['customNotes']}")
        if prof.get("first_met"):
            lines.append(f"  初遇：{prof['first_met']}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  历史消息裁剪
# ═══════════════════════════════════════════════════════════════════════════════

def _history_messages(history: list[str], limit: int = 60,
                      token_budget: int = 20000) -> list[dict]:
    """历史消息：按条数与估算 token 双重上限裁剪，防止高档位长叙述把上下文撑爆。

    DeepSeek chat 上下文 64K：规则书 + 状态 ≈ 3K，当前叙述 + 选项 ≈ 3-4K，
    剩余给历史。按"1 中文字 ≈ 1.3 token"估算，从最新往旧累计到 budget 即停，
    保留的条目仍是旧→新的时间顺序。
    """
    msgs = []
    for line in history[-limit:]:
        try:
            entry = json.loads(line)
            if entry.get("role") in ("user", "assistant"):
                msgs.append({"role": entry["role"], "content": entry["content"]})
        except json.JSONDecodeError:
            continue
    # 从最新往旧裁剪
    msgs.reverse()
    kept, used = [], 0
    for m in msgs:
        est = max(1, int(len(m.get("content", "")) * 1.3))
        if used + est > token_budget:
            break
        kept.append(m)
        used += est
    kept.reverse()
    return kept


# ═══════════════════════════════════════════════════════════════════════════════
#  自由度字数提示
# ═══════════════════════════════════════════════════════════════════════════════

def _append_length_hint(text: str, chars: int | None) -> str:
    """自由度字数要求：显式给出 ±15% 区间（max_tokens 只是硬上限，指令才引导长度）。

    规则书把每轮叙述固定为 150-250 字，会压制高档位——故本指令显式声明
    覆盖规则书的字数限制，并以本要求为准。实测：模型自然篇幅约 1500 字，
    仅靠"宁多勿少"会让中档位鼓包、高档位飘忽，故对高档位改用结构性指令
    （至少 5 段展开）——具体结构比抽象字数更可控。
    """
    if chars:
        lo = max(int(chars * 0.85), 120)
        hi = int(chars * 1.15)
        text += (f"\n【字数要求】本回合叙述应约为 {chars} 字，字数须在 {lo}～{hi} 字之间，"
                 f"尽量靠近 {chars} 字。\n"
                 f"（本字数要求优先，覆盖规则书中的 150-250 字固定叙述限制，以本要求为准。）")
        if chars >= 1500:
            text += (f"\n请将叙述分成至少 5 个自然段逐段展开（环境→人物→行动→对白→心理→收束），"
                     f"写足 {lo} 字再收尾，宁可偏长不要偏短。")
    return text


# ═══════════════════════════════════════════════════════════════════════════════
#  提示词构建器（叙述 / 开场 / 统合 / 结算）
# ═══════════════════════════════════════════════════════════════════════════════

def _state_delta_example(world: dict, state: dict, extra: str = "") -> str:
    """根据 world.state_template 构造嵌套 state_delta 示例片段，供提示词引用。"""
    st = world.get("state_template", {}) or {}
    res_n = list((st.get("resources") or {}).keys())
    stat_n = list((st.get("stats") or {}).keys())
    aff_n = list(st.get("affection_chars") or []) or list((state.get("affection") or {}).keys())
    ex: list[str] = [f'"resources": {{"{res_n[0]}": -10}}'] if res_n else []
    if stat_n:
        ex.append(f'"stats": {{"{stat_n[0]}": 1}}')
    if aff_n:
        ex.append(f'"affection": {{"{aff_n[0]}": 5}}')
    ex_str = ", ".join(ex)
    if ex_str:
        ex_str += ", "
    ex_str += extra or '"location": "新地点", "date": "第X年X月"'
    return "{" + ex_str + "}"


def build_narrative_messages(state: dict, history: list[str], player_action: str,
                             chars: int | None = None, world: dict | None = None) -> list[dict]:
    world = _world_or_douluo(world)
    msgs = [{"role": "system", "content": system_prompt(world)}]
    msgs.append({"role": "system", "content": "【当前状态】\n" + state_summary(state, world)})
    msgs.extend(_history_messages(history))
    user = (
        f"【你的行动】\n{player_action}\n\n"
        "请按叙述规则续写世界。正文必须是一段连贯的叙述文字（场景、人物、行动、对白），"
        "至少 120 字；严禁把'叙述'、'……'等占位词或纯粹的选项清单当作正文——"
        "本轮的 3-4 个行动选项由结算引擎在本回合稍后单独生成，你只需把正文写足写好。"
    )
    msgs.append({"role": "user", "content": _append_length_hint(user, chars)})
    return msgs


def build_opening_messages(state: dict, archive: dict, chars: int | None = None,
                           world: dict | None = None) -> list[dict]:
    """开场回合提示词（通用版——不再按 world_id 特判）。"""
    world = _world_or_douluo(world)
    msgs = [{"role": "system", "content": system_prompt(world)}]
    msgs.append({"role": "system", "content": "【新角色状态】\n" + state_summary(state, world)})
    user = (
        f"新玩家已创建角色，档案卡：{json.dumps(archive, ensure_ascii=False)}。\n"
        f"请写出这场{world.get('name', '未知世界')}之行的开场白：交代当前地点、季节、"
        "出场人物或氛围，让玩家感受到自己是谁、身在何处。正文必须是一段连贯的叙述文字，"
        "至少 120 字；严禁把'叙述'、'……'等占位词或纯粹的选项清单当作正文——"
        "本轮的 3-4 个行动选项由结算引擎在本回合稍后单独生成，你只需把正文写足写好。\n"
        "请以【地点·场景·季节·时段】开头。"
    )
    msgs.append({"role": "user", "content": _append_length_hint(user, chars)})
    return msgs


def build_unified_messages(state: dict, history: list[str], player_action: str,
                            chars: int | None = None, world: dict | None = None) -> list[dict]:
    """合并叙述+结算为一次结构化 JSON 调用。

    旧架构：叙述（自由文本→strip_options→重试→兜底）+ 结算（JSON）两次调用。
    新架构：一次 JSON 调用同时产出 narrative + options + state_delta + notes + event。
    JSON 结构本身保证 narrative 和 options 物理隔离，不再需要正则剥离。
    """
    world = _world_or_douluo(world)
    msgs = [{"role": "system", "content": system_prompt(world)}]
    msgs.append({"role": "system", "content": "【当前状态】\n" + state_summary(state, world)})
    msgs.extend(_history_messages(history))
    ex = _state_delta_example(world, state)

    user = (
        f"【你的行动】\n{player_action}\n\n"
        "请输出一个完整的 JSON 对象，包含以下五个字段：\n\n"
        "1. narrative（字符串）：一段连贯的故事叙述文字，包含场景描写、人物行动与对白。"
        "这是纯故事正文，绝不包含选项列表——options 在 JSON 中是独立字段，不要写到 narrative 里。\n"
        "2. options（数组）：3-4 个不同的行动选项，每个选项含三个字段——"
        "label（A/B/C/D）、text（完整中文行动描述，带情绪或代价暗示）、"
        "recommended（布尔值，有且仅有一个为 true，标记最符合当前剧情走向的选项）。\n"
        f"3. state_delta（对象）：状态变更，必须用嵌套结构，例如 {ex}。"
        "资源/属性/好感名只能出现在对应嵌套键里（如 resources 内的 gold、stats 内的 soul_power），"
        "严禁平铺到顶层（如 {\"灵石\": -10} 是错误格式）。state_delta 必须与 narrative 描述一致"
        "——花了钱要扣、升了级要加、换了地点要改、加了好感要反映。\n"
        "4. notes（字符串数组）：1-2 条回合中产生的重要线索或待办笔记，无则空数组 []。\n"
        "5. event（字符串）：如果本回合触发了事件或里程碑，填事件标题；否则空字符串 \"\"。\n\n"
        "重要：narrative 是纯故事叙述，options 是独立的数据数组。因为这是 JSON 结构，"
        "字段本身就是分离的——你不需要在 narrative 里写选项，也绝不要把选项写进 narrative。"
        "narrative 写足字数，options 写得丰富有选择感。\n\n"
        "【💥 绝对规则：防卡死与强制破局】\n"
        "1. 拒绝复读：严禁在 narrative 中重复上一回合已经描写过的动作、对话或场景！"
        "必须展现行动的'后续结果'。\n"
        "2. 强制推进：如果玩家的行动导致剧情停滞，或者玩家在反复进行无意义的重复操作，"
        "你必须立刻生成一个强有力的【突发事件】（如敌袭、意外收获、神秘人介入、环境突变等）"
        "来强行打破僵局，推动剧情向前发展！"
    )
    msgs.append({"role": "user", "content": _append_length_hint(user, chars)})
    return msgs


def build_unified_opening_messages(state: dict, archive: dict, chars: int | None = None,
                                    world: dict | None = None) -> list[dict]:
    """开场回合的合并提示词：角色创建 + 叙述 + JSON 结算一次产出（通用版）。"""
    world = _world_or_douluo(world)
    msgs = [{"role": "system", "content": system_prompt(world)}]
    msgs.append({"role": "system", "content": "【新角色状态】\n" + state_summary(state, world)})
    ex = _state_delta_example(world, state, extra='"location": "新地点", "date": "第X年X月"')

    base = (
        f"新玩家已创建角色，档案卡：{json.dumps(archive, ensure_ascii=False)}。\n"
        f"请写出这场{world.get('name', '未知世界')}之行的开场白，输出一个完整的 JSON 对象，"
        "包含以下五个字段：\n\n"
        "1. narrative（字符串）：开场叙述。交代当前地点、季节、出场人物与氛围，"
        "让玩家感受到自己是谁、身在何处。纯故事正文，绝不包含选项列表。"
        "请以【地点·场景·季节·时段】开头。\n"
        "2. options（数组）：3-4 个开场行动选项，每个含 label(A/B/C/D)、text（完整中文描述）、"
        "recommended（有且仅有一个 true）。\n"
        f"3. state_delta（对象）：状态变更，必须用嵌套结构，例如 {ex}。"
        "资源/属性/好感名只能出现在对应嵌套键里，严禁平铺到顶层。叙述中涉及的初始状态设定"
        "（如起始地点、初始资源等）要在 state_delta 中体现。\n"
        "4. notes（字符串数组）：1-2 条初始线索或待办笔记，无则空数组 []。\n"
        "5. event（字符串）：如有初始事件触发则填标题，否则空字符串 \"\"。\n\n"
        "重要：narrative 是纯故事叙述，options 是独立的数据数组。因为这是 JSON 结构，"
        "字段本身就是分离的——你不需要在 narrative 里写选项，也绝不要把选项写进 narrative。\n\n"
        "【⚠️ 开场强制指令（第一推力）】\n"
        "警告：这是玩家降生在这个世界的第一个瞬间。请绝对不要描写静态的风景或平淡的日常！\n"
        "玩家此时必须正处于一个【紧迫或充满悬念的事件】之中（例如：正在被追杀、面前正发生一场争执、正处于某场重要考核的倒计时等）。\n"
        "请直接通过这个危机事件作为开场，强行把玩家拉入剧情漩涡，并逼迫玩家做出第一个抉择！"
    )
    msgs.append({"role": "user", "content": _append_length_hint(base, chars)})
    return msgs


def build_settle_messages(state: dict, history: list[str], narrative: str,
                          world: dict | None = None) -> list[dict]:
    """结算提示词（通用版）。"""
    world = _world_or_douluo(world)
    msgs = [{"role": "system", "content": system_prompt(world)}]
    msgs.append({"role": "system", "content": "【当前状态】\n" + state_summary(state, world)})
    msgs.extend(_history_messages(history))
    ex = _state_delta_example(world, state)

    msgs.append({"role": "user", "content":
        f"刚才的叙述如下：\n{narrative}\n\n"
        "请作为结算引擎输出本轮 JSON 结算（options + state_delta + notes + event）。"
        "选项要求：\n"
        "- options 必须给出 3-4 个不同的行动选项，label 用 A/B/C/D，text 为完整的中文行动描述（带情绪/代价暗示）。\n"
        "- options 字段必不可少且优先于任何规则书中的输出格式规定——本指令为准，规则书若与之一致则照做，若冲突则按本指令输出。\n"
        "- 系统推荐：结合世界大纲/正典与玩家当前行为路径，判定其中最符合剧情走向的一个选项，"
        "给该选项加 \"recommended\": true（有且仅有一个）。\n"
        f"- state_delta 必须用嵌套结构，例如 {ex}。资源/属性/好感名只能出现在对应嵌套键里，"
        "严禁平铺到顶层（如 {\"灵石\": -10} 是错误格式）。state_delta 必须与叙述一致，"
        "例如叙述中花了钱、提升了等级、改了地点、加了好感，都要如实反映。"})
    return msgs
