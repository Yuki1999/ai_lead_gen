# 私有化离线部署手册

面向「实施/交付工程师」。客户服务器通常在内网、无外网，所以采用**离线交付包**：在有网的构建机做好包，拷到客户机断网一键安装。

## 一、制作交付包（构建方，有网机器）

```bash
./scripts/make-offline-package.sh 1.0.0      # 版本号自定，不传则用 日期-gitSHA
```

产物：`dist/ai_lead_gen-offline-1.0.0.tar.gz`，内含三服务镜像、离线 compose、配置模板、安装/预检/冒烟脚本、交付清单 `MANIFEST.txt`、校验和 `SHA256SUMS`。

把这个 tar.gz（连同它的 SHA256 值）交付给现场。

## 二、现场安装（实施方，客户服务器，可断网）

前置：目标服务器已装 **Docker + Docker Compose v2**（离线环境用厂商 Docker 离线包先装好）。

```bash
tar xzf ai_lead_gen-offline-1.0.0.tar.gz
cd ai_lead_gen-offline-1.0.0
./install-offline.sh
```

安装脚本会依次：① 环境预检 → ② 校验包完整性 → ③ `docker load` 导入镜像 → ④ 生成内部令牌/配置 → ⑤ 启动 → ⑥ 冒烟测试。

完成后：
- Web：`http://<服务器IP>:5173`
- 默认管理员 `admin / admin123`（**首次登录强制改密**）

### 安装后必做
1. 登录改默认管理员密码。
2. 填 `agent/.env` 的大模型 key（`OPENAI_API_KEY` 或 `DASHSCOPE_API_KEY`），改完 `docker compose -f docker-compose.deploy.yml restart agent`。
3. 在「设置」页填企业邮箱（Exchange）信息。
4. 生产域名：改 `.env` 的 `PUBLIC_ORIGIN` 为真实访问地址。

## 三、升级

```bash
# 1) 先备份数据卷（重要）
docker run --rm -v medbot-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/medbot-data-$(date +%F).tar.gz -C /data .
# 2) 解压新版本包，复用旧的 .env 与 agent/.env，执行
./install-offline.sh
```

数据库 schema 由后端启动时自动迁移（向后兼容）。升级后务必跑一次 `./smoke-test.sh` 确认正常。

## 四、回滚

```bash
# 改 .env 的 IMAGE_TAG 为上一个版本号（镜像仍在本机），然后：
docker compose -f docker-compose.deploy.yml up -d
# 如涉及数据结构变更，先恢复对应版本的数据备份。
```

## 五、常用运维

```bash
docker compose -f docker-compose.deploy.yml ps        # 状态
docker compose -f docker-compose.deploy.yml logs -f   # 日志
docker compose -f docker-compose.deploy.yml restart agent
docker compose -f docker-compose.deploy.yml down       # 停止（数据卷保留）
```

数据持久化在 `medbot-data` 卷；删卷会丢数据，谨慎。

## 六、常见问题

- **端口被占用**：预检会报；改 `.env` 的 `FRONTEND_PORT`/`BACKEND_PORT` 后重装。
- **AI 功能报"未配置"**：`agent/.env` 没填 key，或改完没重启 agent 容器。
- **ARM/信创环境**：交付包镜像须在对应架构（arm64/鲲鹏）上构建；x86 镜像不能直接跑。
- **冒烟测试失败**：等 1-2 分钟容器起全再重试 `./smoke-test.sh`；仍失败看 `logs`。
