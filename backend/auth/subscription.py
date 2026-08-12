"""订阅门禁（微信收款 · 服务器端码池）。

码 = 站长用 generate_code.py 一次性生成的 365 个随机码，存在 data/activation_codes.json。
一个码对应一年中的一个日子（MM-DD），从对应日起 30 天内任意一天都可以激活；
订阅到期日固定为"对应日 + 30 天"（从码的日期起算，而非从激活日起算）。
激活后写本机 paid_until 镜像，供后续不带码读取。
"""
from __future__ import annotations

import os
import threading
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from game import activation_codes
from game import save_manager as sm

SUB_DAYS = 30   # 激活窗口天数：码从对应日起可激活，至对应日 + SUB_DAYS 天到期
FREE_TRIAL_TURNS = int(os.getenv("FREE_TRIAL_TURNS", "5"))   # 未激活可免费试玩的回合数（0 = 纯付费）

# 登记表读改写加锁：trial_used 是读-改-写，锁防止并发请求互相覆盖。
# 不锁整个回合流——只锁登记表本身的写操作（毫秒级），不会串行化 LLM 生成。
_GATE_LOCK = threading.Lock()

# 中国时区（UTC+8）。服务器可能跑在 UTC：码的"今天"、订阅到期比较必须以玩家所在的
# 中国时区墙钟为准，否则北京 0:00-8:00 之间会把"今天"错认成前一天（如北京 8/11
# 凌晨仍显示 8/10）。返回 naive（剥掉 tzinfo），与存量 naive iso 字符串可直接比较。
_CN_TZ = timezone(timedelta(hours=8))


def _norm_cid(cid: str | None) -> str:
    """归一化 client_id：统一去首尾空白，避免同一设备因空白差异产生不同记录键。"""
    return (cid or "").strip()


def _client_rec(acts: dict, cid: str) -> dict:
    """取一个客户端的登记记录（无则空）。非 dict 记录按空处理，防 500。"""
    cid = _norm_cid(cid)
    rec = acts.get(cid, {})
    return rec if isinstance(rec, dict) else {}


def _cn_now() -> datetime:
    """当前中国时区（UTC+8）墙钟时刻，naive。"""
    return datetime.now(_CN_TZ).replace(tzinfo=None)


def _verify_code(code: str) -> tuple[bool, str | None, str | None]:
    """校验码池中的激活码：返回 (是否可用, paid_until iso, 错误提示)。

    码池规则：一个码对应一年中的一个日子（MM-DD），每年循环使用。从对应日起
    SUB_DAYS 天内（含起止日）都可以激活；订阅到期日固定为"对应日 + SUB_DAYS 天"
    23:59:59（从码的日期起算，而非从激活日起算）。例如 8/10 的码在 8/10~9/9
    之间任意一天都可激活，到期始终为 9/9 23:59:59。
    "今天"以中国时区（UTC+8）为准（_cn_now()），每年同一天用同一个码，无需重新生成。
    """
    day = activation_codes.find_day_by_code(code)
    if day is None:
        return False, None, "激活码无效。请核对后重试，或联系站长补发。"
    try:
        mm, dd = int(day[:2]), int(day[3:5])
    except (ValueError, IndexError):
        return False, None, "激活码无效。请核对后重试，或联系站长补发。"
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return False, None, "激活码无效。请核对后重试，或联系站长补发。"
    today = _cn_now().date()
    # 构造码对应日期的完整 date（跨年场景：今天 1/5 但码是 12/25 → 取去年 12/25）
    try:
        code_date = date(today.year, mm, dd)
    except ValueError:
        # 非闰年 02-29 无法构造 → 回落去年（去年是闰年则存在，否则拒绝）
        try:
            code_date = date(today.year - 1, mm, dd)
        except ValueError:
            return False, None, "激活码无效。请核对后重试，或联系站长补发。"
    if code_date > today:
        try:
            code_date = date(today.year - 1, mm, dd)
        except ValueError:
            return False, None, "激活码无效。请核对后重试，或联系站长补发。"
    window_end = code_date + timedelta(days=SUB_DAYS)
    if today < code_date or today > window_end:
        # 只提示"码不对"，不透露这个码对应哪一天——避免激活码隐私泄漏。
        return False, None, "激活码错误或已过期，请核对后重试。"
    until = (datetime.combine(window_end, datetime.min.time())
             + timedelta(days=1) - timedelta(seconds=1))
    return True, until.isoformat(), None


def _paid_status(rec: dict, code: str | None = None) -> tuple[bool, str | None]:
    """返回 (是否在激活期内, paid_until iso)。过期按未激活处理。

    两种来源都算有效订阅：
    1. 码池激活（主）：code 在服务器码池中、且在对应日起 30 天窗口内 → 激活成功，
       到期 = 对应日 + SUB_DAYS 天。码随机存服务器，不可伪造；
    2. 登记表 paid_until 镜像：activate 成功时写一份，供之后（含码的对应日窗口已过）
       不带码的请求读取——本机持续有效至到期日。
    """
    if code:
        ok, until, _ = _verify_code(code)
        if ok:
            return True, until
    cur = rec.get("paid_until")
    if cur and isinstance(cur, str):
        try:
            if datetime.fromisoformat(cur) >= _cn_now():
                return True, cur
        except ValueError:
            pass
    return False, None


def _gate_for(client_id: str | None, code: str | None = None) -> None:
    """订阅门禁：持有效激活码或登记在激活期内 → 放行；否则免费试玩回合用尽 → 403。"""
    acts = sm.load_activations()
    rec = _client_rec(acts, _norm_cid(client_id))
    if _paid_status(rec, code)[0]:
        return
    used = int(rec.get("trial_used", 0))
    if used >= FREE_TRIAL_TURNS:
        raise HTTPException(403, "免费试玩已结束。1元/月订阅即可无限游玩——微信扫码支付后联系站长领取激活码，在此输入即可继续。")


def _bump_trial(client_id: str | None, code: str | None = None) -> None:
    """未激活玩家每完成一个回合记一次免费试玩；激活期内不计数。回合失败时不会调用。"""
    if FREE_TRIAL_TURNS <= 0:
        return
    cid = _norm_cid(client_id)
    with _GATE_LOCK:
        acts = sm.load_activations()
        rec = _client_rec(acts, cid)
        if _paid_status(rec, code)[0]:
            return
        rec["trial_used"] = int(rec.get("trial_used", 0)) + 1
        acts[cid] = rec
        sm.save_activations(acts)
