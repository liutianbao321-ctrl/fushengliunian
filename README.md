# 浮生流年

面向百万字长篇创作的 AI 小说生产系统。它不是一次性续写器，而是把建书、事实研究、长篇规划、逐章写作、审稿、记忆更新和读者反馈组织成可恢复、可审计的创作工作流。

## 当前能力

- 创作工作室：从原始想法生成 4～6 个互补创作支柱，由作者选择主支柱并融合成同一本书，不再要求三选一。
- 高质量建书：持久化保存方向、作者决策、故事基座和版本，并用读者编辑、长篇架构师视角模拟开篇、中期、后期与终局压力。
- 受控联网研究：后端直接调用阿里云百炼 WebSearch MCP，一次检索后独立整理事实备忘录和引用来源；资料只作为外部参考，不覆盖小说 Canon。
- 场景契约：每章明确视角、目标、阻力、行动、决定、后果、状态变化和下一章承诺，减少空转、跳戏和人物行为断裂。
- 长篇记忆：组合创作宪章、世界设定、人物状态、伏笔账本、最近章节、卷级规划、Wiki、全文检索和向量检索，并按节点控制上下文预算。
- 反馈学习：把作者接受、修改和拒绝的结果记录成反馈事件与风格样本，后续章节可以复用，而不是每次从零开始。
- 可靠生成：任务租约、幂等节点、断点恢复、质量门、原子发布、SSE 回放和 transactional outbox，生成失败不会污染已发布正文。

## 生产架构

- FastAPI API：JWT、项目/章节/Wiki/检索、幂等生成命令、可回放 SSE。
- Durable worker：PostgreSQL `SKIP LOCKED` 领取、租约心跳、崩溃恢复、节点级幂等、暂停/恢复。
- 角色化创作流水线：故事总监、事实研究编辑、长篇架构师、场景规划、Writer、Editor、Canon Observer 等角色由持久化状态机编排，不依赖自由聊天式多 Agent 相互猜测上下文。
- Canon 数据层：chapter revisions、append-only state events、current-state projection、Wiki revisions。
- 长篇检索：PostgreSQL FTS + pgvector + entity RRF，以及书→卷→章分层 PageIndex。
- 写作知识库：原文证据 RAG + 可追溯方法卡 + 目录树导航，和小说 Canon 严格隔离。
- 发布链路：九道质量门、原子发布、索引任务、transactional outbox、SSE backlog。

## 本地验证

后端要求 Python 3.12 和 PostgreSQL 16 + pgvector：

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/pytest -q
.venv/bin/ruff check app tests alembic
.venv/bin/uvicorn app.main:app --port 8100
```

前端要求 Node.js 22+：

```bash
cd frontend
npm ci
npm audit --audit-level=moderate
npm run build
npm run dev
```

`LLM_BACKEND=mock` 只用于开发联调。`ENV=production` 会拒绝 mock、弱 `SECRET_KEY` 和通配 CORS。

## 模型配置

后端直接调用 OpenAI 兼容的 `/chat/completions` 接口。每个节点自动加载
[backend/skills](./backend/skills) 对应的 `SKILL.md`，不再需要独立 Agent Gateway：

```dotenv
LLM_BACKEND=openai_compatible
LLM_BASE_URL=https://your-llm-endpoint/v1
LLM_API_KEY=your-api-key
LLM_MODEL=deepseek-chat
```

`backend/.env` 已忽略且应保持 `0600` 权限。开发联调可使用 `LLM_BACKEND=mock`；
mock 模式也能体验多卷树、卷末再规划和章纲确认流程，但不会生成真实正文。

### WebSearch（可选）

联网研究使用独立的阿里云百炼 Workspace 与 WebSearch API Key。后端通过标准 MCP `tools/call` 精确执行一次搜索，再使用 Responses API 整理来源；搜索失败会显示降级状态，但不会阻塞故事基座生成。

```dotenv
WEB_SEARCH_ENABLED=true
WEB_SEARCH_BASE_URL=https://your-workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
WEB_SEARCH_MCP_URL=https://your-workspace.cn-beijing.maas.aliyuncs.com/api/v1/mcps/WebSearch/mcp
WEB_SEARCH_API_KEY=your-websearch-api-key
WEB_SEARCH_MODEL=qwen3.6-plus
WEB_SEARCH_TIMEOUT_SECONDS=240
```

未配置时 `/readyz` 返回 `web_search: disabled`；配置完整并启动成功后返回 `web_search: ready`。API Key 只能放在本机 `backend/.env` 或服务器 `/etc/fushengliunian/backend.env`，不得提交到仓库。

## 长篇规划

- 建书流程为“原始想法 → 多支柱融合 → 联网事实研究 → 故事基座 → 百万字压力测试 → 作者确认 → 第一章试写”。每一步都可恢复，不依赖浏览器一直在线。
- 新项目按目标字数建立书→卷的多卷锚点，第一卷详细规划，后续卷滚动规划。
- 设定管理→大纲可查看书→卷→事件弧树；旧项目可一键安全升级为多卷结构。
- 规划下一卷时，系统自动汇总人物状态、活跃伏笔、最近章节和上一卷结果。
- 章纲确认前会展示“为什么建议这样写”、当前事件弧和临期伏笔。
- 正文发布后 observer 把人物、时间、物品和伏笔变化写回 Canon，供下一章重新装配。

## 作者心意与写作知识库

新书向导会先建立作者创作宪章，保存写作动机、期望余味、不可妥协项、AI 授权范围和每章验收问题。AI 可以在宪章内自动规划和写作，但阻断质量门失败时只保留待审稿，不更新 Canon，也不会继续下一章。

写作指导库的抽样研究、RAG 导入、LLM Wiki/PageIndex 使用边界及 pgvector/Milvus 决策见 [docs/创作流程与写作知识库改造.md](./docs/创作流程与写作知识库改造.md)。

## 无 Docker 部署

Ubuntu 24.04 可直接使用 Python venv、Node.js、PostgreSQL、Nginx 和 systemd 部署。低内存单机模式只运行一个 API/worker 进程和一个 Next.js standalone 进程：

```bash
sudo ROOT=/opt/fushengliunian \
  UV_INDEX_URL=https://pypi.org/simple \
  ./deploy/build_baremetal.sh
