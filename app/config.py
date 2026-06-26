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
    OCR_MODEL: str = "PP-OCRv6_medium"  # 可切 PP-OCRv6_small / PP-OCRv6_tiny
    OCR_MODEL_DIR: str = "models"  # 本地模型根目录（git 排除）
    OCR_MAX_CONCURRENT: int = 2  # 推理并发上限，GPU 防爆
    OCR_PDF_MAX_PAGES: int = 50
    OCR_PDF_RENDER_SCALE: float = 2.0


settings = Settings()


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
