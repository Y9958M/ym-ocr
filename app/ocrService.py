"""OCR 核心服务：唯一真相，REST 与 MCP 都调这里。

图片：PIL → np.ndarray → engine.predict
PDF：优先 PyMuPDF 文本层；不足则逐页渲染 → engine.predict → 合并
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time
from functools import partial
from typing import Literal

import numpy as np
from PIL import Image

from app import engine
from app.config import modelLabel, settings
from app.readingOrder import (
    BoxItem,
    LayoutMode,
    normalize_layout,
    order_box_items,
    order_texts_and_boxes,
)
from app.schemas import OcrMeta, OcrResponse
from app.softWrap import mergeSoftWrappedByBoxes
from app.textNormalize import normalizeRecTexts

logger = logging.getLogger("ym-ocr")

_semaphore: asyncio.Semaphore | None = None

ExtractMode = Literal["text", "ocr"]

# Boss 直聘导出水印（含下划线），纯文本层 PDF 常见
_BOSS_WATERMARK_RE = re.compile(r"^[0-9A-Za-z_]{20,}$")


def _isPdfTextLayerNoiseLine(line: str) -> bool:
    """Boss 水印或 OCR 页脚碎片，不能当作有效文本层。"""
    t = (line or "").strip()
    if not t:
        return True
    if _BOSS_WATERMARK_RE.fullmatch(t):
        return True
    if len(t) <= 2 and t.isascii() and t.isalpha():
        return True
    return False


def _meaningfulPdfTextLines(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not _isPdfTextLayerNoiseLine(ln)]


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


def _pageTextLinesByReadingOrder(
    page,
    *,
    layout: LayoutMode = "legacy",
) -> tuple[list[str], str]:
    """按视觉阅读顺序提取文本行；返回 (lines, reading_order_used)。

    layout=legacy：blocks 按 (y0, x0)（历史行为）。
    layout=auto/columns：几何双栏时先左栏再右栏，各栏内自上而下。
    """
    blocks = page.get_text("blocks") or []
    text_blocks = [b for b in blocks if len(b) >= 7 and b[6] == 0]
    items: list[BoxItem] = []
    for b in text_blocks:
        text = (b[4] or "").strip()
        if not text:
            continue
        items.append(
            BoxItem(
                text=text,
                x0=float(b[0]),
                y0=float(b[1]),
                x1=float(b[2]),
                y1=float(b[3]),
            )
        )
    page_w = float(page.rect.width) if hasattr(page, "rect") else None
    ordered, used = order_box_items(items, layout=layout, page_width=page_w)
    lines: list[str] = []
    for it in ordered:
        for ln in it.text.splitlines():
            s = ln.strip()
            if s:
                lines.append(s)
    return lines, used


def _tryExtractPdfText(
    doc,
    *,
    layout: LayoutMode = "legacy",
) -> tuple[list[str], list[list[int]], int, str] | None:
    """尝试从 PDF 文本层提取；页均有效字符不足则返回 None（走 OCR）。

    返回 (texts, boxes, pages, reading_order_used)。
    """
    nPages = len(doc)
    if nPages <= 0:
        return None

    allTexts: list[str] = []
    used_order = "legacy"
    for i in range(nPages):
        lines, used = _pageTextLinesByReadingOrder(doc[i], layout=layout)
        allTexts.extend(lines)
        if used == "columns":
            used_order = "columns"
    if not allTexts:
        return None

    meaningful = _meaningfulPdfTextLines(allTexts)
    if not meaningful:
        return None

    avgMeaningful = sum(len(t) for t in meaningful) / nPages
    if avgMeaningful < settings.OCR_PDF_TEXT_MIN_CHARS_PER_PAGE:
        return None

    boxes = [[0, 0, 0, 0] for _ in meaningful]
    return meaningful, boxes, nPages, used_order


def _ocrPdfPages(
    doc,
    *,
    layout: LayoutMode = "legacy",
) -> tuple[list[str], list[list[int]], int, str]:
    """逐页渲染后 OCR；按 layout 重排。"""
    import fitz

    nPages = len(doc)
    mat = fitz.Matrix(settings.OCR_PDF_RENDER_SCALE, settings.OCR_PDF_RENDER_SCALE)
    allTexts: list[str] = []
    allBoxes: list[list[int]] = []
    used_order = "legacy"
    for i in range(nPages):
        page = doc[i]
        pix = page.get_pixmap(matrix=mat, alpha=False)
        arr = _pixmapToRgbArray(pix)
        texts, boxes = engine.predict(arr)
        page_w = float(page.rect.width) * settings.OCR_PDF_RENDER_SCALE
        texts, boxes, used = order_texts_and_boxes(
            texts, boxes, layout=layout, page_width=page_w
        )
        if used == "columns":
            used_order = "columns"
        allTexts.extend(texts)
        allBoxes.extend(boxes)
    return allTexts, allBoxes, nPages, used_order


def _recognizePdfSync(
    pdfBytes: bytes,
    *,
    layout: LayoutMode = "legacy",
) -> tuple[list[str], list[list[int]], int, ExtractMode, str]:
    """多页 PDF：优先文本层，不足则 OCR。"""
    import fitz

    mode = normalize_layout(layout)
    doc = fitz.open(stream=pdfBytes, filetype="pdf")
    try:
        nPages = len(doc)
        if nPages <= 0:
            return [], [[0, 0, 0, 0]], 0, "ocr", "legacy"
        if nPages > settings.OCR_PDF_MAX_PAGES:
            raise ValueError(f"PDF 页数超过上限 ({settings.OCR_PDF_MAX_PAGES})")

        if settings.OCR_PDF_PREFER_TEXT:
            extracted = _tryExtractPdfText(doc, layout=mode)
            if extracted is not None:
                texts, boxes, pages, used = extracted
                return texts, boxes, pages, "text", used

        texts, boxes, pages, used = _ocrPdfPages(doc, layout=mode)
        return texts, boxes, pages, "ocr", used
    finally:
        doc.close()


def _recognizeImageSync(
    imageBytes: bytes,
    *,
    layout: LayoutMode = "legacy",
) -> tuple[list[str], list[list[int]], int, ExtractMode, str]:
    """单图同步识别。"""
    image = Image.open(io.BytesIO(imageBytes)).convert("RGB")
    arr = np.array(image)
    texts, boxes = engine.predict(arr)
    page_w = float(arr.shape[1]) if arr.ndim >= 2 else None
    texts, boxes, used = order_texts_and_boxes(
        texts, boxes, layout=normalize_layout(layout), page_width=page_w
    )
    return texts, boxes, 1, "ocr", used


def _isPdf(filename: str) -> bool:
    return (filename or "").lower().endswith(".pdf")


def _buildResponse(
    texts: list[str],
    boxes: list[list[int]],
    pages: int,
    elapsed_ms: int,
    extract_mode: ExtractMode = "ocr",
    reading_order: str = "legacy",
) -> OcrResponse:
    label = modelLabel()
    soft_wrap_merges = 0
    if settings.OCR_TEXT_NORMALIZE:
        texts, boxes = normalizeRecTexts(texts, boxes)
    if settings.OCR_SOFT_WRAP:
        texts, boxes, soft_wrap_merges = mergeSoftWrappedByBoxes(texts, boxes)
    if not texts:
        return OcrResponse(
            code=400,
            message="未识别到文本",
            meta=OcrMeta(
                pages=pages,
                elapsed_ms=elapsed_ms,
                model=label,
                extract_mode=extract_mode,
                reading_order=reading_order,
                soft_wrap_merges=soft_wrap_merges,
            ),
        )
    boxes_out = boxes if boxes else [[0, 0, 0, 0]]
    return OcrResponse(
        rec_texts=texts,
        rec_boxes=boxes_out,
        meta=OcrMeta(
            pages=pages,
            elapsed_ms=elapsed_ms,
            model=label,
            extract_mode=extract_mode,
            reading_order=reading_order,
            soft_wrap_merges=soft_wrap_merges,
        ),
    )


def _shortFile(name: str, maxLen: int = 36) -> str:
    n = (name or "-").replace("\n", " ")
    return n if len(n) <= maxLen else n[: maxLen - 1] + "…"


def _shortModel(label: str) -> str:
    """PP-OCRv6_small_det+PP-OCRv6_medium_rec → small+medium；同档 → small。"""
    s = (label or "").replace("PP-OCRv6_", "")
    s = s.replace("_det", "").replace("_rec", "")
    return s or "-"


def _logResult(
    *,
    caller: str,
    via: str,
    filename: str,
    bytes_len: int,
    res: OcrResponse,
) -> None:
    # 单行：ocr ym-ats rest lpList.png 595k 124L 1p text cols 1214ms small+medium
    kb = max(1, (bytes_len + 512) // 1024)
    pages = res.meta.pages
    pagePart = f" {pages}p" if pages != 1 else ""
    modePart = f" {res.meta.extract_mode}" if res.meta.extract_mode else ""
    orderPart = (
        f" {res.meta.reading_order}"
        if res.meta.reading_order and res.meta.reading_order != "legacy"
        else ""
    )
    err = f" ERR {res.message}" if res.code != 200 and res.message else ""
    logger.info(
        "ocr %s %s %s %dk %dL%s%s%s %dms %s%s",
        caller or "-",
        via,
        _shortFile(filename),
        kb,
        len(res.rec_texts),
        pagePart,
        modePart,
        orderPart,
        res.meta.elapsed_ms,
        _shortModel(res.meta.model),
        err,
    )


async def recognize(
    fileBytes: bytes,
    filename: str,
    *,
    caller: str = "",
    via: str = "unknown",
    layout: str = "legacy",
) -> OcrResponse:
    """统一入口：根据文件名分发图片/PDF，限流 + 线程池执行。

    layout: legacy（默认）| columns | auto — 见 app.readingOrder
    """
    started = time.monotonic()
    isPdf = _isPdf(filename)
    extract_mode: ExtractMode = "ocr"
    reading_order = "legacy"
    layout_mode = normalize_layout(layout)
    try:
        async with _sem():
            loop = asyncio.get_running_loop()
            if isPdf:
                texts, boxes, pages, extract_mode, reading_order = (
                    await loop.run_in_executor(
                        None,
                        partial(_recognizePdfSync, fileBytes, layout=layout_mode),
                    )
                )
            else:
                texts, boxes, pages, extract_mode, reading_order = (
                    await loop.run_in_executor(
                        None,
                        partial(_recognizeImageSync, fileBytes, layout=layout_mode),
                    )
                )
    except Exception as e:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        res = OcrResponse(
            code=400,
            message=str(e),
            meta=OcrMeta(
                pages=0,
                elapsed_ms=elapsed_ms,
                model=modelLabel(),
                extract_mode=extract_mode,
                reading_order=reading_order,
            ),
        )
        _logResult(
            caller=caller, via=via, filename=filename, bytes_len=len(fileBytes), res=res
        )
        return res
    elapsed_ms = int((time.monotonic() - started) * 1000)
    res = _buildResponse(
        texts, boxes, pages, elapsed_ms, extract_mode, reading_order=reading_order
    )
    _logResult(
        caller=caller, via=via, filename=filename, bytes_len=len(fileBytes), res=res
    )
    return res


async def recognizeFromPath(
    filePath: str,
    *,
    caller: str = "",
    via: str = "mcp",
    layout: str = "legacy",
) -> OcrResponse:
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

    return await recognize(
        data, Path(path).name, caller=caller, via=via, layout=layout
    )
