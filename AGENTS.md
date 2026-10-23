# AGENTS.md: 开发与维护 humanizer API

给在此仓库工作的 AI 编码代理(Claude Code、Codex、Cursor 等)的说明。人类向文档见 [README.md](README.md)。

## 0. 这是什么

FastAPI 服务,把本地 humanizer 模型(`jialinyyzz/humanizer`,Gemma-4-12B 微调,bf16 约 24GB)
包装成 HTTP API + Tailwind 网页客户端,把 AI 草稿改写成"像人写的"。单文件服务 [`server.py`](server.py),
单文件前端 [`static/index.html`](static/index.html)。

## 1. 不许破坏的约束(改坏 = 模型输出质量下降)

1. **default 身份的 prompt 必须逐字节复刻模型的 `prompt_format.json`**:
   `INSTR + "\n\n" + draft.strip() + SEP`。`server.py` 顶部有 sha256 指纹断言
   (`cc51d66b4c593fbe`,对草稿 "X"),该断言必须保留且必须通过。
2. **采样参数固定**:temperature 1.0、top_p 0.95、**top_k 0**(显式覆盖模型自带
   generation_config.json 里的 top_k 64)、min_p 0、repetition_penalty 1.0。
   只在 EOS 停,**绝不加 stop 字符串**(尤其不能是 `"###"`)。
3. **不是 chat 模型**:不加系统提示、不套聊天模板、不用 `/v1/chat/completions` 类接口。
4. **上下文 8192 token**(指令 + 草稿 + 改写总量),超长返回 413。
5. **英文稿输出混入大段中文时重采样**(最多 3 次),这是模型作者建议的行为,别删。
6. 非默认身份 = 在指令区末尾追加一句英文 `Write it in the voice of …`,这是有意的受控偏离;
   不要把身份描述插进草稿或分隔符里。`default` 的 voice 必须是 `None`。

## 2. 常用命令

```bash
./install.sh            # uv sync; 缺 uv 会提示
./server.sh             # 启动(前台); 子命令: stop / restart / status
uv run python tests/selftest.py   # 服务运行时的自测(官方评估集样例草稿)
uvx pyflakes server.py  # 提交前的静态检查
```

服务默认 `http://127.0.0.1:8100`,`GET /health` 返回 `{"status":"ok"}` 即就绪。
模型加载约 20 秒,占约 23GB 显存(需要 ≥26GB 空闲 VRAM);不要并行启动两个实例。

## 3. 改动约定

- 加**写作身份**:在 `server.py` 的 `IDENTITIES` 里加一行
  `{label: 中文标签, voice: 英文描述}` 即可,前端下拉框自动从 `GET /identities` 渲染。
  voice 用一句英文描述口吻,不要写成完整段落。
- 改**前端**只动 `static/index.html`(单文件,JS 内联);Tailwind Play 版已下载到
  `static/vendor/tailwind.js`,页面必须离线可用,不要换成 CDN 链接。
- API 契约变化要同步更新 README.md 的接口文档。
- 依赖用 `uv add` 管理,版本钉死;torch 2.14.1+cu130 / transformers 5.17.0 已验证兼容
  RTX 5090 D,升级前先跑自测。
- 提交信息用中文一句话,改完推送 `git push origin main`。

## 4. 自测判定

`tests/selftest.py` 输出 `PASS: install looks right` 即通过;`NOTE: numbers not found`
是采样偶发,重跑一次即可,连续出现才算问题。自测覆盖:无 prompt 回显、无聊天标记、
不复制草稿(5-gram 重合 < 0.5)、数字保留。

## 5. 已知事实

- 模型仍可能改动细节:官方评测 420 篇英文改写 376 篇无事实问题。任何面向用户的输出
  都应提醒核对数字、日期、姓名。
- `kill` 服务后显存立即释放;`restart` 需要重新加载约 20 秒。
- git 仓库 remote: `github.com/aifeifei798/humanizer`(public,Apache 2.0)。
