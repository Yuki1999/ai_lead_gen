# 微创畅行海外渠道拓展系统

本仓库包含一个本地可运行的 Web 应用和一个 agent skill，用于海外代理商获客、邮件触达记录、回复理解和复杂情况转人工。

当前应用会读取项目根目录下的产品资料：

- `SkyWalker-Surgical-Robot-Sales-Brochure-International.pdf`
- `02-鸿鹄产品介绍Skywalker TKA Brochure.pdf`
- `0_6.mp4`

后端会从可提取文本的 PDF 中识别 SkyWalker Robotic Platform Total Knee Application、TKA、orthopedic/joint replacement、CT-based planning、gap balancing 等定位，并用这些关键词实时搜索公开网页，抽取官网和公开邮箱后入库。为避免搜索引擎临时不可用导致演示完全无结果，后端还内置了一组经人工验证的官网种子 URL；运行时仍会实时打开这些官网页面抽取邮箱，不保存伪造联系人。中文 PDF 是扫描图像，当前不做 OCR。

## 结构

- `backend/`: FastAPI + SQLite API
- `frontend/`: Vue + Vite 操作台
- `agent/`: Pi/pi-mono Node sidecar，默认加载 `overseas-distributor-prospecting`
- `skills/overseas-distributor-prospecting/`: 给 agent 使用的拓客 workflow skill
- `docs/superpowers/`: 设计文档和实施计划

## 后端

```bash
cd backend
uv run pytest -v
uv run uvicorn app.main:app --reload --port 8000
```

后端默认使用 `backend/medbot-demo.db`。可通过 `MEDBOT_DB_PATH` 指定 SQLite 文件路径。

主要接口：

- `GET /product/profile`: 读取根目录产品资料并生成产品画像
- `POST /agent/chat`: 代理到本地 Pi agent sidecar，前端 Agent 面板使用这个接口
- `POST /agent/chat/stream`: 以 `text/event-stream` 代理 Agent 实时输出、工具事件和完成状态
- `GET /agent/config`: 返回 Agent provider、模型和脱敏 key 预览
- `PUT /agent/config`: 从 Web 写入 `agent/.env` 的 `PI_PROVIDER`、provider API key、`PI_MODEL`、`BACKEND_BASE_URL`
- `POST /leads/search`: 默认执行真实网页搜索；传 `real_search: false` 才使用离线样例
- `POST /campaigns/outreach-records`: 根据真实线索邮箱生成触达记录和邮件草稿
- `POST /replies/analyze`: 理解邮件回复并更新线索状态

如需修改 agent sidecar 地址，设置 `AGENT_BASE_URL`。如果 sidecar 配置了 `AGENT_TOKEN`，后端进程也需要设置相同的 `AGENT_TOKEN`，代理会自动转发 `Authorization: Bearer ...`。如果要让配置 API 写入其他文件，可设置 `AGENT_ENV_PATH`。

## Pi Agent Sidecar

```bash
cd agent
npm install
cp .env.example .env
# 编辑 agent/.env，至少设置 provider 对应的 API key
npm test
npm run build
npm run dev
```

sidecar 默认监听 `127.0.0.1:8011`，暴露 `/health`、`/agent/chat` 和 `/agent/chat/stream`。它会把 `skills/overseas-distributor-prospecting/SKILL.md` 注册为默认 skill，并只给模型开放业务工具：

- `get_product_profile`
- `web_search`
- `fetch_url`
- `search_leads`
- `list_leads`
- `create_outreach_records`
- `analyze_reply`

provider 默认是 `openai`，模型默认是 `gpt-5-mini`，可通过 `PI_PROVIDER` 和 `PI_MODEL` 修改。DeepSeek 可配置为 `PI_PROVIDER=deepseek`、`DEEPSEEK_API_KEY=...`、`PI_MODEL=deepseek-v4-pro`。`BACKEND_BASE_URL` 指向 FastAPI 服务，默认 `http://localhost:8000`。如果把 `AGENT_HOST` 设为非本地地址，必须同时配置 `AGENT_TOKEN`。

也可以在 Web 的 Agent 面板里选择 provider，并保存 API key、模型名和 backend 地址。后端会写入 `agent/.env`，接口不会回传完整 key，只会返回脱敏状态。运行中的 sidecar 不热重载 `.env`；保存后需要重启 `npm run dev` 或 `npm start` 的 agent 进程。

## 前端

```bash
cd frontend
npm install
npm run build
npm run dev -- --host 0.0.0.0
```

打开 Vite 输出的本地地址，默认 API 地址是 `http://localhost:8000`。如需修改，设置 `VITE_API_BASE_URL`。页面里的 Agent 面板会通过后端 `POST /agent/chat/stream` 调用 sidecar，实时显示会话开始、工具事件、模型增量输出和完成状态，不直接暴露 sidecar token。

## 运行流程

1. 在前端确认产品画像，填写目标国家/地区、搜索关键词和返回数量，点击“实时搜索并入库”。
2. 系统会调用实时网页搜索，打开候选官网/contact 页面，抽取公开邮箱；默认只保存发现邮箱的线索。
3. 在 Agent 面板下达任务，例如“帮我找 SkyWalker TKA 在印度的渠道商”，Agent 会默认使用海外渠道拓展 skill 并调用业务工具。
4. 在线索数据库中勾选代理商邮箱，点击“生成触达记录”。
5. 粘贴代理商回复，点击“理解回复”。
6. 对复杂商务、法务或注册问题，系统会标记为“转人工”。

## 新增依赖说明

- 后端使用 `fastapi`、`uvicorn`、`pydantic` 提供 API；`pypdf` 读取 PDF；`requests`、`beautifulsoup4` 执行网页搜索结果解析和公开邮箱抽取；`pytest`、`httpx` 用于测试。
- Agent sidecar 使用 `@earendil-works/pi-ai`、`@earendil-works/pi-coding-agent` 和 `typebox` 运行 Pi session、注册默认 skill 和声明业务工具。
- 前端使用 `vue`、`vite`、`typescript` 构建单页运营界面；`lucide-vue-next` 用于按钮和指标图标。

## 运行建议

如果 8000 已被占用：

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8010
```

另开终端：

```bash
cd frontend
VITE_API_BASE_URL=http://localhost:8010 npm run dev -- --host 0.0.0.0
```

如果后端端口改为 8010，agent sidecar 也要用同一个后端地址：

```bash
cd agent
BACKEND_BASE_URL=http://localhost:8010 npm run dev
```

真实搜索依赖网络和搜索引擎可访问性。若目标地区太宽或网络不可用，可能返回 0 条；可改用更具体的国家或关闭“仅保存已发现邮箱”观察候选官网。
