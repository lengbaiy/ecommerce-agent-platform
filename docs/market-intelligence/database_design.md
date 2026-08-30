# 项目数据库设计

## 1. 文档基线

本文描述项目当前 PostgreSQL 持久化结构，核对依据如下：

| 依据 | 作用 |
| --- | --- |
| `backend/app/db/models.py` | 当前 ORM 目标结构 |
| `backend/migrations/versions/` | 数据库结构演进记录 |
| PostgreSQL `information_schema` | 当前运行数据库的实际结构 |
| Repository 与 Persistence 实现 | 表的真实读写方式和事务边界 |

当前运行数据库使用 PostgreSQL 16，Alembic 版本为 `20260825_0006`。除 `alembic_version` 外，共有 14 张业务表。

## 2. 数据库总览

| 领域 | 表 | 作用 |
| --- | --- | --- |
| 任务中心 | `agent_task` | 保存任务输入、状态、Worker 租约和最终结果 |
| 任务中心 | `task_event` | 保存可回放的任务事件，为 SSE 断线恢复提供数据 |
| 任务中心 | `agent_step` | 保存 Graph 节点每次执行的状态和错误 |
| 任务中心 | `tool_call` | 保存 Tool 调用、幂等键和输入输出 |
| 任务中心 | `graph_checkpoint` | 保存 Graph 状态快照，用于恢复执行 |
| 市场情报 | `market_intelligence_report` | 保存市场情报最终报告及内容哈希 |
| 市场情报 | `collection_run` | 保存一次商品或评论采集批次 |
| 市场情报 | `product_snapshot` | 保存标准化商品快照 |
| 市场情报 | `review_snapshot` | 保存标准化评论快照 |
| 市场情报 | `evidence_reference` | 保存报告证据与来源追溯信息 |
| 审批 | `approval` | 保存任务结果或动作的审批记录 |
| 认证 | `user_account` | 保存租户用户、角色和登录安全状态 |
| 认证 | `captcha_challenge` | 保存滑块验证码挑战状态 |
| 认证 | `auth_session` | 保存登录会话及吊销状态 |

## 3. 公共字段

多数任务和市场情报表继承 `TenantAuditRecord`。

| 字段 | 数据库类型 | 约束 | 作用 |
| --- | --- | --- | --- |
| `id` | `varchar(36)` | 主键、非空 | UUID 字符串标识 |
| `tenant_id` | `varchar(64)` | 非空、索引 | 租户隔离键 |
| `trace_id` | `varchar(64)` | 非空、索引 | 全链路追踪标识 |
| `created_at` | `timestamptz` | 非空 | 记录创建时间 |

`user_account`、`captcha_challenge` 和 `auth_session` 使用各自的认证字段，没有继承该基类。

## 4. 任务中心表

### 4.1 `agent_task`

保存任务的权威状态，同时支持 Worker 领取、续租、取消、乐观锁和最终结果校验。

| 字段组 | 字段 | 作用 |
| --- | --- | --- |
| 身份 | `id`、`tenant_id`、`trace_id`、`user_id` | 标识任务、租户、链路和发起人 |
| 请求 | `intent`、`user_query`、`request_payload` | 保存任务意图、原始输入和结构化请求 |
| 状态 | `status`、`current_step`、`retry_count` | 保存任务状态、当前步骤和重试次数 |
| 并发 | `state_version`、`updated_at` | 使用状态版本进行乐观并发控制 |
| Worker | `claimed_by`、`lease_expires_at`、`heartbeat_at` | 保存 Worker 所有权、租约和心跳 |
| 取消 | `cancel_requested_at` | 保存取消请求时间 |
| 结果 | `result_payload`、`result_hash`、`completed_at` | 保存任务结果、内容哈希和完成时间 |
| 审批摘要 | `approval_status`、`approval_hash`、`approver_id` | 保存当前审批状态和最后审批信息 |
| 兼容字段 | `events`、`error` | 保留旧事件 JSON 和任务错误文本 |

主要索引：`tenant_id`、`trace_id`、`user_id`、`status`、`intent`、`approval_status`、`claimed_by`、`lease_expires_at`。

### 4.2 `task_event`

保存结构化任务事件，是进度查询、SSE 推送和断线恢复的持久化事件流。

| 字段 | 作用 |
| --- | --- |
| `task_id` | 逻辑关联任务 |
| `event_type` | 任务、节点或 Tool 事件类型 |
| `state_version` | 事件产生时的任务状态版本 |
| `step` | 所属 Graph 步骤，可空 |
| `status` | 事件产生时的任务状态 |
| `summary` | 事件摘要 |
| 公共审计字段 | 租户、Trace 和事件时间 |

