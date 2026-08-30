# 开发顺序

## 1. 总体顺序

    需求和数据契约
      -> 数据模型
      -> 固定数据集与 Adapter
      -> 四个 Tool
      -> Service 与 Graph
      -> Task API 与 SSE
      -> 市场机会页面
      -> 未来主图接入

数据能力放在页面和Graph之前。

## 2. 阶段一：冻结数据契约

交付：

- MarketIntelligenceContext
- MarketIntelligenceRequest
- MarketIntelligenceReport
- NormalizedProduct
- NormalizedReview
- MarketMetric
- CompetitorItem
- ProfitInput（复用`app.tools`公开导出的定义）
- ProfitAnalysis
- ReviewInsight
- EntryAssessment
- EvidenceReference
- DataLimitation
- AdapterCapabilities
- 错误码和 Schema 版本规则

退出条件：所有后续组件使用同一套字段，评审后不再随意改名和改变语义。

## 3. 阶段二：数据能力

交付：

- DatasetAdapter。
- 完整固定数据集。
- CommerceAdapter 公共请求类型。
- AdapterRegistry。
- collection_run、source_snapshot 和 product_snapshot。

退出条件：

- 固定数据集可以返回商品、评论、市场指标和成本。
- 缺失能力可以通过 capabilities 判断。
- Adapter 测试不依赖外网。

## 4. 阶段三：四个 Tool

依次完成：

1. ProductSearchTool。
2. MarketDataTool。
3. ReviewInsightTool。
4. ProfitCalculatorTool。

退出条件：每个 Tool 可以独立调用，返回统一结构，证据和错误码完整。

## 5. 阶段四：后台独立模块

交付：

- MarketIntelligenceService。
- MarketIntelligenceGraph。
- MarketIntelligenceState。
- 报告综合和证据校验。
- 结果持久化。
- intent 为 market_entry 的独立任务执行器。

退出条件：通过后端 API 可以用固定数据集完成 FR-020 至 FR-024 的市场情报链路。

## 6. 阶段五：任务 API 和 SSE

交付：

- 创建、查询、事件和取消。
- inline 和 worker 共用 Dispatcher。
- Checkpoint 和断线恢复。
- 状态、错误和降级事件。

退出条件：没有前端页面时也能用 API 完成和追踪任务。

## 7. 阶段六：市场机会页面

交付：

- 独立页面和路由。
- 真实参数表单。
- 任务进度。
- 报告展示。
- 证据查看。
- 刷新恢复和取消。

退出条件：页面不再使用固定指标和固定任务参数。

## 8. 阶段七：扩展正式数据源

取得官方接口文档、权限和测试凭据后实现 TaobaoOfficialApiAdapter、JdOfficialApiAdapter、PinduoduoOfficialApiAdapter 和其他平台 Adapter。每个平台继续使用统一 Schema。

## 9. 阶段八：主图接入

当前只保留公开 Service 和 Schema。以后主图调用同一个 MarketIntelligenceService，不复制Graph、Tool和Adapter。

## 10. 当前仓库对应位置

现有淘宝页面采集代码不再属于目标方案。代码实施时停止注册并移除相关页面采集依赖。下一步先补齐公共数据 Schema 和 DatasetAdapter；官方 API Adapter 等取得平台授权后再开发。
