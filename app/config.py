"""环境变量配置（pydantic-settings）。"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 服务
    YM_OCR_HOST: str = "127.0.0.1"
    YM_OCR_PORT: int = 8001
    YM_OCR_API_KEY: str = ""  # 必填，空则不鉴权（仅内网调试用）

    # 推理
    OCR_DEVICE: str = ""  # 空=自动探测 gpu:0/cpu
    OCR_MODEL: str = "PP-OCRv6_small"  # det/rec 未单独指定时的默认档位
    OCR_DET_MODEL: str = ""  # 空=跟随 OCR_MODEL；如 PP-OCRv6_small
    OCR_REC_MODEL: str = ""  # 空=跟随 OCR_MODEL；如 PP-OCRv6_medium
    OCR_MODEL_DIR: str = "models"  # 本地模型根目录（git 排除）
    OCR_DET_LIMIT_SIDE_LEN: int = 1280  # 检测最长边上限，降显存
    OCR_MAX_CONCURRENT: int = 2  # 推理并发上限，GPU 防爆
    OCR_PDF_MAX_PAGES: int = 50
    OCR_PDF_RENDER_SCALE: float = 1.5
    OCR_PDF_PREFER_TEXT: bool = True  # 原生文本层优先；扫描件自动回退 OCR
    OCR_PDF_TEXT_MIN_CHARS_PER_PAGE: int = 30  # 页均字符低于此值视为扫描件


settings = Settings()


def effectiveDetModel() -> str:
    return settings.OCR_DET_MODEL.strip() or settings.OCR_MODEL.strip()


def effectiveRecModel() -> str:
    return settings.OCR_REC_MODEL.strip() or settings.OCR_MODEL.strip()


def modelLabel() -> str:
    """API meta 用：同档返回单名，混用返回 det+rec。"""
    det, rec = effectiveDetModel(), effectiveRecModel()
    if det == rec:
        return det
    return f"{det}_det+{rec}_rec"


def effectiveDevice() -> str:
    """返回传给 PaddleOCR(device=...) 的字符串，避免 device=None 触发不完整 paddle 安装的报错。"""
    if settings.OCR_DEVICE.strip():
        return settings.OCR_DEVICE.strip()
    try:
        import paddle

        pd = getattr(paddle, "device", None)
        if pd is not None and pd.is_compiled_with_cuda() and pd.cuda.device_count() > 0:
            return "gpu:0"
    except Exception:
        pass
    return "cpu"
