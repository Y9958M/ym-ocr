"""ym-ocr 启动入口：uv run ocr.py

REST: http://{host}:{port}/v1/ocr
MCP:  http://{host}:{port}/mcp
"""

from __future__ import annotations

import uvicorn

from app.config import modelLabel, settings


def main() -> None:
    host = settings.YM_OCR_HOST
    port = settings.YM_OCR_PORT
    print(f"[ym-ocr] 启动 http://{host}:{port}")
    print(f"[ym-ocr] REST /v1/ocr  MCP /mcp  model={modelLabel()}")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
