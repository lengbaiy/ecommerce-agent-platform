# Adapter 统一接口

## 1. Adapter 的作用

Adapter 隔离不同数据源。淘宝页面、固定数据集和以后接入的授权 API，都要转换成统一商品、评论和市场指标。

## 2. 选择规则

AdapterRegistry 使用 platform 和 data_source_mode 选择实现：

| platform | data_source_mode | Adapter |
| --- | --- | --- |
| taobao | fixed_dataset | DatasetAdapter，读取淘宝固定数据 |
| jd | fixed_dataset | DatasetAdapter，读取京东固定数据 |
| pdd | fixed_dataset | DatasetAdapter，读取拼多多固定数据 |
| amazon | fixed_dataset | DatasetAdapter，读取亚马逊固定数据 |
| taobao | official_api | TaobaoOfficialApiAdapter，取得授权后实现 |
| jd | official_api | JdOfficialApiAdapter，取得授权后实现 |
| pdd | official_api | PinduoduoOfficialApiAdapter，取得授权后实现 |

fixed_dataset 仍然保留真实业务平台。DatasetAdapter 不能把 platform 改成 dataset。

## 3. 接口

统一接口包含：

    capabilities() -> AdapterCapabilities
    search_products(request, context) -> AdapterResult[list[NormalizedProduct]]
    search_reviews(request, context) -> AdapterResult[list[NormalizedReview]]
    get_market_metrics(request, context) -> AdapterResult[list[MarketMetric]]

AdapterCapabilities 明确当前实现支持哪些方法：

| 字段 | 说明 |
| --- | --- |
| platform | 业务平台 |
| data_source_mode | 数据源模式 |
| supports_products | 是否支持商品 |
| supports_reviews | 是否支持评论 |
| supports_market_metrics | 是否支持市场指标 |
| max_products | 单次商品上限 |
| max_reviews_per_product | 单商品评论上限 |
| adapter_version | Adapter 版本 |
| schema_version | 输出 Schema 版本 |

Graph 先读取 capabilities，再决定调用或返回 unavailable。

## 4. 公共请求类型

Adapter 基类只能依赖 market_intelligence 公共 Schema，不能导入 taobao 目录下的请求类型。平台特有参数由对应 Adapter 自己解析，不能泄漏到 Tool 的公共接口。

## 5. AdapterResult

返回结果包含：

| 字段 | 说明 |
| --- | --- |
| data | 标准化数据 |
| run | 本次读取或采集批次 |
| evidence_refs | 数据证据 |
| warnings | 不影响主结果的警告 |
| degraded | 是否为部分结果 |

## 6. 注册规则

- dev、test、demo 注册固定数据集。
- prod 只注册已经取得官方授权的数据源。
- 没有官方 API 文档、接口权限和凭据时，不注册对应 OfficialApiAdapter。
- 缺少必需配置时不注册 Adapter。
- 相同 platform 和 data_source_mode 不允许重复注册。

## 7. 错误规则

Adapter 使用稳定错误码抛出业务错误。Tool 把错误转换成统一 ToolResponse。官方 API 的认证失败、权限不足和参数错误不重试；超时、5xx和限流按照官方接口规则处理。

## 8. 当前实现差距

当前 CommerceAdapter 只有 search_products，并且基类导入了淘宝专用 ProductCollectionRequest。现有淘宝页面采集实现不再进入目标架构。实现完整市场机会模块前，需要把请求类型移到公共 Schema，完成 DatasetAdapter，并补 capabilities、fetch_reviews 和 fetch_market_metrics。
