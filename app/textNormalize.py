"""OCR 识别出口 · 字形/符号减噪（平台级，无业务语义）。

参考口径：
- Unicode NFKC（兼容区/康熙部首 → 统一汉字，如 ⼤→大、硕⼠→硕士）
- apiYmy `ocr_text_normalize`：全角数字字母/标点 → 半角、空白折叠
- ym-ats S0：零宽剥离（消费方仍可再做一遍，作双保险）

刻意不做：
- 简历水印/关键词丢行、切段、校名/雇主猜测（属消费方业务）
- 将 ·•● 改成空格（会破坏经历职责 bullet；apiYmy 流水线有此步，平台 OCR 不跟）
"""

from __future__ import annotations

import re
import unicodedata

# 隐形字符 / 软连字符（OCR PDF 常见）
_ZW_CHARS_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00a0\u00ad]")

_FULLWIDTH_ALNUM = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
)

# 与 apiYmy / ym-ats S0 对齐的全角标点；另补 em dash / 波浪线常见异体
_PUNCT_FULL_TO_HALF: dict[str, str] = {
    "　": " ",
    "－": "-",
    "–": "-",
    "—": "-",
    "−": "-",
    "～": "~",
    "，": ",",
    "！": "!",
    "？": "?",
    "：": ":",
    "；": ";",
    "（": "(",
    "）": ")",
    "【": "[",
    "】": "]",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "｛": "{",
    "｝": "}",
}

_PUNCT_TRANSLATION = str.maketrans(_PUNCT_FULL_TO_HALF)


def normalizeOcrText(raw: str) -> str:
    """单行/片段字形规范化（幂等；不改大小写）。"""
    if not raw or not isinstance(raw, str):
        return ""
    t = unicodedata.normalize("NFKC", raw)
    t = _ZW_CHARS_RE.sub("", t)
    t = t.translate(_FULLWIDTH_ALNUM)
    t = t.translate(_PUNCT_TRANSLATION)
    t = t.replace("\u3000", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def normalizeRecTexts(
    texts: list[str],
    boxes: list[list[int]] | None = None,
) -> tuple[list[str], list[list[int]]]:
    """对 rec_texts 逐行规范化；空行丢弃并与 boxes 对齐。"""
    if not texts:
        return [], list(boxes or [])

    out_texts: list[str] = []
    out_boxes: list[list[int]] = []
    n_boxes = len(boxes) if boxes is not None else 0

    for i, line in enumerate(texts):
        cleaned = normalizeOcrText(line)
        if not cleaned:
            continue
        out_texts.append(cleaned)
        if boxes is not None:
            if i < n_boxes:
                out_boxes.append(list(boxes[i]))
            else:
                out_boxes.append([0, 0, 0, 0])

    if boxes is None:
        return out_texts, []
    return out_texts, out_boxes
