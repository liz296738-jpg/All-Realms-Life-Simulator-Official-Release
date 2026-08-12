"""激活码池：随机码 + 服务器端登记（每年循环，一次生成、长期复用）。

一个码对应一年中的一个"日子"（键为 MM-DD，如 08-10），每年同一天用同一个码：
2026 年 8 月 10 号的码，2027 年 8 月 10 号、2028 年 8 月 10 号……永远能用。
码由站长用 generate_code.py 一次补齐一年（含闰日 02-29，共 366 个码），随机、
不可伪造，只存在服务器 data/activation_codes.json —— 不需要任何人去"算"，输入即用。
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CODES_PATH = BASE_DIR / "data" / "activation_codes.json"

# 去掉易混淆的 0/O、1/I，只留大写字母 + 数字，方便口述/输入
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# 每月的天数（二月按 29 天补齐，含闰日 02-29）→ 共 366 天，覆盖闰年
_MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def gen_code() -> str:
    """生成一个 12 位随机码，格式 XXXX-XXXX-XXXX。"""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def _norm(s: str) -> str:
    """归一化：去连字符/空白、转大写，容错前端五花八门的粘贴格式。"""
    return "".join(s.split()).replace("-", "").upper()


def load_codes() -> dict[str, str]:
    """读 {月-日(MM-DD): 激活码}。文件缺失/损坏 → 空 dict。"""
    try:
        data = json.loads(CODES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_codes(mapping: dict[str, str]) -> None:
    """原子写码池。保留已有日子、只补新的，避免改掉已发出的码。"""
    CODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CODES_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CODES_PATH)


def ensure_full_pool() -> int:
    """确保码池覆盖一年中每一天（含闰日 02-29，共 366 个码），缺失的补新码。

    幂等：已有日子的码保持不变（不会改掉已发出的码），只需第一次运行补齐。
    之后每年循环复用，不需要重新生成。返回本次新增数量。
    """
    mapping = load_codes()
    added = 0
    for month, days in enumerate(_MONTH_DAYS, start=1):
        for day in range(1, days + 1):
            key = f"{month:02d}-{day:02d}"
            if key not in mapping:
                mapping[key] = gen_code()
                added += 1
    if added:
        save_codes(mapping)
    return added


def find_day_by_code(code: str) -> str | None:
    """查一个码对应的日子（MM-DD，如 08-10）。码不在池中 → None。大小写/连字符宽容。"""
    c = _norm(code)
    if not c:
        return None
    for day, stored in load_codes().items():
        if _norm(stored) == c:
            return day
    return None


def find_code_for_date(d: "date") -> str | None:
    """查某一天（date 对象）对应的码。码按 月-日 存，每年同一天是同一个码。"""
    return load_codes().get(d.strftime("%m-%d"))
