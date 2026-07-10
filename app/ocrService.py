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
from typing import Literal

import numpy as np
from PIL import Image

from app import engine
from app.config import modelLabel, settings
from app.schemas import OcrMeta, OcrResponse

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


def _recognizeImageSync(imageBytes: bytes) -> tuple[list[str], list[list[int]], int, ExtractMode]:
    """单图同步识别，返回 (texts, boxes, pages, mode)。在线程池中执行。"""
    image = Image.open(io.BytesIO(imageBytes)).convert("RGB")
    texts, boxes = engine.predict(np.array(image))
    return texts, boxes, 1, "ocr"


def _pageTextLinesByReadingOrder(page) -> list[str]:
    """按视觉阅读顺序（上→下、左→右）提取文本行。

    `get_text("text")` 跟随 PDF 内容流，WPS/复杂排版常把标题写在内容之后，
    导致「项目经历」出现在项目正文后面。改用 blocks 按 (y0, x0) 排序。
    """
    blocks = page.get_text("blocks") or []
    # block: (x0, y0, x1, y1, text, block_no, block_type)；0=文本
    text_blocks = [b for b in blocks if len(b) >= 7 and b[6] == 0]
    text_blocks.sort(key=lambda b: (round(float(b[1]), 0), round(float(b[0]), 0)))
    lines: list[str] = []
    for b in text_blocks:
        for ln in (b[4] or "").splitlines():
            s = ln.strip()
            if s:
                lines.append(s)
    return lines


def _tryExtractPdfText(
    doc,
) -> tuple[list[str], list[list[int]], int] | None:
    """尝试从 PDF 文本层提取；页均有效字符不足则返回 None（走 OCR）。

    Boss 图片型 PDF 常带水印文本层（页均 ~150 字符），须过滤后再判阈值。
    文本行按页面坐标排序，避免内容流乱序。
    """
    nPages = len(doc)
    if nPages <= 0:
        return None

    allTexts: list[str] = []
    for i in range(nPages):
        allTexts.extend(_pageTextLinesByReadingOrder(doc[i]))
    if not allTexts:
        return None

    meaningful = _meaningfulPdfTextLines(allTexts)
    if not meaningful:
        return None

    avgMeaningful = sum(len(t) for t in meaningful) / nPages
    if avgMeaningful < settings.OCR_PDF_TEXT_MIN_CHARS_PER_PAGE:
        return None

    boxes = [[0, 0, 0, 0] for _ in meaningful]
    return meaningful, boxes, nPages


def _ocrPdfPages(doc) -> tuple[list[str], list[list[int]], int]:
    """逐页渲染后 OCR。"""
    import fitz

    nPages = len(doc)
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


def _recognizePdfSync(
    pdfBytes: bytes,
) -> tuple[list[str], list[list[int]], int, ExtractMode]:
    """多页 PDF：优先文本层，不足则 OCR。返回 (texts, boxes, pages, mode)。"""
    import fitz

    doc = fitz.open(stream=pdfBytes, filetype="pdf")
    try:
        nPages = len(doc)
        if nPages <= 0:
            return [], [[0, 0, 0, 0]], 0, "ocr"
        if nPages > settings.OCR_PDF_MAX_PAGES:
            raise ValueError(f"PDF 页数超过上限 ({settings.OCR_PDF_MAX_PAGES})")

        if settings.OCR_PDF_PREFER_TEXT:
            extracted = _tryExtractPdfText(doc)
            if extracted is not None:
                texts, boxes, pages = extracted
                return texts, boxes, pages, "text"

        texts, boxes, pages = _ocrPdfPages(doc)
        return texts, boxes, pages, "ocr"
    finally:
        doc.close()


def _isPdf(filename: str) -> bool:
    return (filename or "").lower().endswith(".pdf")


def _buildResponse(
    texts: list[str],
    boxes: list[list[int]],
    pages: int,
    elapsed_ms: int,
    extract_mode: ExtractMode = "ocr",
) -> OcrResponse:
    label = modelLabel()
    if not texts:
        return OcrResponse(
            code=400,
            message="未识别到文本",
            meta=OcrMeta(
                pages=pages,
                elapsed_ms=elapsed_ms,
                model=label,
                extract_mode=extract_mode,
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
    # 单行：ocr ym-ats rest lpList.png 595k 124L 1p text 1214ms small+medium
    kb = max(1, (bytes_len + 512) // 1024)
    pages = res.meta.pages
    pagePart = f" {pages}p" if pages != 1 else ""
    modePart = f" {res.meta.extract_mode}" if res.meta.extract_mode else ""
    err = f" ERR {res.message}" if res.code != 200 and res.message else ""
    logger.info(
        "ocr %s %s %s %dk %dL%s%s %dms %s%s",
        caller or "-",
        via,
        _shortFile(filename),
        kb,
        len(res.rec_texts),
        pagePart,
        modePart,
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
) -> OcrResponse:
    """统一入口：根据文件名分发图片/PDF，限流 + 线程池执行。"""
    started = time.monotonic()
    isPdf = _isPdf(filename)
    extract_mode: ExtractMode = "ocr"
    try:
        async with _sem():
            loop = asyncio.get_running_loop()
            if isPdf:
                texts, boxes, pages, extract_mode = await loop.run_in_executor(
                    None, _recognizePdfSync, fileBytes
                )
            else:
                texts, boxes, pages, extract_mode = await loop.run_in_executor(
                    None, _recognizeImageSync, fileBytes
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
            ),
        )
        _logResult(
            caller=caller, via=via, filename=filename, bytes_len=len(fileBytes), res=res
        )
        return res
    elapsed_ms = int((time.monotonic() - started) * 1000)
    res = _buildResponse(texts, boxes, pages, elapsed_ms, extract_mode)
    _logResult(
        caller=caller, via=via, filename=filename, bytes_len=len(fileBytes), res=res
    )
    return res


async def recognizeFromPath(
    filePath: str,
    *,
    caller: str = "",
    via: str = "mcp",
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

    return await recognize(data, Path(path).name, caller=caller, via=via)