主要索引：`tenant_id`、`trace_id`、`task_id`、`event_type`、`status`。`agent_task.events` 用于兼容存量数据，新事件以本表为主要回放来源。

### 4.3 `agent_step`

保存每次 Graph 节点执行，用于展示节点进度和定位失败步骤。

| 字段 | 作用 |
| --- | --- |
| `task_id` | 逻辑关联任务 |
| `step_name` | Graph 节点名称 |
| `status` | 节点执行状态 |
| `attempt` | 节点执行次数 |
| `state_version` | 节点结束时的状态版本，可空 |
| `error_code` | 节点错误码，可空 |
| `started_at`、`finished_at` | 节点执行时间范围 |

主要索引：`tenant_id`、`trace_id`、`task_id`、`step_name`、`status`。

### 4.4 `tool_call`

保存 Tool 调用记录，并通过幂等键避免 Worker 重试造成重复调用。

| 字段 | 作用 |
| --- | --- |
| `task_id` | 逻辑关联任务 |
| `tool_name`、`step_name` | Tool 名称和所属 Graph 节点 |
| `status`、`error_code` | 调用状态和稳定错误码 |
| `attempt` | 当前调用次数 |
| `idempotency_key` | Tool 调用幂等键，可空但全表唯一 |
| `request_payload` | ToolRequest JSON，可空 |
| `response_payload` | ToolResponse JSON，可空 |
| `started_at`、`finished_at` | 调用时间范围 |

主要索引：`tenant_id`、`trace_id`、`task_id`、`tool_name`、`status`。`idempotency_key` 具有唯一约束。

### 4.5 `graph_checkpoint`

保存每个成功节点后的不可变 Graph State，用于 Worker 异常后的恢复执行。

| 字段 | 作用 |
| --- | --- |
| `task_id` | 逻辑关联任务 |
| `graph_name` | Graph 名称，市场情报使用 `market_intelligence` |
| `current_step` | Checkpoint 对应步骤 |
| `state_version` | 状态版本 |
| `state_payload` | 完整 MarketIntelligenceState JSON |

唯一约束：`(task_id, graph_name, state_version)`。主要索引：`tenant_id`、`trace_id`、`task_id`、`graph_name`。

## 5. 市场情报表

### 5.1 `market_intelligence_report`

保存一个市场任务的最终结构化报告，并使用哈希校验报告内容。

| 字段 | 作用 |
| --- | --- |
| `task_id` | 逻辑关联任务；每个任务唯一 |
| `report_id` | 报告公共标识；全表唯一 |
| `schema_version` | MarketIntelligenceReport 契约版本 |
| `status` | `COMPLETED`、`DEGRADED` 或 `FAILED` |
| `report_hash` | 规范化报告 JSON 的 SHA-256 |
| `report_payload` | 完整 MarketIntelligenceReport JSON |

唯一约束：`task_id`、`report_id`。主要索引：`tenant_id`、`trace_id`、`task_id`、`report_id`、`status`、`report_hash`。

### 5.2 `collection_run`

保存一次商品搜索或评论读取批次，是快照和证据的直接父记录。

| 字段 | 作用 |
| --- | --- |
| `task_id` | 逻辑关联任务 |
| `keyword` | 本次采集关键词 |
| `requested_count`、`actual_count` | 请求数量和实际数量 |
| `status` | 批次执行状态 |
| `stop_reason` | 部分完成或失败原因，可空 |
| `adapter_version`、`parser_version` | Adapter 和解析器版本 |
| `started_at`、`finished_at` | 批次时间范围 |

主要索引：`tenant_id`、`trace_id`、`task_id`、`keyword`、`status`。

### 5.3 `product_snapshot`

保存 `NormalizedProduct` 的一次采集快照，为竞品矩阵、样本指标和商品证据提供数据。

| 字段组 | 字段 | 作用 |
| --- | --- | --- |
| 归属 | `collection_run_id` | 外键关联采集批次，批次删除时级联删除 |
| 范围 | `platform`、`market`、`product_id` | 平台、市场和商品标识 |
| 商品 | `title`、`brand`、`category`、`shop_name` | 商品及店铺描述 |
| 价格 | `price numeric(18,4)`、`currency varchar(3)` | 必填价格和 ISO 币种 |
| 销量 | `sales_display`、`sales_value`、`sales_value_type` | 原始销量文字、解析值和语义 |
| 反馈 | `rating numeric(18,4)`、`review_count` | 商品评分和评论数 |
| 来源 | `source_ref`、`source_url`、`source_snapshot_ref` | 来源记录、链接和快照引用 |
| 时间 | `source_timestamp`、`ingest_timestamp` | 源数据时间和入库时间 |
| 质量 | `source_type`、`data_status` | 数据源模式和数据质量状态 |

