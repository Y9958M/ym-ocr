"""bbox 软换行合并单测（不依赖 GPU）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_merge_by_boxes_continuation():
    from app.softWrap import mergeSoftWrappedByBoxes

    texts = [
        "进行电源方案可行性评估。向相关领",
        "输出方案可行性报告。",
        "2.项目初期完成设计",
    ]
    # 同列、相邻行
    boxes = [
        [10, 10, 200, 24],
        [12, 26, 180, 40],
        [10, 50, 190, 64],
    ]
    out_t, out_b, n = mergeSoftWrappedByBoxes(texts, boxes)
    assert n == 1
    assert len(out_t) == 2
    assert "向相关领输出方案可行性报告。" in out_t[0]
    assert out_t[1].startswith("2.")
    assert out_b[0] == [10, 10, 200, 40]


def test_no_merge_without_boxes():
    from app.softWrap import mergeSoftWrappedByBoxes

    texts = ["向相关领", "输出方案可行性报告。"]
    out_t, out_b, n = mergeSoftWrappedByBoxes(texts, None)
    assert n == 0
    assert out_t == texts


def test_no_merge_across_columns():
    from app.softWrap import mergeSoftWrappedByBoxes

    texts = ["向相关领", "输出方案可行性报告。"]
    boxes = [
        [10, 10, 100, 24],
        [300, 26, 400, 40],  # 右栏
    ]
    out_t, _, n = mergeSoftWrappedByBoxes(texts, boxes)
    assert n == 0
    assert out_t == texts


def test_no_merge_new_numbered_item():
    from app.softWrap import mergeSoftWrappedByBoxes

    texts = ["完成前期评估,", "1.开始详细设计"]
    boxes = [[10, 10, 200, 24], [10, 26, 180, 40]]
    out_t, _, n = mergeSoftWrappedByBoxes(texts, boxes)
    assert n == 0
    assert out_t == texts


def test_merge_numbered_list_body_wrap():
    from app.softWrap import mergeSoftWrappedByBoxes

    texts = [
        "2、 拥有服务器SI PI全流程设计经验;具备主板",
        "设计及检视能力。",
        "3、拥有手机经验",
    ]
    boxes = [
        [10, 10, 220, 24],
        [12, 26, 180, 40],
        [10, 50, 200, 64],
    ]
    out_t, _, n = mergeSoftWrappedByBoxes(texts, boxes)
    assert n == 1
    assert len(out_t) == 2
    assert "主板设计及检视能力。" in out_t[0]
    assert out_t[1].startswith("3、")


def test_build_response_soft_wrap_meta():
    from app.ocrService import _buildResponse

    res = _buildResponse(
        ["向相关领", "输出方案可行性报告。"],
        [[10, 10, 200, 24], [12, 26, 180, 40]],
        pages=1,
        elapsed_ms=1,
        extract_mode="ocr",
    )
    assert res.code == 200
    assert res.meta.soft_wrap_merges >= 1
    assert len(res.rec_texts) == 1
    assert "向相关领输出方案可行性报告。" in res.rec_texts[0]


if __name__ == "__main__":
    test_merge_by_boxes_continuation()
    test_no_merge_without_boxes()
    test_no_merge_across_columns()
    test_no_merge_new_numbered_item()
    test_build_response_soft_wrap_meta()
    print("ok")
