"""PDF 文本层优先提取单测（不依赖 GPU / PaddleOCR）。

用法：
    uv run python -m pytest tests/test_pdf_text_extract.py -q
    # 或无 pytest 时：
    uv run python tests/test_pdf_text_extract.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SAMPLE_PDF = Path(
    "/mnt/d/OneDrive/猎头/【架构师-AI智能体（Agent）_杭州 100-200K】王翔 10年以上.pdf"
)
LI_PDF = Path(
    "/mnt/d/OneDrive/猎头/【架构师-AI智能体（Agent）_杭州 100-200K】李先生 10年以上.pdf"
)
FEIWEN_PDF = Path(
    "/mnt/d/OneDrive/猎头/【射频⼯程师RF --上海_上海 25-35K】飞文 1年.pdf"
)
WATERMARK = "7aaa920c0240668a1HJ70tm4GVBXxIW9U_KWWOGhlv7XNxdq"


def _make_watermark_only_pdf() -> bytes:
    """模拟 Boss 图片型 PDF：文本层仅含水印。"""
    import fitz

    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_text((72, 72), f"{WATERMARK}\ndq\nq\n{WATERMARK}\n")
    data = doc.tobytes()
    doc.close()
    return data


def _make_text_pdf() -> bytes:
    """内存构造带文本层的单页 PDF（ASCII，避免缺中文字体）。"""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    # 足够超过 OCR_PDF_TEXT_MIN_CHARS_PER_PAGE（默认 30）
    page.insert_text(
        (72, 72),
        "Education Background\nUniversity of Melbourne\nMaster of Information Technology\n",
    )
    data = doc.tobytes()
    doc.close()
    return data


def _make_empty_pdf() -> bytes:
    """无文本层的空白 PDF（模拟扫描件）。"""
    import fitz

    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def test_try_extract_text_pdf():
    from app.ocrService import _tryExtractPdfText
    import fitz

    doc = fitz.open(stream=_make_text_pdf(), filetype="pdf")
    try:
        result = _tryExtractPdfText(doc)
    finally:
        doc.close()
    assert result is not None
    texts, boxes, pages, _order = result
    assert pages == 1
    joined = "\n".join(texts)
    assert "Education Background" in joined
    assert "University of Melbourne" in joined
    assert len(boxes) == len(texts)


def test_try_extract_empty_pdf_returns_none():
    from app.ocrService import _tryExtractPdfText
    import fitz

    doc = fitz.open(stream=_make_empty_pdf(), filetype="pdf")
    try:
        result = _tryExtractPdfText(doc)
    finally:
        doc.close()
    assert result is None


def test_recognize_pdf_prefer_text_mode():
    from app.ocrService import _recognizePdfSync

    texts, boxes, pages, mode, _order = _recognizePdfSync(_make_text_pdf())
    assert mode == "text"
    assert pages == 1
    assert any("Melbourne" in t for t in texts)
    assert len(boxes) == len(texts)


def test_try_extract_watermark_only_pdf_returns_none():
    from app.ocrService import _tryExtractPdfText
    import fitz

    doc = fitz.open(stream=_make_watermark_only_pdf(), filetype="pdf")
    try:
        result = _tryExtractPdfText(doc)
    finally:
        doc.close()
    assert result is None


def test_recognize_watermark_only_pdf_falls_back_to_ocr():
    """水印 PDF 须回退 OCR；无 GPU 时跳过。"""
    from app.ocrService import _recognizePdfSync

    try:
        texts, _boxes, pages, mode, _order = _recognizePdfSync(
            _make_watermark_only_pdf()
        )
    except RuntimeError:
        return  # engine 未初始化
    assert mode == "ocr"
    assert pages == 2


def test_wangxiang_pdf_text_extract_if_present():
    """可选：本机有王翔 PDF 时做端到端文本层断言。"""
    if not SAMPLE_PDF.is_file():
        return
    from app.ocrService import _recognizePdfSync

    data = SAMPLE_PDF.read_bytes()
    texts, _boxes, pages, mode, _order = _recognizePdfSync(data)
    joined = "\n".join(texts)
    assert mode == "text"
    assert pages == 9
    assert len(joined) > 10000
    assert "教育背景" in joined
    assert "墨尔本大学" in joined


def test_li_pdf_ocr_fallback_if_present():
    """Boss 图片型 PDF：须走 OCR 而非水印文本层。"""
    if not LI_PDF.is_file():
        return
    from app.engine import initEngine
    from app.ocrService import _recognizePdfSync

    initEngine()
    data = LI_PDF.read_bytes()
    texts, _boxes, pages, mode, _order = _recognizePdfSync(data)
    joined = "\n".join(texts)
    assert mode == "ocr"
    assert pages == 4
    assert len(joined) > 1000
    assert "李" in joined


def test_feiwen_pdf_reading_order_if_present():
    """WPS 简历：标题须出现在对应内容之前（按坐标排序）。"""
    if not FEIWEN_PDF.is_file():
        return
    from app.ocrService import _recognizePdfSync

    texts, _boxes, pages, mode, _order = _recognizePdfSync(FEIWEN_PDF.read_bytes())
    assert mode == "text"
    assert pages == 1
    joined = "\n".join(texts)
    assert joined.index("个人信息") < joined.index("名：飞文")
    assert joined.index("教育背景") < joined.index("上海大学")
    assert joined.index("工作经历") < joined.index("上海龙旗科技股份有限公司")
    assert joined.index("项目经历") < joined.index("中瑞先进技术研究院")


if __name__ == "__main__":
    test_try_extract_text_pdf()
    test_try_extract_empty_pdf_returns_none()
    test_try_extract_watermark_only_pdf_returns_none()
    test_recognize_pdf_prefer_text_mode()
    test_wangxiang_pdf_text_extract_if_present()
    test_li_pdf_ocr_fallback_if_present()
    test_feiwen_pdf_reading_order_if_present()
    print("PASS")
