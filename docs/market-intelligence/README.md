# 市场情报 Agent 开发文档

## 1. 这组文档解决什么问题

这组文档只描述市场情报 Agent 和“市场机会”独立业务模块。当前目标是先完成一个可以单独运行的市场机会页面和后台链路；以后主图通过同一个 Service 接口调用市场情报能力。

需求基线是《电商智能运营 Agent 平台项目需求规格说明书 V1.0》。当前开发只使用固定数据集。各电商平台的真实数据在取得官方 API 文档、授权范围和测试凭据后，通过独立的官方 API Adapter 接入。

## 2. 模块边界

本模块负责：

- 获取市场、商品、竞品和评论数据。
- 计算样本统计和利润。
- 生成市场事实、推断、机会、风险和数据限制。
- 保存证据引用，使结果能够追溯到 Tool 和数据来源。
- 通过统一任务 API 为市场机会页面提供服务。
- 暴露稳定的 MarketIntelligenceService 接口，供未来主图调用。

本模块不负责商品定位、最终定价策略、Listing 文案、运营诊断、商品保存、上架和其他 Agent 的内部流程。

## 3. 文档阅读顺序

| 顺序 | 文档 | 说明 |
| --- | --- | --- |
| 1 | [需求与范围](01-requirements-and-scope.md) | 需求编号、范围和非目标 |
| 2 | [模块架构](02-architecture.md) | 当前独立调用链和模块依赖 |
| 3 | [输入输出契约](03-data-contracts.md) | 输入、输出和跨模块交换结构 |
| 4 | [统一数据模型](04-data-models.md) | 商品、评论、市场指标和利润数据结构 |
| 5 | [Adapter接口](05-adapter-contract.md) | 所有数据源必须遵守的统一接口 |
| 6 | [DatasetAdapter](06-dataset-adapter.md) | 固定数据集的文件格式和读取规则 |
| 7 | [官方API Adapter](07-official-api-adapters.md) | 后期接入各平台官方 API 的统一规范 |
| 8 | [ProductSearchTool](08-product-search-tool.md) | 商品查询 Tool |
| 9 | [MarketDataTool](09-market-data-tool.md) | 市场指标 Tool |
| 10 | [ReviewInsightTool](10-review-insight-tool.md) | 评论洞察 Tool |
| 11 | [ProfitCalculatorTool](11-profit-calculator-tool.md) | 利润计算 Tool |
| 12 | [证据与追溯](12-evidence-and-traceability.md) | 证据、快照和追溯链 |
| 13 | [错误与降级](13-error-and-degradation.md) | 错误码、重试和降级 |
| 14 | [Service与Graph](14-service-and-graph.md) | Service 和 Graph 执行流程 |
| 15 | [API、任务与SSE](15-api-task-and-sse.md) | 页面使用的任务 API 和事件 |
| 16 | [市场机会页面](16-market-opportunity-ui.md) | 市场机会页面 |
| 17 | [测试与验收](17-testing-and-acceptance.md) | 测试范围和验收标准 |
| 18 | [未来主图接入](18-future-root-graph-integration.md) | 未来主图接入契约 |
| 19 | [开发顺序](19-development-order.md) | 实际开发顺序和阶段交付物 |

后续接入平台官方 API 时，先完成以下三份接入基线：

- [授权与能力确认](integrations/01-authorization-and-capabilities.md)
- [官方接口清单](integrations/02-official-api-inventory.md)
- [字段映射与数据口径](integrations/03-field-mapping-and-data-semantics.md)

## 4. 需求、设计和实现状态怎么区分

每篇文档使用三种说明：

- 需求依据：需求规格书明确要求的能力。
- 模块方案：为了落实需求，本模块已经确定的技术方案。
- 当前状态：仓库中已经存在的代码，或者仍需开发的内容。

## 5. 当前代码状态

当前需要实现 DatasetAdapter、四个 Tool 的统一契约、MarketIntelligenceService、MarketIntelligenceGraph、任务分派和市场机会独立页面。官方 API Adapter 留到取得平台授权后开发。
