"""查看 / 补全服务器端激活码池（每年循环，一次生成、长期复用）。

码池方案：一个码对应一年中的一个"日子"（键 MM-DD，含闰日 02-29，共 366 个码），
每年同一天用同一个码——2026 年 8 月 10 号的码，2027 年 8 月 10 号、2028 年……永远能用，
不需要每年重新生成。码随机生成、存服务器 data/activation_codes.json，不可伪造、无需人算。

用法：
    python generate_code.py               # 交互模式：补齐码池并展示
    python generate_code.py 365           # 补齐码池，从今天起展示 365 天
    python generate_code.py 2026-08-10    # 从指定日期起展示 365 天
    python generate_code.py 20260810 100  # 从指定日期起展示 100 天

按天发码：顾客扫码付款后，把"今天"的码发给他，从对应日起 30 天内任意一天都能激活。
激活后订阅至对应日 + 30 天到期。同一天多个顾客用同一个码。
首次运行补齐全部 366 个码，之后每次只是查看，不再改动已生成的码。
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

from game import activation_codes
from game.activation_codes import ensure_full_pool, find_code_for_date

SUB_DAYS = 30   # 与 backend/main.py 的 SUB_DAYS 保持一致


def parse_date_arg(arg: str) -> date:
    arg = arg.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(arg, fmt).date()
        except ValueError:
            continue
    raise SystemExit(f"无法解析日期：{arg!r}（支持 YYYYMMDD、YYYY-MM-DD、YYYY/M/D）")


def _fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _print_codes(start: date, days: int, added: int) -> None:
    mapping = activation_codes.load_codes()
    offset = (date.today() - start).days
    print(f"\n═ 激活码池（共 {len(mapping)} 个码，每年循环复用）═")
    print(f"本次补全新增 {added} 个码（首次运行补齐全年，之后不改动已发出的码）。")
    print("一个码 = 一年中的一天，每年同一天用同一个码；从对应日起 30 天内可激活，激活后至对应日 + 30 天到期：")
    print("\n  #   日期          到期日期      激活码")
    for i in range(days):
        d = start + timedelta(days=i)
        code = find_code_for_date(d)
        if not code:
            continue
        expiry = d + timedelta(days=SUB_DAYS)
        marker = " [今天]" if i == offset else ""
        print(f"  {i+1:<3} {_fmt(d)}  {_fmt(expiry)}  {code}{marker}")
    print("\n发码流程：顾客微信扫码支付 1 元 → 把今天的码发给顾客 → 顾客在对应日起 30 天内随时激活。")
    print("同一天有多个顾客 → 用同一天的同一个码即可。码每年循环，不需要再生成新的。")


def interactive() -> int:
    print("═ 微信订阅激活码生成器（服务器端码池 · 每年循环）═")
    print("先补齐全年 366 个码（含闰日），每个码对应一年中的一天、从对应日起 30 天内都能激活；")
    print("到期日为对应日 + 30 天。之后每天运行一次，把 [今天] 那个码发给付款的顾客即可。")
    added = ensure_full_pool()
    start_s = input(f"\n从哪天开始展示？(回车默认今天 {_fmt(date.today())}) > ").strip()
    start = parse_date_arg(start_s) if start_s else date.today()
    days_s = input("展示多少天？(回车默认 365 天) > ").strip()
    try:
        days = int(days_s) if days_s else 365
    except ValueError:
        days = 365
    days = max(1, min(days, 3660))
    _print_codes(start, days, added)
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if a]
    if not args:
        return interactive()
    try:
        if args[0].isdigit() and len(args[0]) == 8:
            start = parse_date_arg(args[0])
            days = int(args[1]) if len(args) > 1 else 365
        elif "-" in args[0] or "/" in args[0]:
            start = parse_date_arg(args[0])
            days = int(args[1]) if len(args) > 1 else 365
        else:
            start = date.today()
            days = int(args[0])
        if days <= 0 or days > 3660:
            raise SystemExit("天数需在 1~3660 之间")
    except ValueError:
        raise SystemExit("参数需为数字/日期：python generate_code.py [YYYYMMDD|YYYY-MM-DD] [天数]")

    added = ensure_full_pool()
    _print_codes(start, days, added)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
