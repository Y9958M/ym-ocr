"""OCR 核心服务：唯一真相，REST 与 MCP 都调这里。

图片：PIL → np.ndarray → engine.predict
PDF：PyMuPDF 逐页渲染 → engine.predict → 合并
"""

from __future__ import annotations

import asyncio
import io
import time

import numpy as np
from PIL import Image

from app import engine
from app.config import settings
from app.schemas import OcrMeta, OcrResponse

_semaphore: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    """延迟创建 Semaphore，避免在 import 时绑定错误的事件循环。"""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.OCR_MAX_CONCURRENT)
    return _semaphore


def _pixmapToRgbArray(pix) -> np.ndarray:
    """PyMuPDF Pixmap → HWC uint8 RGB，供 PaddleOCR.predict。"""
    h, w, n = pix.height, pix.width, pix.n
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(h, w, n)
    if n >= 3:
        return np.ascontiguousarray(arr[:, :, :3])
    if n == 1:
        g = arr[:, :, 0]
        return np.stack([g, g, g], axis=-1)
    raise ValueError(f"不支持的 pixmap 通道数: {n}")


def _recognizeImageSync(imageBytes: bytes) -> tuple[list[str], list[list[int]], int]:
    """单图同步识别，返回 (texts, boxes, pages)。在线程池中执行。"""
    image = Image.open(io.BytesIO(imageBytes)).convert("RGB")
    texts, boxes = engine.predict(np.array(image))
    return texts, boxes, 1


def _recognizePdfSync(pdfBytes: bytes) -> tuple[list[str], list[list[int]], int]:
    """多页 PDF 同步识别，返回合并后的 (texts, boxes, pages)。"""
    import fitz

    doc = fitz.open(stream=pdfBytes, filetype="pdf")
    try:
        nPages = len(doc)
        if nPages <= 0:
            return [], [[0, 0, 0, 0]], 0
        if nPages > settings.OCR_PDF_MAX_PAGES:
            raise ValueError(f"PDF 页数超过上限 ({settings.OCR_PDF_MAX_PAGES})")

        mat = fitz.Matrix(settings.OCR_PDF_RENDER_SCALE, settings.OCR_PDF_RENDER_SCALE)
        allTexts: list[str] = []
        allBoxes: list[list[int]] = []
        for i in range(nPages):
            pix = doc[i].get_pixmap(matrix=mat, alpha=False)
            arr = _pixmapToRgbArray(pix)
            texts, boxes = engine.predict(arr)
            allTexts.extend(texts)
            allBoxes.extend(boxes)
        return allTexts, allBoxes, nPages
    finally:
        doc.close()


def _isPdf(filename: str) -> bool:
    return (filename or "").lower().endswith(".pdf")


def _buildResponse(
    texts: list[str],
    boxes: list[list[int]],
    pages: int,
    elapsedMs: int,
) -> OcrResponse:
    if not texts:
        return OcrResponse(
            code=400,
            message="未识别到文本",
            meta=OcrMeta(pages=pages, elapsedMs=elapsedMs, model=settings.OCR_MODEL),
        )
    boxesOut = boxes if boxes else [[0, 0, 0, 0]]
    return OcrResponse(
        fullText="\n".join(texts),
        recTexts=texts,
        recBoxes=boxesOut,
        meta=OcrMeta(pages=pages, elapsedMs=elapsedMs, model=settings.OCR_MODEL),
    )


async def recognize(fileBytes: bytes, filename: str) -> OcrResponse:
    """统一入口：根据文件名分发图片/PDF，限流 + 线程池执行。"""
    started = time.monotonic()
    isPdf = _isPdf(filename)
    try:
        async with _sem():
            loop = asyncio.get_running_loop()
            if isPdf:
                texts, boxes, pages = await loop.run_in_executor(
                    None, _recognizePdfSync, fileBytes
                )
            else:
                texts, boxes, pages = await loop.run_in_executor(
                    None, _recognizeImageSync, fileBytes
                )
    except Exception as e:
        elapsedMs = int((time.monotonic() - started) * 1000)
        return OcrResponse(
            code=400,
            message=str(e),
            meta=OcrMeta(pages=0, elapsedMs=elapsedMs, model=settings.OCR_MODEL),
        )
    elapsedMs = int((time.monotonic() - started) * 1000)
    return _buildResponse(texts, boxes, pages, elapsedMs)


async def recognizeFromPath(filePath: str) -> OcrResponse:
    """从本机文件路径识别（MCP tool 用）。"""
    path = filePath.strip()
    if not path:
        return OcrResponse(code=400, message="file_path 为空")
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return OcrResponse(code=400, message=f"读取文件失败: {e}")
    from pathlib import Path

    return await recognize(data, Path(path).name)