唯一约束：`(collection_run_id, platform, product_id)`。主要索引包括批次、平台、市场、商品、类目、来源类型和数据状态。

### 5.4 `review_snapshot`

保存 `NormalizedReview` 快照，为评论洞察、代表性评论和评论证据提供数据。

| 字段组 | 字段 | 作用 |
| --- | --- | --- |
| 归属 | `collection_run_id` | 外键关联采集批次，批次删除时级联删除 |
| 范围 | `platform`、`market`、`review_id`、`product_id` | 平台、市场、评论和商品标识 |
| 评论 | `content`、`rating`、`review_time` | 脱敏评论内容、评分和时间 |
| 属性 | `verified_purchase`、`helpful_count` | 已验证购买和有用数 |
| 分析 | `sentiment`、`themes` | 可空情感和主题 JSON |
| 来源 | `source_ref`、`source_snapshot_ref` | 评论来源和快照引用 |
| 时间 | `source_timestamp`、`ingest_timestamp` | 源数据时间和入库时间 |
| 质量 | `data_status` | 数据质量状态 |

唯一约束：`(collection_run_id, platform, review_id)`。主要索引包括批次、平台、市场、评论、商品和数据状态。

### 5.5 `evidence_reference`

保存 EvidenceReference，使最终报告可以追溯到 Tool、采集批次、商品或评论快照。

| 字段组 | 字段 | 作用 |
| --- | --- | --- |
| 归属 | `collection_run_id` | 外键关联采集批次，批次删除时级联删除 |
| 类型 | `evidence_type`、`data_level` | 证据类型和 A/B/C/D 等级 |
| 来源 | `data_source`、`platform` | 数据来源和平台 |
| 对象 | `product_id`、`review_id` | 关联商品或评论，可空 |
| 范围 | `query_range`、`sample_scope` | 查询条件和实际样本范围 JSON |
| 链路 | `tool_call_id` | 逻辑关联 Tool 调用 |
| 快照 | `snapshot_ref`、`sha256`、`data_version` | 快照引用、哈希和数据版本 |
| 时间 | `source_timestamp`、`ingest_timestamp` | 源数据时间和入库时间 |

主要索引包括批次、证据类型、平台、商品、评论、Tool 调用和哈希。

## 6. 审批与认证表

### 6.1 `approval`

保存审批审计记录，并通过 `result_hash` 绑定被审批的结果内容。

| 字段 | 作用 |
| --- | --- |
| `task_id` | 逻辑关联任务 |
| `action` | 审批动作 |
| `result_hash` | 被审批结果的内容哈希 |
| `approver_id`、`approver_roles` | 审批人及审批时角色快照 |
| `reason` | 审批原因，可空 |

主要索引：`tenant_id`、`trace_id`、`task_id`、`action`、`approver_id`。

### 6.2 `user_account`

保存租户用户、角色和登录安全状态。

| 字段 | 作用 |
| --- | --- |
| `id`、`tenant_id`、`username` | 用户、租户和登录名 |
| `display_name`、`roles` | 展示名称和角色 JSON |
| `password_hash` | 密码哈希 |
| `enabled` | 账号是否启用 |
| `failed_attempts`、`locked_until` | 登录失败次数和锁定时间 |
| `last_login_at`、`created_at` | 最近登录和创建时间 |

唯一约束：`(tenant_id, username)`。主要索引：`tenant_id`、`username`。

### 6.3 `captcha_challenge`

保存滑块验证码挑战及其消费状态。

| 字段 | 作用 |
| --- | --- |
| `id`、`target_x` | 挑战 ID 和正确滑块位置 |
| `attempts`、`verified` | 尝试次数和验证状态 |
| `login_consumed` | 是否已被登录流程消费 |
| `created_at`、`expires_at` | 创建和过期时间 |

主要索引：`expires_at`。

### 6.4 `auth_session`

保存登录会话、过期时间和吊销状态。

| 字段 | 作用 |
| --- | --- |
| `id` | Session 主键 |
| `tenant_id`、`user_id` | 会话所属租户和用户 |
| `created_at`、`expires_at` | 会话创建和过期时间 |
| `revoked` | 会话是否已吊销 |

主要索引：`tenant_id`、`user_id`、`expires_at`。

## 7. 关系与约束

