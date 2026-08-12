"""剧情导出：把一场会话的叙述历史整理成 Markdown 小说。

玩家通关或想留个纪念时，在存档面板点「导出」，把自己在这段旅程中亲身经历的
故事（AI 每回合生成的叙述正文）整理成一篇可下载、可分享的 Markdown 小说。

只导出 AI 叙述正文（创作方向已定）：去掉每回合开头的【地点·场景·季节·时段】
标注与结尾的【选项】块，用 `---` 作场景分隔，读起来像一部有场景转换的小说。
"""
from __future__ import annotations

import re
from datetime import datetime

from . import worlds


_OPTION_LINE = re.compile(r"^\s*[A-Da-d][\.、．]\s*")


def _strip_meta(text: str) -> str:
    """去掉单条叙述的元信息外壳，保留正文。

    - 先剥前导空白（AI 偶尔在正文前带空行/BOM，防【地点】头漏剥）；
    - 只剥含「·」的括号标注（规则书的【地点·场景·季节·时段】行），
      正文开篇的【雨声】【内心独白】这类标签不会被误删；
    - 裁到最后一个【选项】标记为止——正文中途提到"选项"字样不会截断后续正文；
    - douluo 规则书用 `---` 分隔正文与选项，剥掉尾部残留的 `---` 行；
    - 自定义世界未必用【选项】标记：末尾 ≥2 行的 "A. 选项" 连排块一并去掉
      （单行引用/对白不受影响，因为不足 2 行）。
    """
    t = (text or "").lstrip()
    t = re.sub(r"^【[^】]*·[^】]*】\s*", "", t, count=1)
    t = t.rsplit("【选项】", 1)[0]
    lines = [ln for ln in t.split("\n")]
    while lines and lines[-1].strip() in ("", "---"):
        lines.pop()
    tail = 0
    for ln in reversed(lines):
        if _OPTION_LINE.match(ln):
            tail += 1
        else:
            break
    if tail >= 2:
        del lines[-tail:]
    return "\n".join(lines).strip()


def _prose_blocks(text: str) -> list[str]:
    """把叙述切成自然段（折叠多余空行与首尾空白）。"""
    return [p.strip() for p in text.split("\n") if p.strip()]


def _safe_filename_part(s: str) -> str:
    """文件名安全化：去掉 Windows/跨平台不允许的字符与空白，避免乱码文件名。"""
    return re.sub(r'[\\/:*?"<>|\r\n\t ]+', "-", s or "").strip("-") or "旅程"


def build_novel_markdown(state: dict, turns: list) -> dict:
    """把权威状态 + 回合记录整理成 Markdown 小说。

    纯函数，不碰磁盘（会话校验由调用方负责）：state 提供主角名与世界名，
    turns 提供按时间顺序的叙述正文。返回
    {title, content, filename, turns, chars}；turns=0 表示还没有可导出的剧情。
    """
    ch = state.get("character")
    name = ch.get("name") if isinstance(ch, dict) else None
    name = name or "无名"
    meta = state.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    world_id = meta.get("world_id") or "douluo"
    w = worlds.get_world(world_id)
    world_name = (w or {}).get("name") or meta.get("world_name") or "未知世界"
    world_desc = (w or {}).get("desc", "")

    now = datetime.now()
    title = f"《{world_name}》——{name}的一段旅程"

    narr = [t.get("narrative") for t in turns
            if isinstance(t, dict) and t.get("narrative")]
    if not narr:
        return {"title": title, "content": "", "filename": "", "turns": 0, "chars": 0}

    head = [f"# {title}", ""]
    if world_desc:
        head.append(f"> {world_desc}")
    head += [
        f"> 主角：{name} ｜ 世界：《{world_name}》 ｜ 导出时间：{now.strftime('%Y-%m-%d %H:%M')}",
        "> 这一段旅程由 AI 与你共同书写——下面是它在你一次次选择中落下的正文。",
        "",
    ]

    # 只收集真正有正文的场景，再用 --- 连接——纯元信息回合（只有地点头+选项）
    # 会被跳过，不会在文末留下悬空的 --- 分隔线。
    scenes: list[str] = []
    for n in narr:
        blocks = _prose_blocks(_strip_meta(n))
        if blocks:
            scenes.append("\n\n".join(blocks))
    if not scenes:
        return {"title": title, "content": "", "filename": "", "turns": 0, "chars": 0}

    content = "\n".join(head) + "\n\n---\n\n".join(scenes) + "\n"
    return {
        "title": title,
        "content": content,
        "filename": f"{_safe_filename_part(world_name)}-{_safe_filename_part(name)}-"
                    f"{now.strftime('%Y%m%d-%H%M')}.md",
        "turns": len(scenes),
        "chars": len(content),
    }
