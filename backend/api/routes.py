"""API 路由层 — 全部 FastAPI 端点。"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import uuid
from copy import deepcopy
from urllib.parse import quote
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from auth.subscription import (
    SUB_DAYS, FREE_TRIAL_TURNS, _GATE_LOCK,
    _norm_cid, _client_rec, _cn_now, _verify_code, _paid_status,
    _gate_for, _bump_trial,
)
from llm.deepseek_client import (
    MODEL, SETTLE_MAX_TOKENS, NARRATIVE_MIN_CHARS,
    _client_for, _friendly_err, _call_turn,
)
from game import exporter
from game import save_manager as sm
from game import worlds
from game.game_engine import apply_delta
from game.novel_parser import extract_text, sample_text, validate_upload_size
from game.prompt_builder import (
    build_narrative_messages, build_opening_messages, build_settle_messages,
    build_unified_messages, build_unified_opening_messages,
    state_summary,
)
from game.session_manager import (
    _load_session, _new_session, remove_session,
)
from game.state_schema import default_state
from game.world_builder import _friendly_build_error, build_world as _call_build_world

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 自由度档位 ──────────────────────────────────────────────
FREEDOM_TIERS = {
    1: {"chars": 200, "max_tokens": 320},
    2: {"chars": 500, "max_tokens": 800},
    3: {"chars": 1000, "max_tokens": 1600},
    4: {"chars": 1500, "max_tokens": 2400},
    5: {"chars": 2000, "max_tokens": 3200},
}
DEFAULT_FREEDOM = 3


def _freedom_tier(freedom) -> dict:
    """自由度 1-5 钳制到合法档位，非法输入回落默认档。"""
    try:
        f = int(freedom)
    except (TypeError, ValueError):
        f = DEFAULT_FREEDOM
    return FREEDOM_TIERS.get(f, FREEDOM_TIERS[DEFAULT_FREEDOM])


# ── 世界系统（世界 = JSON 规格）──────────────────────────────
def _resolve_world(world_id: str | None, client_id: str | None) -> dict:
    """解析世界：缺省回落 douluo；自建世界校验作者（非作者一律 404，不泄露存在）。"""
    wid = (world_id or "").strip() or "douluo"
    w = worlds.get_world(wid)
    if w is None:
        raise HTTPException(404, "世界不存在")
    if w["kind"] == "custom" and w.get("owner") != _norm_cid(client_id):
        raise HTTPException(404, "世界不存在")
    return w


# 建世界限流：单 client 5 次/小时（构建用玩家 Key 计费，但存储/IO 仍是站点资源）
_BUILD_WINDOW = 3600
_BUILD_LIMIT = 5
_build_history: dict[str, list[float]] = {}
_BUILD_LOCK = threading.Lock()


def _check_build_rate(client_id: str) -> None:
    now = time.time()
    with _BUILD_LOCK:
        hist = _build_history.setdefault(client_id, [])
        hist[:] = [t for t in hist if now - t < _BUILD_WINDOW]
        if len(hist) >= _BUILD_LIMIT:
            raise HTTPException(429, "建世界次数已达上限（5 次/小时），请稍后再试。")
        hist.append(now)


# 撤销栈上限：最多可连续"后悔" 20 回合，防止无界膨胀
UNDO_LIMIT = 20


# ── Pydantic 请求模型 ───────────────────────────────────────
class NewGameRequest(BaseModel):
    archive: dict
    session_id: str | None = None
    world_id: str | None = None  # 世界 id（缺省 = douluo）
    api_key: str | None = None  # BYOK：玩家自带 DeepSeek Key，缺省回落服务端 key
    freedom: int = DEFAULT_FREEDOM  # 自由度档位 1-5，控制每回合叙述字数
    client_id: str | None = None  # 浏览器身份：订阅门禁按此判断激活状态
    code: str | None = None  # 激活码（微信收款领到，本机 localStorage 携带）


class WorldDeleteRequest(BaseModel):
    world_id: str
    client_id: str | None = None


class ActRequest(BaseModel):
    session_id: str
    action: str
    api_key: str | None = None  # BYOK：同上
    freedom: int = DEFAULT_FREEDOM  # 同上
    client_id: str | None = None  # 浏览器身份：订阅门禁按此判断激活状态
    code: str | None = None  # 激活码（同 new-game）


class SessionRequest(BaseModel):
    session_id: str
    client_id: str | None = None


class ActivateRequest(BaseModel):
    code: str          # 激活码（XXXX-XXXX-XXXX）
    client_id: str | None = None


class EntitlementRequest(BaseModel):
    client_id: str | None = None
    code: str | None = None  # 本机保存的激活码，供码池校验


class LoadRequest(BaseModel):
    savepoint_id: str
    client_id: str | None = None


class UpdateNpcsRequest(BaseModel):
    session_id: str
    client_id: str | None = None
    npcs: dict  # {name: {age, gender, background, ...}}


class ExtractNpcProfilesRequest(BaseModel):
    session_id: str
    npc_names: list[str]
    client_id: str | None = None
    api_key: str | None = None  # BYOK: 服务端 key 不可用时玩家自带


class ExportAllRequest(BaseModel):
    client_id: str


class ImportAllRequest(BaseModel):
    client_id: str  # 导入后数据归属的新 client_id


EXTRACT_NPC_PROMPT = (
    "你是一个文字 RPG 的设定提取器。"
    "根据游戏叙述，为以下 NPC 提取结构化情报。\n\n"
    "【重要规则】\n"
    "1. 仅根据上下文提取信息，不要编造。上下文找不到的信息留空字符串。\n"
    "2. personality 是字符串数组（最多 5 个标签，每个 2-4 字）。\n"
    "3. affection 以好感度数值或描述状态表示（如 45、友好、敌视）。\n"
    "4. strength 为该角色在当前世界观下的实力描述（如 魂王、金丹期）。\n"
    "5. background 为一句话概括身份/职业（如 赏金猎人、长安城铁匠）。\n"
    "6. preferences 为喜好/厌恶摘要（如 贪财好色，最恨背叛）。\n"
    "7. 玩家手动填写的备注（customNotes）拥有最高优先级——若已存在则保留不动。\n\n"
    "返回 JSON 格式：{\"profiles\": { \"角色名\": { "
    "\"age\": \"\", \"gender\": \"\", \"background\": \"\", "
    "\"affection\": \"\", \"personality\": [], \"strength\": \"\", "
    "\"preferences\": \"\" } } }"
)


# ── SSE / 选项规范化 ────────────────────────────────────────
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _normalize_options(raw) -> list[dict]:
    """结算选项规范化：保证 label/text/recommended 三字段，且恰有一个系统推荐。

    - AI 没给选项时兜底单个「继续前行」（自定义世界规则书偶发不产出选项）；
    - label 缺失按 ABCD 顺序补；
    - 若 AI 未标注 recommended（或标了多个），取第一个为系统推荐，保证恰一个。
    """
    opts = list(raw or [])
    if not opts:
        return [{"label": "A", "text": "继续前行", "recommended": True}]
    out = []
    for i, o in enumerate(opts):
        if isinstance(o, dict):
            label = str(o.get("label") or ("ABCD"[i % 4] if i < 4 else f"E{i + 1}"))
            text = str(o.get("text") or "继续前行")
            recommended = bool(o.get("recommended"))
        else:
            label = "ABCD"[i % 4]
            text = str(o)
            recommended = False
        out.append({"label": label, "text": text, "recommended": recommended})
    if sum(1 for o in out if o["recommended"]) != 1:
        for j, o in enumerate(out):
            o["recommended"] = (j == 0)
    return out


# ── 回合引擎 ──────────────────────────────────────────────
def _run_turn(session_id: str, player_action: str, opening: bool = False,
              api_key: str | None = None, freedom: int = DEFAULT_FREEDOM,
              client_id: str | None = None, code: str | None = None):
    """生成叙述 + 结算（单次结构化 JSON 调用），应用状态，返回 SSE 生成器。

    旧架构：_stream_narrative(自由文本→strip→重试→兜底) + _call_settle(JSON) 两次调用。
    新架构：一次 response_format=json_object 调用同时产出 narrative + options + state_delta，
    JSON 结构本身保证 narrative 和 options 物理隔离——绝不可能混在一起。
    叙述按中文标点边界切分，模拟流式推给前端保持打字机体验。
    """
    sess = _load_session(session_id)
    state, base_history = sess["state"], list(sess["history"])
    tier = _freedom_tier(freedom)
    # 世界从会话状态恢复（旧存档无 world_id → 回落魂兽大陆）
    world = worlds.get_world(state.get("meta", {}).get("world_id", "douluo")) \
        or worlds.get_world("douluo")

    if opening:
        msgs = build_unified_opening_messages(state, sess["archive"], tier["chars"], world)
        turn_history = base_history
    else:
        user_msg = json.dumps({"role": "user", "content": player_action}, ensure_ascii=False)
        turn_history = base_history + [user_msg]
        msgs = build_unified_messages(state, turn_history, player_action, tier["chars"], world)

    unified_max_tokens = tier["max_tokens"] + SETTLE_MAX_TOKENS

    def gen():
        try:
            # ① 单次结构化调用：narrative + options + state_delta 一次产出
            data = _call_turn(msgs, api_key, max_tokens=unified_max_tokens)

            narrative = data.get("narrative", "")
            # Fallback：API 彻底失败（返回 {}）时用模板叙述
            if not narrative or len(str(narrative)) < NARRATIVE_MIN_CHARS:
                safe_name = state.get("character", {}).get("name", "你") if isinstance(state.get("character"), dict) else "你"
                safe_place = state.get("location", {}).get("place", "未知地点") if isinstance(state.get("location"), dict) else str(state.get("location", "未知地点"))
                narrative = (
                    f"{safe_name}站在{safe_place}，环顾四周。"
                    f"微风轻拂，带来远处隐约的声响。{safe_name}深吸一口气，等待着下一步的行动。"
                )

            # 模拟流式：按中文标点/换行边界切分推送
            text = str(narrative)
            buf = ""
            for ch in text:
                buf += ch
                if ch in "，。！？；：、\n）》《\"'」" or len(buf) >= 6:
                    yield _sse("text", {"content": buf})
                    buf = ""
            if buf:
                yield _sse("text", {"content": buf})

            # ② 结算数据直接从 JSON 提取
            settle_options = data.get("options", [])
            settle_state_delta = data.get("state_delta") or {}
            settle_notes = data.get("notes") or []
            settle_event = data.get("event") or ""
        except Exception as e:
            logger.error(f"回合生成失败 (session={session_id}): {e}", exc_info=True)
            # 失败时不写 history，避免玩家重试时重复追加同一行动。
            # StreamingResponse 在生成器迭代前已回 200 头，无法再改状态码——此处若 raise
            # HTTPException，Starlette 会静默吞掉异常，前端只见截断的流。故下发 event: error，
            # 前端 postSse 捕获后抛出并展示友好提示。已生成的叙述保留显示但不落账。
            yield _sse("error", {"message": _friendly_err(e)})
            return

        options = _normalize_options(settle_options)

        try:
            # "后悔"快照：在 apply_delta 落账前保存上一回合的完整状态、历史与选项。
            # 开场回合没有"上一回合"，不可撤销，故跳过。
            if not opening:
                sess["undo_stack"].append({
                    "state": deepcopy(state),
                    "history": list(base_history),
                    "options": list(sess["last_options"]),
                })
                sess["undo_stack"] = sess["undo_stack"][-UNDO_LIMIT:]

            apply_delta(state, settle_state_delta, world)

            # 注意：turn_history 来自闭包，这里只读；写入用新变量，避免遮蔽闭包变量
            new_history = turn_history + [json.dumps({"role": "assistant", "content": narrative}, ensure_ascii=False)]
            # 持久化最后选项，供"继续游戏"恢复
            state["meta"]["last_options"] = options
            sess["last_options"] = options
            sess["history"] = new_history
            sess["state"] = state
            # 回合记录：文字不丢——每次生成完压进 turns，前端回放完整叙述
            sess["turns"].append({
                "narrative": narrative,
                "options": options,
                "notes": settle_notes,
                "event": settle_event,
                "choice": None if opening else player_action,
            })
            sm.save_turns(session_id, sess["turns"], sess["undo_stack"])
            # 每回合同步落盘 state.json/history.jsonl，冷启动恢复时才不会拿到旧状态、
            # 旧历史去配新回合记录（否则 /api/resume 显示的回合与后续生成的账本不一致）。
            sm.save_state(session_id, state, new_history)
        except Exception as e:
            yield _sse("error", {"message": f"回合保存失败：{_friendly_err(e)}"})
            return

        # 订阅门禁：未激活玩家完成一个回合记一次免费试玩（激活期内自动跳过）。
        # 试玩计次尽力而为：登记表写失败不应拖垮本回合，故吞掉异常。
        try:
            _bump_trial(client_id, code)
        except Exception as e:
            logger.warning(f"试玩计次失败 (session={session_id}): {e}")

        # 每 10 回合自动存档（带上回合记录）
        if state["meta"]["turn"] % 10 == 0:
            try:
                sm.create_savepoint(session_id, state, new_history, sess["turns"])
            except Exception as e:
                logger.warning(f"自动存档失败 (session={session_id}): {e}")

        yield _sse("delta", {
            "state": state,
            "options": options,
            "notes": settle_notes,
            "event": settle_event,
            "can_undo": bool(sess["undo_stack"]),
        })
        yield "event: done\ndata: {}\n\n"

    return gen()


# ═══════════════════════════════════════════════════════════════
#  API 路由端点（19 个）
# ═══════════════════════════════════════════════════════════════

@router.get("/api/health")
def health():
    return {"ok": True}


@router.get("/api/saves")
def list_saves(client_id: str | None = None):
    return {"saves": sm.list_sessions(client_id=client_id)}


@router.post("/api/new-game")
def new_game(req: NewGameRequest):
    _gate_for(req.client_id, req.code)  # 订阅门禁：未激活且试玩用尽 → 403
    world = _resolve_world(req.world_id, req.client_id)
    session_id = req.session_id or uuid.uuid4().hex[:12]
    archive = req.archive
    archive["session_id"] = session_id
    archive["created_at"] = _cn_now().isoformat()
    archive["client_id"] = req.client_id or ""
    state = default_state(archive, world)
    sm.save_state(session_id, state, [])
    sm.save_turns(session_id, [], [])
    _new_session(session_id, state, [], archive)
    gen = _run_turn(session_id, "", opening=True, api_key=req.api_key, freedom=req.freedom,
                    client_id=req.client_id, code=req.code)
    return StreamingResponse(gen, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/act")
def act(req: ActRequest):
    _gate_for(req.client_id, req.code)  # 订阅门禁：未激活且试玩用尽 → 403
    _load_session(req.session_id)  # 触发 404 检查
    gen = _run_turn(req.session_id, req.action, api_key=req.api_key, freedom=req.freedom,
                    client_id=req.client_id, code=req.code)
    return StreamingResponse(gen, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/activate")
def activate(req: ActivateRequest):
    """输入码池激活码 → 查服务器登记的"日子" → 在对应日起 30 天窗口内即解锁。

    规则：一个码对应一年中的一个日子（MM-DD，每年循环），从对应日起 SUB_DAYS 天内
    任意一天都能激活；激活后订阅至对应日 + SUB_DAYS 天到期。不限次尝试：码随机、
    存服务器，无需限流防穷举。
    """
    cid = _norm_cid(req.client_id)
    code = (req.code or "").strip()
    if not cid:
        raise HTTPException(400, "缺少设备标识，请刷新页面后重试")
    if not code:
        raise HTTPException(400, "请输入激活码")
    ok, until, detail = _verify_code(code)
    if not ok:
        raise HTTPException(400, detail or "激活码无效。请核对后重试，或联系站长补发。")
    # 顺延：本机已订阅且原到期日更晚 → 保留更晚者（防重复激活把订阅降到同一起点）
    with _GATE_LOCK:
        acts = sm.load_activations()
        rec = _client_rec(acts, cid)
        paid, cur = _paid_status(rec)
        if paid and cur:
            try:
                if datetime.fromisoformat(cur) > datetime.fromisoformat(until):
                    until = cur
            except (ValueError, TypeError) as e:
                logger.debug(f"激活码顺延日期解析跳过 (client={cid}): {e}")
        rec["paid_until"] = until  # 本机镜像：激活后不带码也能继续读到期日
        rec.pop("trial_used", None)  # 已订阅不再计试玩
        acts[cid] = rec
        sm.save_activations(acts)
    return {"paid": True, "paid_until": until, "code": code}


@router.post("/api/entitlement")
def entitlement(req: EntitlementRequest):
    """查询当前订阅/试玩状态（Home 页展示 + 激活弹窗用）。

    前端带上本机保存的激活码（body.code）来做码池校验：码在对应日起 30 天窗口内
    → 订阅至对应日 + SUB_DAYS 天。不带码时读登记表 paid_until 镜像。
    """
    acts = sm.load_activations()
    rec = _client_rec(acts, _norm_cid(req.client_id))
    paid, cur = _paid_status(rec, req.code)
    return {
        "paid": paid,
        "paid_until": cur,
        "trial_used": int(rec.get("trial_used", 0)),
        "trial_limit": FREE_TRIAL_TURNS,
    }


@router.post("/api/resume")
def resume(req: SessionRequest):
    """继续游戏：返回最新状态、回合记录与当前选项（不调 AI）。"""
    try:
        sm.check_owner(req.session_id, req.client_id)
    except PermissionError:
        raise HTTPException(403, "无权操作此存档")
    sess = _load_session(req.session_id)
    state = sess["state"]
    # 上一条 assistant 叙述（兼容旧字段）
    last_narrative = ""
    for line in reversed(sess["history"]):
        try:
            e = json.loads(line)
            if e.get("role") == "assistant":
                last_narrative = e["content"]
                break
        except json.JSONDecodeError:
            continue
    options = state.get("meta", {}).get("last_options") or sess["last_options"] or []
    return {"session_id": req.session_id, "state": state,
            "last_narrative": last_narrative, "last_options": options,
            "turns": sess["turns"], "can_undo": bool(sess["undo_stack"])}


@router.post("/api/undo")
def undo(req: SessionRequest):
    """"后悔"：退回上一回合。弹出快照栈，还原状态/历史/选项，不调 AI。"""
    try:
        sm.check_owner(req.session_id, req.client_id)
    except PermissionError:
        raise HTTPException(403, "无权操作此存档")
    sess = _load_session(req.session_id)
    if not sess["undo_stack"]:
        raise HTTPException(400, "没有可撤销的回合")
    snap = sess["undo_stack"].pop()
    sess["state"] = snap["state"]
    sess["history"] = snap["history"]
    sess["last_options"] = snap["options"]
    sess["state"]["meta"]["last_options"] = snap["options"]
    if sess["turns"]:
        sess["turns"].pop()
    sm.save_state(req.session_id, sess["state"], sess["history"])
    sm.save_turns(req.session_id, sess["turns"], sess["undo_stack"])
    return {"session_id": req.session_id, "state": sess["state"],
            "options": snap["options"], "turns": sess["turns"],
            "can_undo": bool(sess["undo_stack"])}


@router.post("/api/save")
def save(req: SessionRequest):
    try:
        sm.check_owner(req.session_id, req.client_id)
    except PermissionError:
        raise HTTPException(403, "无权操作此存档")
    sess = _load_session(req.session_id)
    state, history = sess["state"], sess["history"]
    sp = sm.create_savepoint(req.session_id, state, history, sess["turns"])
    sm.save_state(req.session_id, state, history)
    return {"savepoint": sp}


@router.post("/api/load")
def load(req: LoadRequest):
    try:
        data = sm.load_savepoint(req.savepoint_id)
    except ValueError:
        raise HTTPException(400, "非法存档点 id")
    sid = req.savepoint_id.split("-")[0]
    try:
        sm.check_owner(sid, req.client_id)
    except PermissionError:
        raise HTTPException(403, "无权操作此存档")
    # 存档点恢复回合记录；撤销栈无法回放，置空（后悔从当前回合重新开始积累）
    sess = _new_session(sid, data["state"], data["history"], {},
                        turns=data.get("turns", []), undo_stack=[])
    sm.save_turns(sid, sess["turns"], [])
    # 读档必须同步落盘 state.json/history.jsonl，否则重启后冷启动仍读到读档前的旧状态
    sm.save_state(sid, data["state"], data["history"])
    return {"session_id": sid, "state": data["state"],
            "turns": sess["turns"], "can_undo": False}


@router.post("/api/delete")
def delete(req: SessionRequest):
    try:
        sm.check_owner(req.session_id, req.client_id)
    except PermissionError:
        raise HTTPException(403, "无权操作此存档")
    try:
        d = sm.session_dir(req.session_id)
    except ValueError:
        raise HTTPException(400, "非法会话 id")
    if d.exists():
        shutil.rmtree(d)
    remove_session(req.session_id)
    return {"ok": True}


@router.post("/api/update-npcs")
def update_npcs(req: UpdateNpcsRequest):
    """手动更新 NPC 角色设定（前端编辑后保存）。"""
    try:
        sm.check_owner(req.session_id, req.client_id)
    except PermissionError:
        raise HTTPException(403, "无权操作此存档")
    try:
        sess = _load_session(req.session_id)
    except HTTPException:
        raise
    state = sess["state"]
    existing = state.setdefault("npcs", {})
    for name, profile in req.npcs.items():
        if not isinstance(profile, dict):
            continue
        ex = existing.get(name, {})
        existing[name] = {
            "age": str(profile.get("age", ex.get("age", ""))),
            "gender": str(profile.get("gender", ex.get("gender", ""))),
            "background": str(profile.get("background", ex.get("background", profile.get("description", "")))),
            "affection": str(profile.get("affection", ex.get("affection", ""))),
            "personality": [str(p) for p in (profile.get("personality") or ex.get("personality") or [])],
            "strength": str(profile.get("strength", ex.get("strength", ""))),
            "preferences": str(profile.get("preferences", ex.get("preferences", ""))),
            "customNotes": str(profile.get("customNotes", ex.get("customNotes", ""))),
            "first_met": str(profile.get("first_met", ex.get("first_met", ""))),
        }
    sm.save_state(req.session_id, state, sess["history"])
    return {"ok": True}


@router.post("/api/extract-npc-profiles")
def extract_npc_profiles(req: ExtractNpcProfilesRequest):
    """AI 提取 NPC 结构化情报：读取游戏上下文 → DeepSeek → 返回结构化档案。"""
    sess = _load_session(req.session_id)
    state = sess["state"]
    world = _resolve_world(state.get("meta", {}).get("world_id") or "douluo", None)
    existing_npcs = state.get("npcs", {})
    # 构建上下文：状态 + 最近 30 条历史
    ctx_lines = [state_summary(state, world), ""]
    for line in sess["history"][-30:]:
        try:
            e = json.loads(line)
            role = e.get("role")
            content = e.get("content", "")
            if role == "user":
                ctx_lines.append(f"玩家行动：{content}")
            elif role == "assistant":
                ctx_lines.append(f"叙述：{content}")
        except json.JSONDecodeError:
            continue
    context = "\n".join(ctx_lines)
    # 为每个 NPC 附带已有数据（避免重复提取）
    npc_hints = []
    for name in req.npc_names:
        ex = existing_npcs.get(name, {})
        if ex.get("customNotes"):
            npc_hints.append(f"  {name}（已有备注：{ex['customNotes']}，请保留此备注）")
    hint_text = "\n".join(npc_hints) if npc_hints else "(无已有数据)"
    msgs = [
        {"role": "system", "content": EXTRACT_NPC_PROMPT},
        {"role": "user", "content": (
            f"**【已有备注（必须保留）】**\n{hint_text}\n\n"
            f"**【需要提取情报的 NPC】**\n{json.dumps(req.npc_names, ensure_ascii=False)}\n\n"
            f"**【游戏上下文】**\n{context}"
        )},
    ]
    # 非流式调用 DeepSeek
    try:
        client = _client_for(req.api_key)
        resp = client.chat.completions.create(
            model=MODEL, messages=msgs, temperature=0.3,
            max_tokens=2000, response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content or "{}"
        data = json.loads(text)
    except Exception as e:
        raise HTTPException(502, _friendly_err(e))
    raw_profiles = data.get("profiles", {})
    if not isinstance(raw_profiles, dict):
        raise HTTPException(502, "AI 返回格式异常，请重试")
    # 清洗并合并：保留已有 customNotes
    profiles = {}
    for name in req.npc_names:
        raw = raw_profiles.get(name, {})
        if not isinstance(raw, dict):
            raw = {}
        ex = existing_npcs.get(name, {})
        profiles[name] = {
            "age": str(raw.get("age", ex.get("age", ""))),
            "gender": str(raw.get("gender", ex.get("gender", ""))),
            "background": str(raw.get("background", ex.get("background", ""))),
            "affection": str(raw.get("affection", ex.get("affection", ""))),
            "personality": [str(p) for p in raw.get("personality", ex.get("personality", []))],
            "strength": str(raw.get("strength", ex.get("strength", ""))),
            "preferences": str(raw.get("preferences", ex.get("preferences", ""))),
            "customNotes": str(ex.get("customNotes", "")),  # 保留玩家备注
            "first_met": str(raw.get("first_met", ex.get("first_met", ""))),
        }
    # 写回 state
    state.setdefault("npcs", {}).update(profiles)
    sm.save_state(req.session_id, state, sess["history"])
    return {"profiles": profiles}


@router.post("/api/export-all")
def export_all(req: ExportAllRequest):
    """导出自定义世界 + 全部存档为备份 JSON 文件（浏览器下载）。"""
    cid = _norm_cid(req.client_id)
    if not cid:
        raise HTTPException(400, "缺少客户端标识")
    payload: dict = {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "worlds": {},
        "saves": {},
    }
    # 自定义世界
    for w in worlds.custom_worlds():
        if w.get("owner") == cid:
            payload["worlds"][w["id"]] = w
    # 存档（完整 state + history + turns + undo）
    sessions = sm.list_sessions(client_id=cid)
    for s in sessions:
        sid = s["session_id"]
        try:
            state, history = sm.load_state(sid)
            turns, undo = sm.load_turns(sid)
            payload["saves"][sid] = {
                "state": state, "history": history,
                "turns": turns, "undo": undo,
            }
        except Exception as e:
            logger.warning(f"导出存档 {sid} 加载失败，跳过: {e}")
            continue
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = quote(f"万界人生模拟器-备份-{ts}.json")
    return Response(
        content=body, media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


@router.post("/api/import-all")
async def import_all(file: UploadFile = File(...), client_id: str = Form(...)):
    """导入备份 JSON 文件：恢复世界和存档，归属到当前 client_id。"""
    cid = _norm_cid(client_id)
    if not cid:
        raise HTTPException(400, "缺少客户端标识")
    raw = await file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "文件格式错误，请上传有效的备份文件")
    if data.get("version") != 1:
        raise HTTPException(400, "备份文件版本不兼容，请使用新版导出的文件")
    worlds_imported = worlds_skipped = 0
    saves_imported = saves_skipped = 0
    # 恢复世界：已存在但 owner 不同 → 更新归属（同玩家换设备）；owner 相同 → 跳过
    existing_worlds = {w["id"]: w for w in worlds.custom_worlds()}
    for wid, wspec in (data.get("worlds") or {}).items():
        exist = existing_worlds.get(wid)
        if exist:
            if exist.get("owner") == cid:
                worlds_skipped += 1   # 已归属当前设备，跳过
            else:
                # 同玩家换设备：更新 owner
                wspec["owner"] = cid
                wspec["kind"] = "custom"
                try:
                    worlds.save_custom_world(wspec)
                    worlds_imported += 1
                except Exception as e:
                    logger.warning(f"导入世界 {wid} (已存在) 失败: {e}")
                    worlds_skipped += 1
        else:
            wspec["owner"] = cid
            wspec["kind"] = "custom"
            try:
                worlds.save_custom_world(wspec)
                worlds_imported += 1
            except Exception as e:
                logger.warning(f"导入世界 {wid} (新建) 失败: {e}")
                worlds_skipped += 1
    # 恢复存档（session_id 已存在则跳过，不覆盖已有进度）
    for sid, sdata in (data.get("saves") or {}).items():
        if (sm.SAVES_DIR / sid).exists():
            saves_skipped += 1
            continue
        state = sdata.get("state", {})
        history = sdata.get("history", [])
        turns = sdata.get("turns", [])
        undo = sdata.get("undo", [])
        state.setdefault("meta", {})["client_id"] = cid
        try:
            sm.save_state(sid, state, history)
            sm.save_turns(sid, turns, undo)
            saves_imported += 1
        except Exception as e:
            logger.warning(f"导入存档 {sid} 失败: {e}")
            saves_skipped += 1
    return {
        "worlds_imported": worlds_imported, "worlds_skipped": worlds_skipped,
        "saves_imported": saves_imported, "saves_skipped": saves_skipped,
    }


@router.post("/api/export")
def export(req: SessionRequest):
    """导出剧情：把一段旅程的叙述历史整理成 Markdown 小说（可下载、可分享）。

    纯本地读操作、无 AI 调用，不设订阅门禁——免费试玩期的玩家也能把玩过的剧情导出留念。
    """
    try:
        sm.check_owner(req.session_id, req.client_id)
    except PermissionError:
        raise HTTPException(403, "无权操作此存档")
    sess = _load_session(req.session_id)
    return exporter.build_novel_markdown(sess["state"], sess["turns"])


# ── 世界系统：广场列表 / 上传小说建世界 / 删除自建世界 ────
@router.get("/api/worlds")
def list_worlds(client_id: str | None = None):
    """世界广场：创作者已开发的世界对所有人可见；自建世界仅作者本人可见。"""
    cid = _norm_cid(client_id)
    builtin = [worlds.world_summary(w) for w in worlds.builtin_worlds()]
    mine = [worlds.world_summary(w) for w in worlds.custom_worlds()
            if w.get("owner") == cid]
    return {"builtin": builtin, "mine": mine}


@router.post("/api/worlds/build")
async def build_world(file: UploadFile = File(...), api_key: str | None = Form(None),
                      client_id: str | None = Form(None)):
    """上传小说 → 抽样精读 → 玩家自己的 DeepSeek Key 建世界框架 → 落盘。

    站点零成本（玩家 Key 计费）；不存小说原文；单 client 限流 5 次/小时。
    """
    cid = _norm_cid(client_id)
    if not api_key or not api_key.strip():
        raise HTTPException(400, "请先填写你自己的 DeepSeek API Key，建世界功能需要用它调用 DeepSeek。")
    _check_build_rate(cid or "anon")
    # 分块读取并提前拦截超大文件，避免整块读进内存（上限 30MB）
    _MAX_UPLOAD = 30 * 1024 * 1024
    raw = b""
    while True:
        chunk = await file.read(1024 * 256)
        if not chunk:
            break
        raw += chunk
        if len(raw) > _MAX_UPLOAD:
            raise HTTPException(400, "文件超过 30MB，请截取部分章节后再上传")
    try:
        validate_upload_size(raw)
        text = extract_text(file.filename or "", raw)
        sample = sample_text(text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        spec = _call_build_world(sample, api_key, cid)
    except Exception as e:
        raise HTTPException(400, _friendly_build_error(e))
    worlds.save_custom_world(spec)
    return worlds.world_summary(spec)


@router.post("/api/worlds/delete")
def delete_world(req: WorldDeleteRequest):
    """删除自建世界（仅作者本人）。创作者已开发的世界不可删。"""
    w = _resolve_world(req.world_id, req.client_id)
    if w["kind"] != "custom":
        raise HTTPException(400, "创作者已开发的世界不能删除")
    worlds.delete_custom_world(req.world_id)
    return {"ok": True}
