"""PaddleOCR 单例引擎：启动时加载一次，全局共享，避免重复占显存。

环境变量须在首次 import paddle/paddlex 前生效，故本模块顶层即设置。
默认 PP-OCRv6 small + 检测最长边限制 + 识别 batch=1，与 apiYmy ocrSvc.py 对齐。
"""

from __future__ import annotations

import os
from pathlib import Path

# 必须在 import paddle / paddlex 之前写入
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("FLAGS_fraction_of_gpu_memory_to_use", "0.5")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
# 官方模型缓存/锁目录指向项目内（默认 ~/.paddlex 可能被 root 占用导致权限错误）
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(Path(__file__).resolve().parent.parent / ".paddlex_cache"))

import numpy as np

from app.config import settings, effectiveDevice

_ocr = None


def _modelComplete(modelDir: Path) -> bool:
    """检查模型目录是否含三个必需文件（inference.json/pdiparams/yml）。"""
    required = ("inference.json", "inference.pdiparams", "inference.yml")
    return all((modelDir / f).is_file() for f in required)


def initEngine() -> None:
    """启动时加载 PaddleOCR 单例（lifespan 调用）。

    本地模型目录优先（det/rec 各自独立判断）；
    缺失或不完整的模型交给 PaddleOCR 自动联网下载到 OCR_MODEL_DIR。
    """
    global _ocr
    if _ocr is not None:
        return
    from paddleocr import PaddleOCR

    device = effectiveDevice()
    model = settings.OCR_MODEL
    modelDir = Path(settings.OCR_MODEL_DIR)
    detDir = modelDir / f"{model}_det"
    recDir = modelDir / f"{model}_rec"

    detOk = _modelComplete(detDir)
    recOk = _modelComplete(recDir)

    kw = {
        "device": device,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "text_detection_model_name": f"{model}_det",
        "text_recognition_model_name": f"{model}_rec",
        "text_det_limit_side_len": settings.OCR_DET_LIMIT_SIDE_LEN,
        "text_det_limit_type": "max",
        "text_recognition_batch_size": 1,
        "enable_mkldnn": False,
        "precision": "fp16",
    }
    if detOk:
        kw["text_detection_model_dir"] = str(detDir)
        print(f"[ym-ocr] 检测模型: 本地 {detDir}")
    else:
        print(f"[ym-ocr] 检测模型缺失或不完整，将由 PaddleOCR 自动下载到 {modelDir}")
    if recOk:
        kw["text_recognition_model_dir"] = str(recDir)
        print(f"[ym-ocr] 识别模型: 本地 {recDir}")
    else:
        print(f"[ym-ocr] 识别模型缺失或不完整，将由 PaddleOCR 自动下载到 {modelDir}")

    print(f"[ym-ocr] PaddleOCR 初始化: device={device} model={model}")
    _ocr = PaddleOCR(**kw)


def shutdownEngine() -> None:
    """关闭时释放（lifespan 调用）。"""
    global _ocr
    _ocr = None


def isReady() -> bool:
    return _ocr is not None


def predict(image: np.ndarray) -> tuple[list[str], list[list[int]]]:
    """单图同步推理，返回 (rec_texts, rec_boxes)。

    供 asyncio.to_thread 调用，避免阻塞事件循环。
    """
    if _ocr is None:
        raise RuntimeError("OCR engine 未初始化")
    result = _ocr.predict(image)
    # predict 返回 generator，取第一页
    first = next(iter(result))
    rec_texts = list(first["rec_texts"])
    rec_boxes = [list(b) for b in first["rec_boxes"].tolist()]
    return rec_texts, rec_boxes
