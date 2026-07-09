"""REST 适配：POST /v1/ocr + 健康检查。鉴权由 main.py middleware 统一处理。"""

from __future__ import annotations

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app import engine
from app.config import modelLabel
from app.ocrService import recognize
from app.schemas import OcrResponse

router = APIRouter()


def _callerFromRequest(
    request: Request,
    x_ym_caller: str | None,
) -> str:
    """优先 X-Ym-Caller；否则用 User-Agent 简写 + 客户端 IP。"""
    if x_ym_caller and x_ym_caller.strip():
        return x_ym_caller.strip()[:64]
    ua = (request.headers.get("user-agent") or "").strip()
    uaShort = ua.split("/")[0][:32] if ua else "unknown"
    client = request.client.host if request.client else "-"
    return f"{uaShort}@{client}"


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    return {"ready": engine.isReady(), "model": modelLabel()}


@router.post("/v1/ocr", response_model=OcrResponse)
async def ocr(
    request: Request,
    file: UploadFile = File(..., description="图片或 PDF"),
    x_ym_caller: str | None = Header(default=None, alias="X-Ym-Caller"),
):
    """对上传的图片或 PDF 做 OCR，返回统一 OcrResponse。"""
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件为空")
    caller = _callerFromRequest(request, x_ym_caller)
    res = await recognize(
        data,
        file.filename or "upload.bin",
        caller=caller,
        via="rest",
    )
    return JSONResponse(
        content=res.model_dump(),
        status_code=200 if res.code == 200 else 400,
    )
