"""单文件自检：不启动服务，直接调 engine + ocrService 确认识别链路通。

用法：
    uv run python scripts/selfcheck.py samples/test.png

ponytail: 非平凡逻辑留一个最小自检（无框架）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import engine
from app.ocrService import recognizeFromPath


async def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python scripts/selfcheck.py <图片或PDF路径>")
        sys.exit(1)
    filePath = sys.argv[1]
    if not Path(filePath).exists():
        print(f"文件不存在: {filePath}")
        sys.exit(1)

    print("[selfcheck] 初始化引擎...")
    engine.initEngine()
    print(f"[selfcheck] 引擎就绪: {engine.isReady()}")

    print(f"[selfcheck] 识别: {filePath}")
    res = await recognizeFromPath(filePath, caller="selfcheck", via="selfcheck")
    print(f"[selfcheck] code={res.code} message={res.message}")
    print(f"[selfcheck] pages={res.meta.pages} elapsed_ms={res.meta.elapsed_ms} model={res.meta.model}")
    print(f"[selfcheck] 行数={len(res.rec_texts)}")
    if res.rec_texts:
        preview = res.rec_texts[:5]
        print(f"[selfcheck] 前 5 行: {preview}")
        assert res.rec_texts, "rec_texts 不应为空"
        print("[selfcheck] PASS")
    else:
        print("[selfcheck] 未识别到文本（检查文件或模型）")
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
