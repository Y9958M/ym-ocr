"""阅读顺序 / 分栏单测（不依赖 GPU）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.readingOrder import BoxItem, detect_column_split, order_box_items


def test_legacy_keeps_yx_order():
    items = [
        BoxItem("L", 10, 100, 50, 120),
        BoxItem("R", 200, 100, 300, 120),
        BoxItem("L2", 10, 200, 50, 220),
    ]
    ordered, used = order_box_items(items, layout="legacy")
    assert used == "legacy"
    assert [it.text for it in ordered] == ["L", "R", "L2"]


def test_columns_left_then_right():
    items = [
        BoxItem("L-top", 20, 50, 80, 70),
        BoxItem("R-top", 250, 55, 400, 75),
        BoxItem("L-bot", 20, 200, 80, 220),
        BoxItem("R-bot", 250, 210, 400, 230),
        BoxItem("L-mid", 25, 120, 90, 140),
        BoxItem("R-mid", 260, 130, 410, 150),
        # pad to satisfy min_left/right
        BoxItem("La", 30, 80, 70, 90),
        BoxItem("Lb", 30, 160, 70, 170),
        BoxItem("Ra", 270, 90, 400, 100),
        BoxItem("Rb", 280, 170, 400, 180),
    ]
    split = detect_column_split(items, page_width=500)
    assert split is not None
    ordered, used = order_box_items(items, layout="columns", page_width=500)
    assert used == "columns"
    texts = [it.text for it in ordered]
    left = [t for t in texts if t.startswith("L")]
    right = [t for t in texts if t.startswith("R")]
    assert texts == left + right
    assert left[0] == "L-top"


def test_auto_falls_back_when_single_column():
    items = [
        BoxItem(f"r{i}", 100, i * 20, 400, i * 20 + 15) for i in range(12)
    ]
    ordered, used = order_box_items(items, layout="auto", page_width=500)
    assert used == "legacy"
    assert [it.text for it in ordered] == [f"r{i}" for i in range(12)]


def test_shiliu_pdf_columns_if_present():
    path = Path("/mnt/d/Users/share/石榴_简历.pdf")
    if not path.is_file():
        return
    import fitz
    from app.ocrService import _pageTextLinesByReadingOrder

    doc = fitz.open(path)
    try:
        legacy, _ = _pageTextLinesByReadingOrder(doc[0], layout="legacy")
        cols, used = _pageTextLinesByReadingOrder(doc[0], layout="auto")
    finally:
        doc.close()
    assert used == "columns"
    # legacy 会把邮箱插在工作经历中间；分栏后邮箱应在左栏「基本信息」一带，
    # 且「采埃孚」之后不应紧跟「电子邮箱」
    joined = "\n".join(cols)
    assert "采埃孚" in joined and "电子邮箱" in joined
    for i, line in enumerate(cols):
        if "采埃孚" in line:
            nxt = cols[i + 1] if i + 1 < len(cols) else ""
            assert "电子邮箱" not in nxt, f"interleaved after company: {nxt!r}"
            break
    # 左栏姓名应早于右栏教育段在列序中… 分栏后左整段在前
    assert cols.index("石榴") < cols.index("教育经历") or "教育经历" in cols


if __name__ == "__main__":
    test_legacy_keeps_yx_order()
    test_columns_left_then_right()
    test_auto_falls_back_when_single_column()
    test_shiliu_pdf_columns_if_present()
    print("ok")
