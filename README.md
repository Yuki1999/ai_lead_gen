# 微创畅行海外渠道拓展系统

本仓库包含一个本地可运行的 Web 应用和一个 agent skill，用于海外代理商获客、邮件触达记录、回复理解和复杂情况转人工。

当前应用会读取项目根目录下的产品资料：

- `SkyWalker-Surgical-Robot-Sales-Brochure-International.pdf`
- `02-鸿鹄产品介绍Skywalker TKA Brochure.pdf`
- `0_6.mp4`

后端会从可提取文本的 PDF 中识别 SkyWalker Robotic Platform Total Knee Application、TKA、orthopedic/joint replacement、CT-based planning、gap balancing 等定位，并用这些关键词实时搜索公开网页，抽取官网和公开邮箱后入库。为避免搜索引擎临时不可用导致演示完全无结果，后端还内置了一组经人工验证的官网种子 URL；运行时仍会实时打开这些官网页面抽取邮箱，不保存伪造联系人。中文 PDF 是扫描图像，当前不做 OCR。

## 结构

- `backend/`: FastAPI + PostgreSQL API
- `frontend/`: Vue + Vite 操作台
- `agent/`: Pi/pi-mono Node sidecar，默认加载 `overseas-distributor-prospecting`
- `skills/overseas-distributor-prospecting/`: 给 agent 使用的拓客 workflow skill
- `docs/superpowers/`: 设计文档和实施计划
- `docs/business/`: 客户业务输入（代理商/KOL 筛选标准、邮件模板、渠道开发信息表）

## 登录与权限（RBAC）

系统内置一套完整的权限体系：用户名+密码登录、签发 JWT、自定义角色 + 操作级权限。除 `GET /health` 外的所有接口都需要认证，前端会先登录再使用，并按权限显隐功能与菜单。

- **默认管理员**：`admin` / `admin123`（首次登录后请在「用户菜单 → 修改密码」尽快修改）。
- **内置角色**（可改权限，不可删）：`管理员`（全部）、`操作员`（获客+触达，不含系统/用户配置）、`只读`。
- **自定义角色**：管理员在「用户与权限」页新建角色、勾选操作级权限，再分配给用户。
- **操作级权限**：线索查看/搜索/编辑/删除、触达查看/生成/发送、回复分析、Agent 使用/配置、系统设置、用户与角色管理。
- **接口**：`POST /auth/login`、`GET /auth/me`、`POST /auth/change-password`；管理端 `/admin/permissions`、`/admin/roles`、`/admin/users`（需 `users.manage`）。
- **JWT 密钥**：默认自动生成并持久化在 settings 表，可用环境变量 `MEDBOT_AUTH_SECRET` 覆盖。

## 发送节流与队列（保护域名声誉）

外联邮件**不瞬时群发**，而是进入发送队列由后台 worker 按速率发出，避免触发垃圾邮件过滤、保住公司域名声誉：

- 手动发送、AI 自动发送、草稿批准都只是**入队**（事件状态 `queued`），后台按节流限制逐封发出。
- 可配置：每日发送上限 `send_daily_cap`（默认 200）、最小发送间隔 `send_min_interval_seconds`（默认 20s）、单域名每日上限 `send_per_domain_daily_cap`（默认 25）。在「设置 → 同步」页调整。
- 发送前再次检查抑制名单；命中则跳过记为 `suppressed`。
- **退信处理**：`/replies/sync` 识别 NDR/退信报文，自动把失败地址加入抑制名单（reason `bounce`）。
- 队列状态见 `GET /campaigns/queue`，前端「设置 → 同步」页有可视化（排队中 / 今日已发 / 每日上限）。

## 安全加固

- **CORS**：用 Bearer token（非 cookie），已关闭 `allow_credentials`，源可经 `MEDBOT_CORS_ORIGINS` 锁定（默认 `*`，生产应设为前端域名）。
- **登录防爆破**：同一 IP+用户名 15 分钟内失败 5 次即锁定（HTTP 429），成功登录清零。
- **强制改密**：默认管理员及被重置密码的用户，下次登录必须先改密码（前端强制弹窗、不可跳过）。
- **密钥加密存储**：DB 中的 LLM key、邮箱密码用 Fernet 加密（密钥派生自服务端 secret），接口只返回脱敏预览。

## 合规：退订 / 抑制名单 / 审计日志

面向真实医生的冷邮件需要满足 CAN-SPAM / GDPR，系统内置三道合规机制：

- **退订**：每封发出的邮件自动附带一个**按收件人签名**的退订链接（语言随正文中英自适应）。收件人点击 `GET /unsubscribe?token=...`（公开、无需登录）即被加入抑制名单并停止跟进。同时按 RFC 8058 设置了 `List-Unsubscribe` / `List-Unsubscribe-Post` 邮件头（`POST /unsubscribe` 是给邮箱客户端一键退订用的目标地址，不渲染网页），Gmail/Outlook/Yahoo 会据此在收件箱直接显示原生"退订"按钮，也是判断"正规发件人"、避免被判定为垃圾邮件的重要信号。
- **抑制名单（do-not-email）**：抑制名单内的邮箱**永不发送**。来源包括：退订链接点击、回复"不感兴趣"自动入库、手动添加退信/投诉地址。所有发送入口（手动、自动、草稿批准、全部批准）都会在发送前检查并跳过，记录为 `suppressed` 状态。
- **审计日志**：关键操作落库可追溯——登录、邮件发送、退订、抑制名单增删、用户/角色/权限变更、线索删除、系统设置变更（密钥值不记录）。

