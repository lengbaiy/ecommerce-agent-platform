# 官方 API 接口清单

## 1. 目的

本文记录 Official API Adapter 实际调用的接口。平台字段、分页参数和认证细节只存在于 Adapter 内，上层 Tool 继续使用统一请求和返回契约。

## 2. 接口登记表

每个接入平台按下表登记已获授权的接口：

| 业务能力 | 官方接口与版本 | 请求方式 | 授权 Scope | 分页方式 | 限流与配额 | 对应方法 |
| --- | --- | --- | --- | --- | --- | --- |
| 商品查询 | 接入时登记 | GET/POST | 接入时登记 | page/cursor/none | QPS、并发、日配额 | `search_products` |
| 评论查询 | 接入时登记 | GET/POST | 接入时登记 | page/cursor/none | QPS、并发、日配额 | `search_reviews` |
| 市场指标 | 接入时登记 | GET/POST | 接入时登记 | 时间范围或分页 | QPS、并发、日配额 | `get_market_metrics` |

每个接口还应记录：

- 生产和沙箱地址。
- 必填参数、允许的市场和时间范围。
- 单页上限、最大翻页数量和停止条件。
- 响应时间字段及其时区。
- 官方业务错误码和 `Retry-After` 规则。
- 接口废弃日期和替代版本。

## 3. 公共请求映射

| 公共参数 | 使用位置 |
| --- | --- |
| `platform`、`market` | 选择平台、站点和 Adapter |
| `category`、`keyword` | 商品检索条件 |
| `product_limit` | 控制商品分页和停止条件 |
| `product_ids`、`review_limit_per_product` | 控制评论查询范围 |
| `sort_by` | 映射官方排序；不支持时返回 `UNSUPPORTED_SORT` |
| `start_time`、`end_time` | 限定评论或市场指标时间范围 |

Access Token、App Secret、官方 URL 和分页游标不得进入公共请求。

## 4. 错误映射

| 官方情况 | 统一错误码 |
| --- | --- |
| 凭据缺失 | `API_CREDENTIALS_MISSING` |
| Token 失效且刷新失败 | `API_TOKEN_EXPIRED` |
| 租户、应用或 Scope 无权限 | `API_PERMISSION_DENIED` |
| 请求参数被拒绝 | `API_INVALID_REQUEST` |
| 平台限流 | `API_RATE_LIMIT` |
| 配额耗尽 | `API_QUOTA_EXHAUSTED` |
| 平台临时不可用 | `API_UPSTREAM_UNAVAILABLE` |
| 响应结构发生变化 | `API_SCHEMA_CHANGED` |
| 请求超时 | `TOOL_TIMEOUT` |

限流按官方等待时间处理；认证、权限、参数、配额和 Schema 错误不进行无意义重试。

## 5. 完成条件

接口清单中的每项能力都必须有明确的接口版本、授权 Scope、分页规则、限流规则和错误映射。未获授权的接口不能写入 Adapter 能力声明。
