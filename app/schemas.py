"""统一 OCR 响应契约：REST 与 MCP 共用，字段名对齐 Paddle 官方 prunedResult（snake_case）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OcrMeta(BaseModel):
    pages: int = 1
    elapsed_ms: int = 0
    model: str = "PP-OCRv6_small"
    extract_mode: str = "ocr"  # "text" | "ocr"
    # legacy | columns — 实际采用的阅读顺序（请求 layout=auto 时可能回退 legacy）
    reading_order: str = "legacy"
    # bbox 软换行合并次数（0=未合或无盒）
    soft_wrap_merges: int = 0


class OcrResponse(BaseModel):
    code: int = 200
    message: str = ""
    rec_texts: list[str] = Field(default_factory=list)
    rec_boxes: list[list[int]] = Field(default_factory=lambda: [[0, 0, 0, 0]])
    meta: OcrMeta = Field(default_factory=OcrMeta)
