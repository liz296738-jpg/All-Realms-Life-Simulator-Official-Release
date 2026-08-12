# ── 阶段 1：构建前端（bun，锁文件 bun.lock 保证可复现）─────
FROM oven/bun:1 AS frontend
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

# ── 阶段 2：后端运行时（Python）──────────────────────────
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=frontend /app/dist ./frontend/dist
COPY backend/ ./backend
WORKDIR /app/backend
RUN pip install --no-cache-dir -r requirements.txt
ENV PORT=10000
EXPOSE 10000
# Render 会注入 DEEPSEEK_API_KEY 与 PORT 环境变量
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}