### 7.1 数据库实际外键

| 子表 | 外键 | 父表 | 删除规则 |
| --- | --- | --- | --- |
| `product_snapshot` | `collection_run_id` | `collection_run.id` | `ON DELETE CASCADE` |
| `review_snapshot` | `collection_run_id` | `collection_run.id` | `ON DELETE CASCADE` |
| `evidence_reference` | `collection_run_id` | `collection_run.id` | `ON DELETE CASCADE` |

### 7.2 逻辑关联

以下关系由 Repository、租户条件和事务保证，当前数据库没有创建外键：

| 字段 | 逻辑目标 |
| --- | --- |
| 各运行表的 `task_id` | `agent_task.id` |
| `agent_task.user_id`、`auth_session.user_id` | `user_account.id` |
| `evidence_reference.tool_call_id` | `tool_call.id` 或 ToolRequest 中的调用 ID |
| `approval.approver_id` | `user_account.id` |
| `product_id`、`review_id` | 对应平台业务标识或快照记录 |

当前设计允许任务审计数据独立保留，避免级联删除任务时丢失执行历史。业务删除需求确定后，再通过新迁移增加外键或归档策略。

## 8. 核心事务与并发规则

| 场景 | 数据库规则 |
| --- | --- |
| 创建任务 | `agent_task` 与初始 `task_event` 在同一事务提交 |
| 更新任务 | 使用 `state_version` 条件更新，冲突时抛出并发异常 |
| Worker 领取 | PostgreSQL 使用 `FOR UPDATE SKIP LOCKED`，避免重复领取 |
| Worker 续租 | 校验 `claimed_by` 后更新心跳和租约过期时间 |
| 节点执行 | 每次尝试新增一条 `agent_step`，完成时更新状态和错误码 |
| Tool 执行 | `idempotency_key` 唯一；完成结果可被恢复执行复用 |
| 保存采集 | `collection_run`、快照和证据在同一事务写入，任一失败整体回滚 |
| 保存 Checkpoint | `(task_id, graph_name, state_version)` 保证状态版本唯一 |
| 完成任务 | 任务、事件、最终报告和报告哈希在同一事务提交 |
| 审批 | 任务审批状态、事件和 `approval` 记录在同一事务提交 |

## 9. 多租户与敏感数据

| 规则 | 当前设计 |
| --- | --- |
| 租户隔离 | Repository 查询和更新必须包含 `tenant_id` |
| 数据库级隔离 | 当前未启用 PostgreSQL Row Level Security |
| 评论内容 | 入库前脱敏，页面只展示允许返回的内容 |
| 认证信息 | 只保存密码哈希，不保存明文密码 |
| Tool Payload | 不得写入 Access Token、Secret 等凭据 |
| 快照路径 | 普通 API 不返回内部存储路径 |
| JSON 契约 | 请求、结果、Checkpoint、Tool 输入输出和报告保留 `schema_version` |

## 10. 数据生命周期

| 数据 | 建议保留策略 |
| --- | --- |
| `agent_task`、`approval`、最终报告 | 按业务审计周期保留 |
| `task_event`、`agent_step`、`tool_call` | 保留到任务审计周期结束，可归档历史事件 |
| `graph_checkpoint` | 任务完成后保留最近版本或按周期清理 |
| `collection_run`、商品、评论和证据 | 按数据授权、平台协议和证据追溯周期保留 |
| `captcha_challenge` | 过期后短周期清理 |
| `auth_session` | 过期或吊销后按安全审计周期清理 |

删除 `collection_run` 会级联删除商品快照、评论快照和证据，清理前必须确认相关报告已不需要证据追溯。

## 11. 完整数据链路

| 阶段 | 持久化结果 |
| --- | --- |
| 创建任务 | `agent_task`、`task_event` |
| Worker 领取 | 更新 `agent_task` 租约并新增事件 |
| Graph 执行 | `agent_step`、`tool_call`、`task_event` |
| Tool 采集 | `collection_run`、商品/评论快照、`evidence_reference` |
| 节点完成 | `graph_checkpoint` |
| 报告生成 | `market_intelligence_report`、`agent_task.result_payload` |
| 结果审批 | `approval` 和审批事件 |

市场情报主要追溯关系：

```text
agent_task
  -> tool_call
  -> collection_run
       -> product_snapshot / review_snapshot
       -> evidence_reference
  -> market_intelligence_report
```

报告中的关键事实通过 `evidence_id` 找到 `evidence_reference`，再根据采集批次、快照引用、Tool 调用和 SHA-256 回溯数据来源。
