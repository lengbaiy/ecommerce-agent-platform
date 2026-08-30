# API、任务状态与 SSE

## 1. 使用现有统一 API

| Method | Path | 作用 |
| --- | --- | --- |
| POST | /api/v1/agent/tasks | 创建市场机会任务 |
| GET | /api/v1/agent/tasks/{id} | 查询状态和结果 |
| GET | /api/v1/agent/tasks/{id}/events | 订阅 SSE |
| POST | /api/v1/agent/tasks/{id}/cancel | 取消任务 |

不增加页面直连 Graph 的接口。

## 2. 创建任务

请求中的 intent 固定为 market_entry。business_context 中保存 MarketIntelligenceRequest，constraints 保存用户约束。

API先使用鉴权结果覆盖 tenant_id 和 user_id，再创建 task_id 和 trace_id。

## 3. Dispatcher

TaskService 内部使用执行器映射：

    market_entry -> MarketIntelligenceTaskExecutor

MarketIntelligenceTaskExecutor 调用 MarketIntelligenceService。inline 和 worker 都使用该映射。

当前其他 intent 的执行方式不在本文档中展开。修改 Dispatcher 时必须保证它们原有行为不受影响。

## 4. 查询结果

GET任务接口至少返回：

| 字段 | 说明 |
| --- | --- |
| id | task_id |
| status | 当前状态 |
| current_step | 当前节点 |
| retry_count | 重试次数 |
| degraded_flags | 降级原因 |
| error | 错误码和说明 |
| result | MarketIntelligenceReport |
| created_at、updated_at | 时间 |

只有同租户用户可以读取任务。

## 5. SSE 事件

| 事件 | 说明 |
| --- | --- |
| task.planning | 开始准备任务 |
| task.running | 开始执行 |
| node.started | 节点开始 |
| tool.started | Tool 开始 |
| tool.completed | Tool 完成 |
| tool.failed | Tool 失败 |
| node.retrying | 节点重试 |
| task.degraded | 进入降级 |
| task.completed | 报告完成 |
| task.failed | 任务失败 |
| task.cancelled | 任务取消 |

每个事件包含 event_id、task_id、trace_id、state_version、step、timestamp 和安全的摘要。

## 6. 断线恢复

- 客户端保存 task_id 和最后 event_id。
- 重连时提交 Last-Event-ID。
- 服务端先补发缺失事件，再推送新事件。
- 如果事件已经过期，客户端调用 GET 任务接口读取当前状态和最终结果。

## 7. 状态持久化顺序

    更新数据库和 Checkpoint
      -> 提交事务
      -> 发布 SSE 事件

页面看到事件时，对应状态必须已经可以通过 GET 查询。

## 8. 取消

取消接口具有租户和用户权限检查。已完成、失败或取消的任务再次取消时返回稳定业务错误。取消请求成功后不再调度后续 Graph 节点。

