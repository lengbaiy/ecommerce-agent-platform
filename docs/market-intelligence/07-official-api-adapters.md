# 官方 API Adapter 接入规范

## 1. 作用

后期需要真实平台数据时，每个电商平台通过自己的官方 API Adapter 接入。上层 Tool 和 Graph 只使用统一 Adapter 接口，不处理平台的认证、分页、限流和字段差异。

当前阶段不实现任何 OfficialApiAdapter，只保留公共接口和接入规则。市场机会模块使用 DatasetAdapter 完成开发、测试和演示。

## 2. Adapter 命名

每个平台使用独立实现：

| 平台 | Adapter |
| --- | --- |
| 淘宝 | TaobaoOfficialApiAdapter |
| 京东 | JdOfficialApiAdapter |
| 拼多多 | PinduoduoOfficialApiAdapter |
| 其他平台 | 按 PlatformNameOfficialApiAdapter 命名 |

各平台共享 CommerceAdapter 协议，不共享平台认证代码和接口字段映射。

## 3. 开发前必须拿到的信息

开始实现某个平台 Adapter 前，必须确认：

- 官方开发者文档地址和版本。
- 应用申请方式。
- App Key、Client ID 或其他应用身份。
- Access Token 等凭据的获取与刷新方式。
- 已批准的接口权限和数据使用范围。
- 商品搜索、商品详情、评论和市场指标对应的官方接口。
- 分页方式、最大页数和单页数量。
- QPS、日配额、并发限制和 Retry-After 规则。
- 返回字段、错误码和时间口径。
- 数据保存时长、脱敏和审计要求。
- 是否允许把接口响应保存为证据快照。

这些信息没有确认时，Adapter 保持未注册状态。

## 4. 统一能力

每个平台 Adapter 按实际官方接口声明能力：

    capabilities() -> AdapterCapabilities
    search_products(request, context) -> AdapterResult[list[NormalizedProduct]]
    fetch_reviews(request, context) -> AdapterResult[list[NormalizedReview]]
    fetch_market_metrics(request, context) -> AdapterResult[list[MarketMetric]]

官方 API 没有提供的能力在 capabilities 中标记 false。Graph 读取能力后把对应报告字段标记为 unavailable。

## 5. 输入

上层只传业务参数：

| 字段 | 说明 |
| --- | --- |
| platform | 目标平台 |
| market | 目标市场 |
| category | 商品类目 |
| keyword | 单个搜索关键词 |
| product_limit | 商品数量上限 |
| review_limit_per_product | 每件商品评论数量上限 |
| sort_by | 统一排序枚举 |
| time_range | 市场指标或评论时间范围 |

调用方不能传 Access Token、App Secret 和官方接口 URL。

## 6. 认证与凭据

- 凭据由密钥管理系统或环境配置提供。
- 凭据按租户和平台隔离。
- 代码、日志、Trace、ToolResponse 和固定数据集不能包含明文凭据。
- Token 刷新由平台 Adapter 内部处理。
- Token 失效且无法刷新时返回 API_TOKEN_EXPIRED。
- 租户没有接口权限时返回 API_PERMISSION_DENIED。

## 7. 执行过程

    校验租户和平台授权
      -> 获取有效访问凭据
      -> 按官方文档构造请求
      -> 执行分页和限流控制
      -> 校验官方响应
      -> 保存允许保留的响应证据
      -> 映射成统一数据模型
      -> 返回数据、范围、版本和证据

## 8. 分页与数量

- Adapter 根据 product_limit 和 review_limit_per_product 控制最大读取量。
- 达到请求数量后停止继续翻页。
- 官方 API 返回的数据不足时返回 PARTIAL。
- next_token、page_no、cursor 等平台字段只留在 Adapter 内部。
- 上层只看到 requested_count 和 actual_count。

## 9. 限流与重试

- 每个平台单独配置超时、QPS、并发数和日配额。
- HTTP 429 或平台限流错误读取官方 Retry-After 或错误字段。
- 允许重试的请求使用指数退避，并受 Graph 最大重试次数限制。
- 认证失败、权限不足、参数错误和配额耗尽不进行无意义重试。
- 每次重试记录 attempt_id、错误码和等待时间。

## 10. 字段映射

平台响应先经过平台专用 Mapper，再生成统一模型：

    官方商品字段 -> NormalizedProduct
    官方评论字段 -> NormalizedReview
    官方市场指标 -> MarketMetric

Mapper 必须明确：

- 原字段名。
- 统一字段名。
- 类型转换。
- 金额单位和币种。
- 时间和时区。
- 销量是精确值、下界、区间还是未知。
- 缺失值和枚举映射。
- Mapper 版本。

Mapper 不能猜测官方响应中没有的字段。

## 11. 证据

每次官方 API 调用至少记录：

- task_id、trace_id 和 tool_call_id。
- 平台、接口名称和接口版本。
- 查询范围和分页范围。
- 响应时间、数据时间和入库时间。
- HTTP状态或平台业务状态。
- Adapter版本和Mapper版本。
- 返回记录数。
- 官方允许保存时的脱敏响应快照引用和SHA-256。

如果官方规则禁止保存完整响应，只保存允许保留的元数据、记录主键、字段摘要和哈希。

## 12. 错误映射

| 情况 | 统一错误码 |
| --- | --- |
| 凭据不存在 | API_CREDENTIALS_MISSING |
| Token失效 | API_TOKEN_EXPIRED |
| 租户或应用无权限 | API_PERMISSION_DENIED |
| 请求参数不被平台接受 | API_INVALID_REQUEST |
| 平台限流 | API_RATE_LIMIT |
| 当日配额耗尽 | API_QUOTA_EXHAUSTED |
| 平台5xx或临时不可用 | API_UPSTREAM_UNAVAILABLE |
| 响应字段不符合已知版本 | API_SCHEMA_CHANGED |
| 请求超时 | TOOL_TIMEOUT |

错误码随 Adapter Schema 版本化。

## 13. 注册规则

- dev、test、demo 默认不注册 OfficialApiAdapter。
- prod 也只有在授权、凭据、接口配置和安全检查全部完成时注册。
- 每个租户只能使用自己获批的平台能力。
- AdapterCapabilities 必须来自实际获批接口，不能把未授权能力标为可用。

## 14. 测试

在没有官方测试环境时，使用基于官方接口文档构造的 Mock 响应，不调用真实平台。

测试至少覆盖：

- 认证成功和失败。
- Token刷新。
- 商品、评论和市场指标映射。
- 分页结束和数量上限。
- 429、配额耗尽、5xx和超时。
- 缺字段和接口版本变化。
- 凭据不进入日志和响应。
- EvidenceReference可以追溯到接口调用。

## 15. 验收

某个平台 Adapter 只有满足以下条件才算接入完成：

- 使用官方接口。
- 权限范围与租户一致。
- 三类能力按实际情况声明。
- 统一 Schema 校验通过。
- 错误码、限流和重试符合官方规则。
- 数据可以追溯到官方接口和调用时间。
- 自动化测试不依赖生产平台。

