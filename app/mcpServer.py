"""MCP 适配：FastMCP + 2 个 tool，均调 ocrService.recognize。

参照 apiYmy integrations/mcp/abRecruitServer.py 模式：
- FastMCP 实例名为 mcp
- tool 返回 json.dumps(..., ensure_ascii=False)
- 工具命名前缀 ocr_，Hermes 显示为 ym-ocr__ocr_recognize_*
"""

from __future__ import annotations

import base64
import json

from mcp.server.fastmcp import FastMCP

from app.ocrService import recognize, recognizeFromPath

mcp = FastMCP("ym-ocr")
# MCP app 内部路由设为 "/"，由 main.py mount 到 "/mcp"，最终路径为 /mcp
mcp.settings.streamable_http_path = "/"


@mcp.tool()
async def ocr_recognize_file(file_path: str) -> str:
    """对本地图片或 PDF 做 OCR，返回识别全文与逐行结果。

    Args:
        file_path: 本机绝对路径，支持 .png/.jpg/.jpeg/.webp/.pdf
    """
    res = await recognizeFromPath(file_path)
    return json.dumps(res.model_dump(), ensure_ascii=False)


@mcp.tool()
async def ocr_recognize_base64(file_base64: str, filename: str = "upload.png") -> str:
    """对 Base64 编码的图片或 PDF 做 OCR。

    Args:
        file_base64: 文件内容的 Base64 字符串
        filename: 文件名（用于判断 PDF/图片），如 resume.pdf
    """
    try:
        data = base64.b64decode(file_base64)
    except Exception as e:
        return json.dumps(
            {"code": 400, "message": f"Base64 解码失败: {e}"},
            ensure_ascii=False,
        )
    res = await recognize(data, filename)
    return json.dumps(res.model_dump(), ensure_ascii=False)
