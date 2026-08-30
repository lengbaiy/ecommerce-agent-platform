# 错误、重试与降级

## 1. 原则

参数、权限和平台风控错误直接返回明确原因。临时技术错误可以按策略重试。数据不足时保留已经获得的结果，并告诉用户哪些结论受限。

## 2. 错误码

| 错误码 | 含义 | 是否重试 |
| --- | --- | --- |
| INVALID_ARGUMENT | 参数不合法 | 否 |
| TOOL_PERMISSION_DENIED | 租户无权限 | 否 |
| DATA_SOURCE_DISABLED | 数据源未启用 | 否 |
| UNSUPPORTED_DATA_SOURCE | 平台或模式不支持 | 否 |
| UNSUPPORTED_SORT | 数据源不支持排序 | 否 |
| DATA_EMPTY | 没有数据 | 否 |
| DATA_STALE | 数据过期 | 否，允许降级 |
| DATA_CONFLICT | 数据口径冲突 | 否，允许降级 |
| API_CREDENTIALS_MISSING | 官方API凭据不存在 | 否 |
| API_TOKEN_EXPIRED | Token失效且无法刷新 | 否 |
| API_PERMISSION_DENIED | 租户或应用没有接口权限 | 否 |
| API_INVALID_REQUEST | 官方API拒绝请求参数 | 否 |
| API_RATE_LIMIT | 官方API限流 | 按官方Retry-After处理 |
| API_QUOTA_EXHAUSTED | 当日配额耗尽 | 否 |
| API_UPSTREAM_UNAVAILABLE | 平台官方API临时不可用 | 按策略 |
| API_SCHEMA_CHANGED | 官方响应字段变化 | 否 |
| TOOL_TIMEOUT | 普通读 Tool 超时 | 按策略 |
| TOOL_UPSTREAM_ERROR | 授权 API 临时错误 | 按策略 |
| SCHEMA_VALIDATION_FAILED | Tool 或 Agent 输出不符合 Schema | 结构修复一次 |
| SCHEMA_VERSION_UNSUPPORTED | Schema 大版本不支持 | 否 |
| COLLECTION_INTERNAL_ERROR | 未分类采集错误 | 记录后失败 |

## 3. 重试规则

- Graph 节点默认最多重试 2 次。
- 每次重试记录 previous_attempt_id 和失败原因。
- 已成功的节点从 Checkpoint 读取。
- 官方API认证失败、权限不足、参数错误、配额耗尽和Schema变化不重试。
- 官方API限流按照Retry-After和平台规则重试，仍受节点最大重试次数限制。
- 写入采集批次和快照使用幂等键，避免重试产生重复记录。

## 4. 任务状态

任务状态：

    PENDING -> PLANNING -> RUNNING
      -> COMPLETED
      -> DEGRADED
      -> FAILED
      -> CANCELLED

临时错误重试时进入 RETRYING。每次状态改变先持久化，再发送 SSE。

## 5. 降级规则

| 情况 | 结果 |
| --- | --- |
| 有商品，无评论 | 继续生成竞品和样本统计，评论 unavailable |
| 有商品，无全市场指标 | 样本统计可用，全市场字段 unavailable |
| 有数据，无成本 | 利润 unavailable |
| 部分商品采集成功 | 任务 DEGRADED，保留部分结果 |
| 关键数据全部缺失 | 任务 FAILED |
| 多来源冲突 | 任务 DEGRADED，保留冲突证据 |

成本完整性由Graph检查。成本缺失时不调用ProfitCalculatorTool。

DEGRADED 报告必须包含 data_limitations，页面不能只显示“成功”。

## 6. 取消

- 用户取消后持久化 CANCELLED。
- Graph 在节点之间检查取消标记。
- 已发出的官方API请求按客户端能力取消；无法中断时忽略返回结果并停止后续调用。
- 已经保存的证据保留并标记任务已取消。
- 取消后不继续调用后续 Tool。
