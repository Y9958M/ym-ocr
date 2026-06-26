"""ym-ocr 入口：FastAPI + mount /mcp + Bearer 鉴权 middleware。

启动：
    .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
REST: http://127.0.0.1:8001/v1/ocr
MCP:  http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import engine
from app.config import settings
from app.mcpServer import mcp
from app.rest import router as restRouter

# MCP 的 ASGI app（Streamable HTTP），mount 到 /mcp
# 官方 mcp 包用 streamable_http_app()，返回 Starlette app（自带 lifespan）
mcpApp = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时加载 PaddleOCR 单例 + 启动 MCP session manager。"""
    engine.initEngine()
    async with mcp.session_manager.run():
        yield
    engine.shutdownEngine()


app = FastAPI(
    title="ym-ocr",
    description="平台 OCR 服务：PP-OCRv6 + REST + MCP",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/mcp", mcpApp)
app.include_router(restRouter)


# ── Bearer 鉴权 middleware ──────────────────────────────────────────────
# /health 放行；其余路径要求 Authorization: Bearer <YM_OCR_API_KEY>
# 未配置 YM_OCR_API_KEY 时不鉴权（仅内网调试）
_PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def authMiddleware(request: Request, call_next):
    apiKey = settings.YM_OCR_API_KEY.strip()
    if not apiKey:
        return await call_next(request)

    path = request.url.path
    if path in _PUBLIC_PATHS:
        return await call_next(request)

    # /mcp 与 REST 统一走 Bearer 校验（Hermes config headers 会带 Bearer）
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
    if not secrets.compare_digest(token or "", apiKey):
        return JSONResponse({"code": 401, "message": "无效或缺失 API Key"}, status_code=401)
    return await call_next(request)