接口：`GET/POST /unsubscribe`（公开）；`GET/POST/DELETE /admin/suppressions`、`GET /admin/audit`（需 `users.manage`）。前端在「用户与权限」页的「抑制名单」「审计日志」两个标签管理。退订页可访问的对外地址由 `MEDBOT_PUBLIC_URL`（或 settings `public_base_url`）配置，默认 `http://localhost:8000`。

**反垃圾邮件（deliverability）**：除退订头外，系统还有发送节流（日上限/单域名上限/发送间隔）、默认草稿模式（人工审核后再发）、纯文本无附件邮件正文。`SPF`/`DKIM`/`DMARC` 是发件域名的 DNS 配置，应用层管不了，需要在企业邮箱/DNS 那边单独配置——这是比任何应用层策略优先级都高的一环。

### Agent 调用后端的服务令牌

后端接口启用鉴权后，Pi agent sidecar 需要凭「服务令牌」访问后端业务接口：

- 后端设置环境变量 `MEDBOT_SERVICE_TOKEN`，agent 设置 `agent/.env` 的 `BACKEND_SERVICE_TOKEN`，两者必须一致。
- agent 会在每个后端请求带上 `X-Service-Token`，以服务身份（全部业务权限）通过鉴权。
- `scripts/deploy.sh` 会自动生成并同步该令牌到 `.env` 和 `agent/.env`（与 `AGENT_TOKEN` 相同机制）。
- 本地手动启动时，需自己在后端进程的环境里设置 `MEDBOT_SERVICE_TOKEN`，并把同一值写入 `agent/.env` 的 `BACKEND_SERVICE_TOKEN`，否则 Agent 调用后端会返回 401。

## 后端

```bash
cd backend
uv run pytest -v
uv run uvicorn app.main:app --reload --port 8000
```

后端使用 PostgreSQL（psycopg3 + 连接池）。通过环境变量 `MEDBOT_DATABASE_URL` 指定连接串，例如 `postgresql://medbot:medbot@localhost:5432/medbot`；Docker Compose 部署时由 `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` 自动拼装。

主要接口：

- `GET /product/profile`: 读取根目录产品资料并生成产品画像
- `POST /agent/chat`: 代理到本地 Pi agent sidecar，前端 Agent 面板使用这个接口
- `POST /agent/chat/stream`: 以 `text/event-stream` 代理 Agent 实时输出、工具事件和完成状态
- `GET /agent/config`: 返回 Agent provider、模型和脱敏 key 预览
- `PUT /agent/config`: 从 Web 写入 `agent/.env` 的 `PI_PROVIDER`、provider API key、`PI_MODEL`、`BACKEND_BASE_URL`
- `POST /leads/search`: 默认执行真实网页搜索；传 `real_search: false` 才使用离线样例
  - 搜索引擎唯一使用 Tavily（需设置环境变量 `TAVILY_API_KEY`），不再有 DuckDuckGo/Bing 网页抓取兜底——国内网络环境下直连抓取经常被限流或屏蔽，与其静默降级返回不可靠结果，未配置 `TAVILY_API_KEY` 或调用失败时接口直接返回 502 报错。
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
- `get_scoring_rules`：读取当前生效的线索打分规则（权重/加减分/分数区间），管理员可在「设置 → 评分规则」页自定义，Agent 打分前必须先调用这个工具而不是套用文档里的默认值。
- `web_search`
- `fetch_url`
- `search_leads`
- `list_leads`
- `add_leads`
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

## Docker Compose 部署

推荐用 Docker Compose 部署，仓库已经包含前端、后端、Agent sidecar 和 PostgreSQL 的容器编排。前端容器用 Nginx 托管静态文件，并把浏览器里的 `/api/*` 同源反代到后端；后端通过容器网络访问 `http://agent:8011`；PostgreSQL 数据持久化在 `medbot-pgdata` volume。

首次部署：

```bash
cp .env.deploy.example .env
cp agent/.env.example agent/.env
# 编辑 agent/.env，配置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY、PI_PROVIDER、PI_MODEL
./scripts/deploy.sh
```

脚本会检查 Docker/Compose、自动创建缺失的 `.env` 和 `agent/.env`，然后执行：

```bash
docker compose up -d --build
```

部署脚本还会自动生成并同步 `AGENT_TOKEN` 到 `.env` 和 `agent/.env`。这是后端容器调用 Agent sidecar 的内部 Bearer token；如果手动编辑其中一个文件，要保持两个文件里的 `AGENT_TOKEN` 一致。

默认访问地址：

- Web：`http://localhost:5173`
- Backend health：`http://localhost:8000/health`

常用运维命令：

```bash
docker compose ps
docker compose logs -f backend agent frontend
docker compose restart agent
docker compose down
```

如果部署到服务器并使用域名，把 `.env` 里的 `PUBLIC_ORIGIN` 改为真实访问地址。Agent 配置仍写入 `agent/.env`，该文件被 `.gitignore` 排除，不会上传密钥。

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
