# 企业级开发底座说明

## 已落地的框架能力

- API 统一身份边界：账号密码登录、一次性滑块验证码、JWT 会话与企业 IdP JWT 模式。
- 用户管理、账号禁用、失败锁定、角色—权限映射与服务端权限校验。
- 服务端生成租户和用户上下文，任务查询、取消和审批均强制租户隔离。
- 操作员与审批人角色分离；审批记录包含审批人、角色、动作、理由和结果快照哈希。
- SQLAlchemy 持久化仓库，支持 SQLite 本地开发与 PostgreSQL 正式部署。
- Alembic 首版迁移；生产环境禁止自动建表。
- 乐观状态版本检查，防止并发任务更新静默覆盖。
- `inline` 与 `worker` 两种任务执行模式，共用相同 TaskService 和 Repository 契约。
- `/health` 存活检查与 `/ready` 数据库就绪检查。
- 请求 ID、安全响应头与结构化 JSON 日志。
- Web、移动 H5、API 三端构建与 CI；后端覆盖率门槛和依赖漏洞审计。

## 推荐扩展点

后续业务开发应实现接口而不是绕过分层：

- 新业务 Agent：放入 `backend/app/agents/`，通过 Supervisor 注册。
- 外部电商渠道：实现 `backend/app/adapters/` 下的 Adapter，不在 Agent 中直接请求平台。
- 模型调用：增加统一 Model Gateway，集中处理模型选择、限流、预算与审计。
- RAG：通过 `backend/app/rag/` 接入 Qdrant，并保留来源、版本和租户过滤条件。
- 文件与报告：通过对象存储服务写入 MinIO/S3，不直接写应用容器文件系统。
- 新 API：API 只处理 HTTP 契约和身份上下文，状态转换留在 Service。

## 正式部署前仍需完成

此仓库现在是可继续开发的企业工程底座，不代表已经具备生产业务能力。上线前仍需：

1. 将 JWT HMAC 配置替换为企业 IdP 的 OIDC/JWKS 验证。
2. 将 Worker 轮询升级为 Redis Streams、Celery、Dramatiq 或企业消息队列，并实现租约、重试和死信队列。
3. 接入 OpenTelemetry Collector、指标平台、错误聚合和告警规则。
4. 为真实 Tool 和渠道写操作增加持久化幂等键、超时、退避和熔断。
5. 增加 PostgreSQL 集成测试、E2E、性能、故障恢复和备份恢复演练。
6. 使用 Secret Manager、固定镜像版本、非 root 容器、TLS 和受控网络策略。
7. 将本地滑块挑战替换为企业验证码/风控服务，并增加 IP、设备、账号维度限流。
