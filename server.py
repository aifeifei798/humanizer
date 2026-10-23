"""humanizer API: 把 AI 草稿改写成"像人写的"。

模型: /home/feifei/develop/models/humanizer (jialinyyzz/humanizer, gemma-4-12B 微调)
格式: 文本补全, 不是 chat。prompt 必须逐字节复刻 prompt_format.json,
     指纹校验见 PROMPT_FINGERPRINT。
采样: temperature 1.0, top_p 0.95, top_k 0 (覆盖 generation_config.json 的 top_k 64),
     只按 EOS 停, 不设 stop 字符串。
"""

import hashlib
import json
import os
import queue
import threading
import time
from contextlib import asynccontextmanager

import anyio
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

MODEL_PATH = os.environ.get("HUMANIZER_MODEL", "/home/feifei/develop/models/humanizer")
HOST = os.environ.get("HUMANIZER_HOST", "127.0.0.1")
PORT = int(os.environ.get("HUMANIZER_PORT", "8100"))
CONTEXT_TOKENS = 8192          # 指令 + 草稿 + 改写总量上限
DEFAULT_MAX_NEW_TOKENS = 2048
MAX_LANG_RETRIES = 3           # 英文稿混入中文时最多采样 3 次 (AGENTS.md 第 0 节)

# prompt_format.json 里的自校验指纹: sha256(prompt for draft "X") 前 16 位
PROMPT_FINGERPRINT = "cc51d66b4c593fbe"

with open(os.path.join(MODEL_PATH, "prompt_format.json"), encoding="utf-8") as f:
    _PF = json.load(f)
INSTR, SEP = _PF["instr"], _PF["sep"]


def build_prompt(draft: str) -> str:
    return INSTR + "\n\n" + draft.strip() + SEP


assert (
    hashlib.sha256(build_prompt("X").encode("utf-8")).hexdigest()[:16] == PROMPT_FINGERPRINT
), "prompt format mismatch: prompt_format.json 与官方指纹不符"

state: dict = {"model": None, "lock": threading.Lock()}
TOK = None  # tokenizer, 在 lifespan 中加载


def _is_mostly_english(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    latin = sum(1 for c in letters if c.isascii())
    return latin / len(letters) > 0.5


def _chinese_ratio(text: str) -> float:
    if not text:
        return 0.0
    han = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return han / max(1, len(text))


def _default_max_new_tokens(draft: str) -> int:
    draft_len = len(TOK(draft.strip())["input_ids"])
    # app 的规则: 约 2.5 倍草稿 token 数, 收在 [256, 2048]
    est = min(2048, max(256, int(draft_len * 2.5)))
    # 上下文 8192 内能塞多少就给多少
    prompt_len = len(TOK(build_prompt(draft))["input_ids"])
    est = min(est, CONTEXT_TOKENS - prompt_len)
    return max(0, est)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global TOK
    TOK = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        dtype=torch.bfloat16,
        device_map={"": "cuda"},
    )
    model.eval()
    state["model"] = model
    print(f"humanizer ready: {torch.cuda.get_device_name(0)}, "
          f"VRAM {torch.cuda.memory_allocated() / 2**30:.1f} GiB")
    yield
    state["model"] = None


app = FastAPI(title="humanizer API", version="1.0.0", lifespan=lifespan)


class HumanizeRequest(BaseModel):
    text: str = Field(min_length=1, description="AI 写的草稿, 中英文均可")
    max_new_tokens: int | None = Field(
        default=None, ge=1, le=4096,
        description="缺省按草稿长度的 2.5 倍收在 [256, 2048]")
    seed: int | None = Field(default=None, description="固定随机种子以便复现")


class HumanizeResponse(BaseModel):
    rewrite: str
    attempts: int
    tokens_generated: int
    seconds: float


def _with_lock(fn, *args):
    with state["lock"]:
        return fn(*args)


