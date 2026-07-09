"""ym-ocr 启动入口：uv run ocr.py

REST: http://{host}:{port}/v1/ocr
MCP:  http://{host}:{port}/mcp
"""

from __future__ import annotations

import uvicorn

from app.config import modelLabel, settings

# 精简：单行时间+消息；关掉 access（业务日志已含 caller）
_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "short": {
            "format": "%(asctime)s %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "short",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["default"], "level": "WARNING", "propagate": False},
        "ym-ocr": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "httpx": {"handlers": ["default"], "level": "WARNING", "propagate": False},
    },
    "root": {"handlers": ["default"], "level": "WARNING"},
}


def main() -> None:
    host = settings.YM_OCR_HOST
    port = settings.YM_OCR_PORT
    print(f"[ym-ocr] http://{host}:{port}  model={modelLabel()}")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
        access_log=False,
        log_config=_LOG_CONFIG,
    )


if __name__ == "__main__":
    main()
