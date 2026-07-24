"""字形减噪单测（不依赖 GPU / PaddleOCR）。

用法：
    uv run python -m pytest tests/test_text_normalize.py -q
    # 或：
    uv run python tests/test_text_normalize.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_nfkc_kangxi_radicals():
    from app.textNormalize import normalizeOcrText

    assert normalizeOcrText("上海海事⼤学") == "上海海事大学"
    assert normalizeOcrText("轮机⼯程") == "轮机工程"
    assert normalizeOcrText("硕⼠") == "硕士"
    assert normalizeOcrText("2025.07 - ⾄今") == "2025.07 - 至今"


def test_fullwidth_alnum_and_punct():
    from app.textNormalize import normalizeOcrText

    assert normalizeOcrText("本科５年Ｊａｖａ") == "本科5年Java"
    assert normalizeOcrText("经验，五年（含实习）") == "经验,五年(含实习)"
    assert normalizeOcrText("2022.09—2025.06") == "2022.09-2025.06"


def test_strips_zwsp_soft_hyphen():
    from app.textNormalize import normalizeOcrText

    assert normalizeOcrText("南洋理工\u200b大学") == "南洋理工大学"
    assert normalizeOcrText("soft\u00adhyphen") == "softhyphen"


def test_keeps_duty_bullets():
    """平台 OCR 不把 ·•● 改成空格（与 apiYmy 简历流水线刻意不同）。"""
    from app.textNormalize import normalizeOcrText

    assert normalizeOcrText("· 负责热仿真") == "· 负责热仿真"
    assert normalizeOcrText("• 参与结构设计") == "• 参与结构设计"
    assert normalizeOcrText("● 研究方向") == "● 研究方向"


def test_normalize_rec_texts_aligns_boxes():
    from app.textNormalize import normalizeRecTexts

    texts = ["上海海事⼤学", "\u200b", "硕⼠"]
    boxes = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
    out_t, out_b = normalizeRecTexts(texts, boxes)
    assert out_t == ["上海海事大学", "硕士"]
    assert out_b == [[1, 2, 3, 4], [9, 10, 11, 12]]


def test_idempotent():
    from app.textNormalize import normalizeOcrText

    s = normalizeOcrText("上海海事⼤学／本科５年")
    assert normalizeOcrText(s) == s


def test_build_response_applies_normalize(monkeypatch=None):
    from app import config
    from app.ocrService import _buildResponse

    # 默认开启
    assert config.settings.OCR_TEXT_NORMALIZE is True
    res = _buildResponse(
        ["上海海事⼤学", "硕⼠"],
        [[0, 0, 1, 1], [0, 0, 2, 2]],
        pages=1,
        elapsed_ms=1,
        extract_mode="ocr",
    )
    assert res.code == 200
    assert res.rec_texts == ["上海海事大学", "硕士"]


if __name__ == "__main__":
    test_nfkc_kangxi_radicals()
    test_fullwidth_alnum_and_punct()
    test_strips_zwsp_soft_hyphen()
    test_keeps_duty_bullets()
    test_normalize_rec_texts_aligns_boxes()
    test_idempotent()
    test_build_response_applies_normalize()
    print("ok")
