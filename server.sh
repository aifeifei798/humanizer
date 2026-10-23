#!/usr/bin/env bash
# 启动/停止 humanizer API + 网页客户端。
# 用法: ./server.sh [start|stop|restart|status]   默认 start(前台,Ctrl+C 停止)
# 环境变量: HUMANIZER_MODEL (模型路径) / HUMANIZER_HOST / HUMANIZER_PORT
set -euo pipefail
cd "$(dirname "$0")"

MODEL="${HUMANIZER_MODEL:-/home/feifei/develop/models/humanizer}"
HOST="${HUMANIZER_HOST:-127.0.0.1}"
PORT="${HUMANIZER_PORT:-8100}"
URL="http://$HOST:$PORT"
PIDFILE="/tmp/humanizer-server-$PORT.pid"

running_pid() {
    # 先看 pid 文件, 进程已死则忽略; 兜底按命令行匹配
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        cat "$PIDFILE"
        return
    fi
    pgrep -f "uvicorn server:app --host $HOST --port $PORT" | head -1 || true
}

do_stop() {
    local pid
    pid="$(running_pid)"
    if [ -z "$pid" ]; then
        echo "未在运行"
        rm -f "$PIDFILE"
        return 0
    fi
    echo "==> 停止 PID $pid ($URL)"
    kill "$pid"
    for _ in $(seq 1 30); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "==> 5 秒未退出, 强制结束"
        kill -9 "$pid" || true
    fi
    rm -f "$PIDFILE"
    echo "==> 已停止"
}

do_status() {
    local pid
    pid="$(running_pid)"
    if [ -z "$pid" ]; then
        echo "未运行"
        return 1
    fi
    echo "运行中: PID $pid ($URL)"
    curl -s -m 3 "$URL/health" && echo || echo "(模型加载中或无响应)"
}

check_model() {
    if [ ! -f "$MODEL/model.safetensors" ]; then
        echo "错误: 未找到模型 $MODEL/model.safetensors" >&2
        echo "  下载: hf download jialinyyzz/humanizer --local-dir $MODEL" >&2
        echo "  或: HUMANIZER_MODEL=/path/to/model $0" >&2
        exit 1
    fi
}

cmd="${1:-start}"
case "$cmd" in
    start)
        check_model
        if old="$(running_pid)"; [ -n "$old" ]; then
            echo "错误: 已在运行 (PID $old, $URL)。先执行 $0 stop" >&2
            exit 1
        fi
        [ -d .venv ] || ./install.sh
        echo $$ > "$PIDFILE"   # exec 后 shell PID 即 uvicorn PID
        echo "==> 模型: $MODEL"
        echo "==> $URL  (Ctrl+C 停止; 管理命令: $0 stop|restart|status)"
        exec env HUMANIZER_MODEL="$MODEL" uv run uvicorn server:app --host "$HOST" --port "$PORT"
        ;;
    stop) do_stop ;;
    restart) do_stop; exec "$0" start ;;
    status) do_status ;;
    *)
        echo "用法: $0 [start|stop|restart|status]" >&2
        exit 2
        ;;
esac
