"""平台 OCR · 基于 bbox 的软换行合并（无简历业务语义）。

同列、竖直相邻，且有强续写信号（半截尾或续写起笔）时合并文本与包围盒。
消费方可再做业务侧合行（ym-ats S0）；此处只做布局启发。

文本启发式（_CONT_HEAD_RE / _TRUNC_TAIL_RE）以 ym-ats
`backend/domain/matching/ocr/softWrap.py` 为 SSOT；改规则先改 ats 再对齐本文件。
"""

from __future__ import annotations

import re

__all__ = ["mergeSoftWrappedByBoxes"]

_SENTENCE_END_RE = re.compile(r"[。．.!！？；;…]$")
_NEW_ITEM_RE = re.compile(r"^(?:\d{1,2}[\.．、\)）]\s*|[·•\-–—*＊]\s+)")
_DATE_SPAN_RE = re.compile(
    r"^(?:20\d{2}|19\d{2})\s*[.\-/年]\s*\d{0,2}"
    r"|^(?<!\d)(?:20\d{2}|19\d{2})\s*[-–—至到~]"
)
# 文本续写启发式：与 ym-ats softWrap.CONT_HEAD_RE / TRUNC_TAIL_RE 对齐
_CONT_HEAD_RE = re.compile(
    r"^(?:"
    r"输出|调整|完成|进行|并向|向相关|并输出|并完成|"
    r"以及|同时|随后|然后|最终|并且|并在|并对|"
    r"使得|从而|因此|其中|包括|尤其|例如"
    r")"
)
_TRUNC_TAIL_RE = re.compile(r"[向并的与及领导都或且、,，的地得]$")


def _box_ok(b: list[int] | None) -> bool:
    if not b or len(b) < 4:
        return False
    x0, y0, x1, y1 = (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
    return x1 > x0 and y1 > y0


def _same_column(a: list[int], b: list[int], *, x_tol_ratio: float = 0.12) -> bool:
    aw = max(1, int(a[2]) - int(a[0]))
    tol = max(8, int(aw * x_tol_ratio))
    return abs(int(a[0]) - int(b[0])) <= tol


def _vertically_adjacent(
    a: list[int],
    b: list[int],
    *,
    max_gap_ratio: float = 0.85,
) -> bool:
    ah = max(1, int(a[3]) - int(a[1]))
    gap = int(b[1]) - int(a[3])
    if gap < -ah * 0.35:
        return False
    return gap <= ah * max_gap_ratio


def _merge_box(a: list[int], b: list[int]) -> list[int]:
    return [
        min(int(a[0]), int(b[0])),
        min(int(a[1]), int(b[1])),
        max(int(a[2]), int(b[2])),
        max(int(a[3]), int(b[3])),
    ]


def _prev_open(prev: str) -> bool:
    t = (prev or "").rstrip()
    if not t or len(t) < 4:
        return False
    return not bool(_SENTENCE_END_RE.search(t))


def _has_continuation_signal(prev: str, nxt: str) -> bool:
    """与 ym-ats softWrap._next_continues 对齐（另受 bbox 约束）。"""
    t = (nxt or "").strip()
    if not t:
        return False
    if _NEW_ITEM_RE.match(t):
        return False
    if _DATE_SPAN_RE.match(t) and len(t) <= 40:
        return False
    p = (prev or "").rstrip()
    strong_tail = bool(_TRUNC_TAIL_RE.search(p))
    strong_head = bool(_CONT_HEAD_RE.match(t))
    numbered_body = bool(_NEW_ITEM_RE.match(p))
    latin_cont = bool(t[0].isascii() and t[0].islower())
    if not (strong_tail or strong_head or numbered_body or latin_cont):
        return False
    if not strong_head and re.search(r"项目|课题|经历|公司", t):
        return False
    return True


def _join_text(a: str, b: str) -> str:
    if (
        a
        and b
        and a[-1].isascii()
        and a[-1].isalnum()
        and b[0].isascii()
        and b[0].isalnum()
    ):
        return f"{a} {b}"
    return f"{a}{b}"


def mergeSoftWrappedByBoxes(
    texts: list[str],
    boxes: list[list[int]] | None,
) -> tuple[list[str], list[list[int]], int]:
    """按 bbox 合并软换行。

    返回 (texts, boxes, merge_count)。
    boxes 缺失或与 texts 不对齐时原样返回（merge_count=0）。
    """
    if not texts:
        return [], list(boxes or []), 0
    if boxes is None or len(boxes) != len(texts):
        return list(texts), list(boxes or []), 0

    out_t: list[str] = []
    out_b: list[list[int]] = []
    buf_t = texts[0]
    buf_b = list(boxes[0])
    merges = 0

    for i in range(1, len(texts)):
        nxt_t = texts[i]
        nxt_b = list(boxes[i])
        can_geo = (
            _box_ok(buf_b)
            and _box_ok(nxt_b)
            and _same_column(buf_b, nxt_b)
            and _vertically_adjacent(buf_b, nxt_b)
        )
        if can_geo and _prev_open(buf_t) and _has_continuation_signal(buf_t, nxt_t):
            buf_t = _join_text(buf_t, nxt_t)
            buf_b = _merge_box(buf_b, nxt_b)
            merges += 1
        else:
            out_t.append(buf_t)
            out_b.append(buf_b)
            buf_t = nxt_t
            buf_b = nxt_b

    out_t.append(buf_t)
    out_b.append(buf_b)
    return out_t, out_b, merges
