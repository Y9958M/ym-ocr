"""REST 适配：POST /v1/ocr + 健康检查。鉴权由 main.py middleware 统一处理。"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app import engine
from app.config import settings
from app.ocrService import recognize
from app.schemas import OcrResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    return {"ready": engine.isReady(), "model": settings.OCR_MODEL}


@router.post("/v1/ocr", response_model=OcrResponse)
async def ocr(file: UploadFile = File(..., description="图片或 PDF")):
    """对上传的图片或 PDF 做 OCR，返回统一 OcrResponse。"""
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件为空")
    res = await recognize(data, file.filename or "upload.bin")
    return JSONResponse(
        content=res.model_dump(),
        status_code=200 if res.code == 200 else 400,
    )
