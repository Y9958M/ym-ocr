"""统一 OCR 响应契约：REST 与 MCP 共用，字段名小驼峰。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OcrMeta(BaseModel):
    pages: int = 1
    elapsedMs: int = 0
    model: str = "PP-OCRv6_small"


class OcrResponse(BaseModel):
    code: int = 200
    message: str = ""
    fullText: str = ""
    recTexts: list[str] = Field(default_factory=list)
    recBoxes: list[list[int]] = Field(default_factory=lambda: [[0, 0, 0, 0]])
    meta: OcrMeta = Field(default_factory=OcrMeta)