def _generate_once(prompt: str, max_new_tokens: int, seed: int | None,
                   streamer: TextIteratorStreamer | None = None):
    model = state["model"]
    inputs = TOK(prompt, return_tensors="pt").to(model.device)
    kwargs = dict(
        do_sample=True,
        temperature=1.0,
        top_p=0.95,
        top_k=0,          # 必须显式关掉 generation_config.json 里的 top_k 64
        min_p=0.0,
        repetition_penalty=1.0,
        max_new_tokens=max_new_tokens,
        pad_token_id=TOK.pad_token_id or 0,
    )
    if seed is not None:
        torch.manual_seed(seed)
    if streamer is not None:
        kwargs["streamer"] = streamer
    with torch.no_grad():
        out = model.generate(**inputs, **kwargs)
    new_tokens = out.shape[1] - inputs["input_ids"].shape[1]
    return TOK.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip(), new_tokens


def _humanize(text: str, max_new_tokens: int | None, seed: int | None):
    prompt = build_prompt(text)
    prompt_len = len(TOK(prompt)["input_ids"])
    if prompt_len + 1 > CONTEXT_TOKENS:
        raise HTTPException(
            status_code=413,
            detail=f"草稿太长: prompt {prompt_len} tokens, 上下文上限 {CONTEXT_TOKENS}, "
                   f"请拆短后分段调用")
    budget = max_new_tokens if max_new_tokens is not None else _default_max_new_tokens(text)
    budget = max(16, min(budget, CONTEXT_TOKENS - prompt_len))

    english_draft = _is_mostly_english(text)
    attempts = 0
    start = time.monotonic()
    while True:
        attempts += 1
        rewrite, n_tokens = _generate_once(prompt, budget, seed)
        if not english_draft or _chinese_ratio(rewrite) < 0.05 or attempts >= MAX_LANG_RETRIES:
            break
    return rewrite, attempts, n_tokens, time.monotonic() - start


@app.get("/health")
def health():
    ready = state["model"] is not None
    return {"status": "ok" if ready else "loading"}


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


@app.post("/humanize", response_model=HumanizeResponse)
async def humanize(req: HumanizeRequest):
    if state["model"] is None:
        raise HTTPException(status_code=503, detail="模型还在加载")
    # 单卡单模型, 请求串行执行; 丢到线程池避免阻塞事件循环 (锁在线程里同步持有)
    rewrite, attempts, n_tokens, seconds = await anyio.to_thread.run_sync(
        lambda: _with_lock(_humanize, req.text, req.max_new_tokens, req.seed))
    return HumanizeResponse(rewrite=rewrite, attempts=attempts,
                            tokens_generated=n_tokens, seconds=round(seconds, 2))


@app.post("/humanize/stream")
async def humanize_stream(req: HumanizeRequest):
    """SSE 流式输出。一次采样, 不做语言重采样检查。"""
    if state["model"] is None:
        raise HTTPException(status_code=503, detail="模型还在加载")

    prompt = build_prompt(req.text)
    prompt_len = len(TOK(prompt)["input_ids"])
    if prompt_len + 1 > CONTEXT_TOKENS:
        raise HTTPException(status_code=413, detail=f"草稿太长: prompt {prompt_len} tokens")
    budget = req.max_new_tokens if req.max_new_tokens is not None else _default_max_new_tokens(req.text)
    budget = max(16, min(budget, CONTEXT_TOKENS - prompt_len))

    async def gen():
        streamer = TextIteratorStreamer(TOK, skip_prompt=True,
                                        skip_special_tokens=True)

        def worker():
            try:
                _with_lock(_generate_once, prompt, budget, req.seed, streamer)
            except Exception as e:  # noqa: BLE001
                q.put(e)
                streamer.end()   # 解除 streamer 迭代的阻塞

        q: queue.Queue = queue.Queue()
        threading.Thread(target=worker, daemon=True).start()
        for piece in streamer:
            if piece:
                yield f"data: {json.dumps({'delta': piece}, ensure_ascii=False)}\n\n"
        if not q.empty():
            yield f"data: {json.dumps({'error': str(q.get())}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
