"""阅读顺序：legacy 整页 (y,x) vs 几何双栏（栏内自上而下、栏间左→右）。

用于 PDF 文本层 blocks 与 OCR rec_boxes；无简历业务语义。
layout:
  - legacy：保持历史 (y0, x0) 排序（默认，Boss 截图等）
  - columns：强制尝试分栏；检测失败则回退 legacy
  - auto：双峰明显才分栏，否则 legacy
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence, TypeVar

LayoutMode = Literal["legacy", "columns", "auto"]

T = TypeVar("T")


@dataclass(frozen=True)
class BoxItem:
    """带包围盒的文本项（中点用于分栏）。"""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    payload: object | None = None  # 可选保留原始 box

    @property
    def x_mid(self) -> float:
        return (self.x0 + self.x1) / 2.0


def normalize_layout(raw: str | None) -> LayoutMode:
    v = (raw or "legacy").strip().lower()
    if v in ("legacy", "columns", "auto"):
        return v  # type: ignore[return-value]
    return "legacy"


def detect_column_split(
    items: Sequence[BoxItem],
    *,
    page_width: float | None = None,
    min_left: int = 5,
    min_right: int = 5,
    min_gap_ratio: float = 0.06,
) -> float | None:
    """检测左右双栏竖缝（返回分界 x）；单栏或不明显则 None。

    在 x 中点直方图上找最大空隙；要求左右两侧都有足够块，且缝相对页宽够宽。
    """
    if len(items) < min_left + min_right:
        return None
    mids = sorted(it.x_mid for it in items)
    width = page_width
    if width is None or width <= 0:
        width = max(it.x1 for it in items) - min(it.x0 for it in items)
        if width <= 0:
            width = max(mids) - min(mids) or 1.0

    # 页边 8%～92% 内找最大相邻间隙
    lo, hi = width * 0.08, width * 0.92
    best_gap = 0.0
    best_split: float | None = None
    for a, b in zip(mids, mids[1:]):
        if a < lo or b > hi:
            continue
        gap = b - a
        if gap > best_gap:
            best_gap = gap
            best_split = (a + b) / 2.0

    if best_split is None:
        return None
    if best_gap < width * min_gap_ratio:
        return None

    n_left = sum(1 for it in items if it.x_mid < best_split)
    n_right = len(items) - n_left
    if n_left < min_left or n_right < min_right:
        return None
    # 避免一侧过碎（如页眉水印）：两侧占比至少约 15%
    if n_left / len(items) < 0.15 or n_right / len(items) < 0.15:
        return None
    return best_split


def _sort_legacy(items: Sequence[BoxItem]) -> list[BoxItem]:
    return sorted(items, key=lambda it: (round(it.y0, 0), round(it.x0, 0)))


def _sort_columns(items: Sequence[BoxItem], split: float) -> list[BoxItem]:
    left = [it for it in items if it.x_mid < split]
    right = [it for it in items if it.x_mid >= split]
    left_s = sorted(left, key=lambda it: (round(it.y0, 0), round(it.x0, 0)))
    right_s = sorted(right, key=lambda it: (round(it.y0, 0), round(it.x0, 0)))
    return left_s + right_s


def order_box_items(
    items: Sequence[BoxItem],
    *,
    layout: LayoutMode = "legacy",
    page_width: float | None = None,
) -> tuple[list[BoxItem], str]:
    """按 layout 排序；返回 (有序项, 实际采用的模式标签 legacy|columns)。"""
    if not items:
        return [], "legacy"
    mode = normalize_layout(layout)
    if mode == "legacy":
        return _sort_legacy(items), "legacy"

    split = detect_column_split(items, page_width=page_width)
    if split is None:
        return _sort_legacy(items), "legacy"
    if mode == "auto" or mode == "columns":
        return _sort_columns(items, split), "columns"
    return _sort_legacy(items), "legacy"


def order_texts_and_boxes(
    texts: Sequence[str],
    boxes: Sequence[Sequence[float | int]],
    *,
    layout: LayoutMode = "legacy",
    page_width: float | None = None,
) -> tuple[list[str], list[list[int]], str]:
    """对 OCR 行+box 对齐重排。"""
    n = min(len(texts), len(boxes))
    items: list[BoxItem] = []
    for i in range(n):
        b = boxes[i]
        if len(b) < 4:
            x0 = y0 = x1 = y1 = 0.0
        else:
            x0, y0, x1, y1 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
        items.append(
            BoxItem(
                text=str(texts[i]),
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                payload=[int(x0), int(y0), int(x1), int(y1)],
            )
        )
    # 多余文本无 box：legacy 追加末尾
    extras = [str(t) for t in texts[n:]]
    ordered, used = order_box_items(items, layout=layout, page_width=page_width)
    out_t = [it.text for it in ordered] + extras
    out_b: list[list[int]] = []
    for it in ordered:
        if isinstance(it.payload, list) and len(it.payload) >= 4:
            out_b.append([int(x) for x in it.payload[:4]])
        else:
            out_b.append([0, 0, 0, 0])
    out_b.extend([[0, 0, 0, 0] for _ in extras])
    return out_t, out_b, used
