#!/usr/bin/env bash
# 安装依赖: 需要 uv (https://docs.astral.sh/uv/)。模型文件不在此下载, 见 README。
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "错误: 未找到 uv。安装: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

echo "==> 同步 Python 依赖 (torch 2.14.1 / transformers 5.17 / fastapi)"
uv sync

MODEL="${HUMANIZER_MODEL:-/home/feifei/develop/models/humanizer}"
if [ ! -f "$MODEL/model.safetensors" ]; then
    echo
    echo "警告: 未找到模型 $MODEL/model.safetensors" >&2
    echo "  从 Hugging Face 下载: hf download jialinyyzz/humanizer --local-dir $MODEL" >&2
    echo "  或启动时指定: HUMANIZER_MODEL=/path/to/model ./server.sh" >&2
fi

echo
echo "安装完成。启动: ./server.sh   (默认 http://127.0.0.1:8100)"
