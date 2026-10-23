#!/usr/bin/env bash
# 启动 humanizer API + 网页客户端。
# 环境变量: HUMANIZER_MODEL (模型路径) / HUMANIZER_HOST / HUMANIZER_PORT
set -euo pipefail
cd "$(dirname "$0")"

MODEL="${HUMANIZER_MODEL:-/home/feifei/develop/models/humanizer}"
HOST="${HUMANIZER_HOST:-127.0.0.1}"
PORT="${HUMANIZER_PORT:-8100}"

if [ ! -f "$MODEL/model.safetensors" ]; then
    echo "错误: 未找到模型 $MODEL/model.safetensors" >&2
    echo "  下载: hf download jialinyyzz/humanizer --local-dir $MODEL" >&2
    echo "  或: HUMANIZER_MODEL=/path/to/model $0" >&2
    exit 1
fi

if [ ! -d .venv ]; then
    echo "==> 未安装依赖, 先执行 install.sh"
    ./install.sh
fi

echo "==> 模型: $MODEL"
echo "==> http://$HOST:$PORT  (Ctrl+C 停止)"
exec env HUMANIZER_MODEL="$MODEL" uv run uvicorn server:app --host "$HOST" --port "$PORT"
