"""ym-ocr 极简 Python 客户端：给各应用复用。

新应用接入 = 配 YM_OCR_BASE_URL + YM_OCR_API_KEY + 复制本文件。

用法：
    from client.ymOcrClient import YmOcrClient
    client = YmOcrClient(baseUrl="http://127.0.0.1:8001", apiKey="xxx")
    res = await client.ocrFile(open("resume.pdf","rb").read(), "resume.pdf")
    print(res["fullText"])
"""

from __future__ import annotations

import httpx


class YmOcrClient:
    def __init__(self, baseUrl: str, apiKey: str = "", timeout: float = 120.0):
        self.baseUrl = baseUrl.rstrip("/")
        self.apiKey = apiKey.strip()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.apiKey}"} if self.apiKey else {}

    async def ocrFile(self, fileBytes: bytes, filename: str) -> dict:
        """上传文件做 OCR，返回 OcrResponse dict。"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.baseUrl}/v1/ocr",
                files={"file": (filename, fileBytes)},
                headers=self._headers(),
            )
        resp.raise_for_status()
        return resp.json()

    async def ocrPath(self, filePath: str) -> dict:
        """从本机文件路径读取后上传。"""
        from pathlib import Path

        p = Path(filePath)
        with p.open("rb") as f:
            data = f.read()
        return await self.ocrFile(data, p.name)

    async def ready(self) -> bool:
        """检查服务是否就绪（模型已加载）。"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{self.baseUrl}/ready", headers=self._headers())
                return resp.json().get("ready", False)
            except Exception:
                return False
