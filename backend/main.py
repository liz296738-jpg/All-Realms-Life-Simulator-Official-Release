"""《万界人生模拟器》后端 — FastAPI 入口。"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router

load_dotenv()

app = FastAPI(title="万界人生模拟器 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ── 旧架构残留：选项块剥离 ─────────────────────────────────
# 用于叙述自愈的判空基准（整段是选项清单时剥完为空 → 触发重试），以及历史/结算的干净正文。
# 新架构（_call_turn 统一 JSON 调用）中已不再使用，保留以备回退。
def _strip_options_block(text: str) -> str:
    """去掉叙述末尾的选项块（【选项】标记段 或 结尾连排的选项行），与前端 stripOptionsBlock 一致。

    模型可能按规则书在正文后附选项；正文照常入库，选项由结算 JSON 的 options 提供。
    用于：叙述自愈的判空基准（整段是选项清单时剥完为空 → 触发重试），以及历史/结算的干净正文。
    """
    t = (text or "").replace("\r\n", "\n")
    idx = t.rfind("【选项】")
    if idx >= 0:
        t = t[:idx]
    lines = t.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    tail = 0
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if len(s) >= 2 and s[0] in "ABCDabcd" and s[1] in ".、．":
            tail += 1
        else:
            break
    if tail >= 2:
        lines = lines[:-tail]
    return "\n".join(lines).strip()


app.include_router(api_router)

# ── 生产模式：托管前端构建产物 ────────────────────────────
# dev 时前端由 vite 提供（:5173 + /api 代理）；生产部署（Render）
# 时由后端同源托管 frontend/dist。此 mount 置于所有 API 路由之后，
# 因此 /api/* 优先命中，其余路径（首页与 /assets/*）回落到静态文件。
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
