# 电商智能运营 Agent 平台

本仓库依据《电商智能运营 Agent 平台项目需求规格说明书 V1.0》创建，并复用酒店项目已经验证的工程分层、GitHub 协作、Docker Compose 与“任务 -> Agent -> 审批 -> 审计”治理骨架。电商业务模型、Agent 路由、API、前端驾驶舱和测试均已按需求重新设计。

## 当前可运行闭环

`自然语言目标 -> Supervisor 规划/路由 -> 业务 Agent 结构化输出 -> Judge 证据检查 -> 完成或等待人工审批 -> 审计事件`

- 市场进入评估：市场、竞品、评论与利润约束的证据化报告骨架。
- 商品策略：定位、价格区间、卖点、差异化与风险。
- Listing：结构化内容与平台规则校验入口，正式方案需审批。
- 运营诊断：销售、流量、转化、库存的异常归因骨架。
- 治理基线：统一 AgentState、SSE 事件、审批快照哈希、租户字段、稳定 Tool 契约。

当前业务数据为明确标记的固定演示数据或 `unavailable`，不会伪装成真实平台数据，也不会连接生产电商账号。

## 技术栈

- Web：Vue 3、TypeScript、Vite、Pinia、CoreUI Vue、Chart.js
- API：FastAPI、Pydantic、SQLAlchemy
- Agent：LangGraph，1 个 Supervisor + 4 个业务 Agent
- 依赖：PostgreSQL、Redis、Qdrant、MinIO
- 部署：Docker Compose；后续可迁移 Kubernetes

## 快速开始

### Docker

```bash
cp .env.example .env
docker compose up --build
```

Web：`http://localhost:5173`，API 文档：`http://localhost:8000/docs`。

### 本地开发

```bash
# 后端（Python 3.11+）
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 前端（Node 20+）
cd frontend
npm install
npm run dev
```

Windows 可直接运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/Start-Local.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/Verify-Code.ps1
```

完整的环境准备、启动、停止与故障排查说明见 [docs/STARTUP.md](docs/STARTUP.md)。
企业级身份、租户、持久化、审批和任务执行底座说明见 [docs/ENTERPRISE_FOUNDATION.md](docs/ENTERPRISE_FOUNDATION.md)。
登录流程、会话策略与 RBAC 权限矩阵见 [docs/AUTHORIZATION.md](docs/AUTHORIZATION.md)。

## 目录

```text
backend/app/
  api/v1/                 PRD 定义的 HTTP 契约
  agents/                 Supervisor、业务 Agent 与 AgentState
  graph/                  LangGraph 编排与 Judge
  modules/                电商业务域边界
  tools/                  Tool 输入输出与确定性计算
  state/ rag/             Checkpoint 与知识检索扩展点
  observability/          Trace 与指标扩展点
frontend/                 Web 工作台、任务与经营驾驶舱
clients/mobile-ops/       可选移动运营端骨架
packages/                 跨端契约与 API 路径
docs/                     架构、追踪矩阵、API 与研发规范
data/                     脱敏固定数据集约定
```

## 实施顺序

1. M1：商品、市场、销售、库存模型与持久化任务状态。
2. M2：Tool、授权 Adapter、知识库、引用与数据质量。
3. M3：四类任务的真实模型节点、Checkpoint 与 SSE 增量事件。
4. M4：重试、熔断、降级、RBAC、审批和写入幂等。
5. M5：固定评测集、OpenTelemetry、Docker 验收与试点。

完整设计见 [docs/PROJECT_FRAMEWORK.md](docs/PROJECT_FRAMEWORK.md)，需求对应关系见 [docs/PRD_TRACEABILITY.md](docs/PRD_TRACEABILITY.md)。

## 开源界面说明

管理端界面基于 MIT 许可的 [CoreUI Free Vue Admin Template](https://github.com/coreui/coreui-free-vue-admin-template) 进行业务化改造。具体版本、上游提交及许可文本见 [frontend/THIRD_PARTY_NOTICES.md](frontend/THIRD_PARTY_NOTICES.md)。