sudo nginx -t
sudo systemctl reload nginx
curl --fail http://127.0.0.1:8100/readyz
```

生产环境变量放在 `/etc/fushengliunian/backend.env`，权限必须为 `0600`。服务定义见 `deploy/fushengliunian*.service`。

如需在同一 IP 的子路径临时发布，可增加 `NEXT_PUBLIC_BASE_PATH=/novel NEXT_PUBLIC_API_BASE=/novel/api` 后构建，并把 `deploy/nginx-path.conf` include 到现有 server 块；正式独立域名部署不设置这两个变量。

## 容器部署（可选）

复制 `deploy/.env.example` 为 `deploy/.env` 并替换所有密钥，然后执行：

```bash
cd deploy
docker compose build
docker compose up -d db migrate api worker frontend
curl --fail http://127.0.0.1:8100/readyz
```

[deploy/compose.yaml](./deploy/compose.yaml) 将迁移、API、worker 和前端分离。API 可横向扩容；worker 依靠数据库领取语义扩容。Nginx 配置见 [deploy/nginx.conf](./deploy/nginx.conf)。

## 数据与恢复

- 每次生成必须带 `Idempotency-Key`，同一请求不会重复发布。
- 每个生产节点保存 input/output hash；worker 重启后从已完成节点继续。
- 质量门未通过时 revision 保留为 `review_required`，不会污染 Canon 投影。
- 章节发布、状态事件、Wiki revision、索引任务和 outbox 在同一事务提交。
- SSE 使用持久 `ProjectEvent.sequence` 回放；浏览器断线后携带 `Last-Event-ID` 续传。
- 每日备份 PostgreSQL，并定期做 PITR 恢复演练；PageIndex 与 Current State 都可从不可变 revision/event 重建。

## 上线前检查

1. 执行 `alembic upgrade head`，`/readyz` 必须返回 ready，生产模型配置必须完整。
2. 使用生产模型跑一章，确认九门结果、revision、state event、Wiki revision 和两类 index run 均生成。
3. 在节点执行中杀掉 worker，确认租约过期后任务恢复且只发布一个 revision。
4. 验证 Nginx SSE 未缓冲、TLS 生效、数据库不暴露公网。
5. 对百万字样本执行跨卷人物状态、知识边界、伏笔到期和 PageIndex 导航回归测试。

## 开源与安全

- 项目采用 [MIT License](./LICENSE)。
- 仓库只提供 `.env.example`，不会包含模型、WebSearch、数据库或部署账号密钥。
- 提交前建议执行 `git diff --check`、后端完整测试、Ruff、前端构建和密钥扫描。
- 联网资料、导入作品和小说 Canon 分层存储；外部网页内容不能直接改写角色状态或世界设定。
