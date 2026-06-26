#!/bin/bash
# 启动 ym-ocr 服务（避免 pkill 误杀，用脚本名匹配）
cd /home/ym/ym-ocr
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
