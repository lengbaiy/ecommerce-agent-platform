# MarketIntelligenceService 与 Graph

## 1. Service 公开入口

市场机会页面和未来主图共用：

    MarketIntelligenceService.execute(
        request: MarketIntelligenceRequest,
        context: MarketIntelligenceContext,
    ) -> MarketIntelligenceReport

Service 不接收 Vue 页面对象、HTTP Request、根 Graph 或其他 Agent 实例。

## 2. Service 负责什么

- 校验公开输入 Schema 和版本。
- 创建或读取市场情报运行记录。
- 准备 Graph 初始状态。
- 执行 Graph。
- 持久化最终报告。
- 返回统一结果。
- 在取消和重试时读取任务状态。

任务主表的创建和通用状态仍由 TaskService 负责。

## 3. MarketIntelligenceState

| 字段 | 说明 |
| --- | --- |
| context | task_id、tenant_id、user_id、trace_id |
| request | 市场情报请求 |
| current_step | 当前节点 |
| product_result | ProductSearchTool 结果 |
| competitor_matrix | CompetitorItem数组 |
| market_result | MarketDataTool 结果 |
| review_result | ReviewInsightTool 结果 |
| profit_result | ProfitCalculatorTool 结果 |
| facts | 已确认事实 |
| inferences | 推断 |
| opportunity_signals | 机会 |
| risk_signals | 风险 |
| evidence_refs | 所有证据 |
| data_limitations | 数据限制 |
| retry_count | 节点重试次数 |
| degraded_flags | 降级原因 |
| error | 当前错误 |
| final_report | 最终报告 |
| state_version | 状态版本 |

## 4. Graph 节点

    validate_input
      -> search_products
      -> build_competitor_matrix
      -> build_market_snapshot
      -> analyze_reviews
      -> calculate_profit
      -> synthesize_report
      -> validate_evidence
      -> persist_result

## 5. 节点说明

### validate_input

校验 Schema 版本、市场、类目、关键词、平台、数量和利润参数。检查数据源是否注册。失败时不调用任何外部数据源。

### search_products

调用 ProductSearchTool，保存商品、采集批次和证据。零商品进入 FAILED；部分商品进入 DEGRADED。

### build_competitor_matrix

把NormalizedProduct转换成CompetitorItem并按请求规则排序。每个竞品必须保留platform、product_id、source_ref和evidence_ids。排序只代表当前样本范围。

### build_market_snapshot

调用 MarketDataTool。聚合市场指标缺失时保留样本统计，并写入 data_limitations。

### analyze_reviews

调用 ReviewInsightTool。没有评论时生成 unavailable 结果，主流程继续。

### calculate_profit

按`app.tools`公开导出的ProfitInput字段检查成本，并校验currency和minimum_margin。参数完整时调用ProfitCalculatorTool；成本缺失时不调用Tool，生成unavailable结果，主流程继续。

### synthesize_report

Agent只读取结构化Tool结果。输出entry_assessment、facts、inferences、opportunity_signals、risk_signals和suggested_actions。每项内容带evidence_ids；证据不足时entry_assessment使用INSUFFICIENT_DATA。

### validate_evidence

执行 Schema、证据覆盖、数据等级、限制关联和逻辑检查。缺少关键证据时删除强结论或把任务降级。

### persist_result

保存最终报告、状态、版本和结果哈希。持久化成功后发送完成事件。

## 6. Agent 提示词边界

提示词必须要求：

- 只使用 state 中已有字段。
- 区分事实、推断和建议。
- 缺失数字写 unavailable。
- 搜索样本只描述样本。
- 每个结论填写 evidence_ids。
- 不输出商品策略和 Listing。

Prompt 和输出 Schema 都要版本化。

## 7. Checkpoint

每个节点成功后保存 state_version。重试从最近成功节点继续。Tool 调用和节点尝试分别保存 attempt_id，避免把旧错误覆盖掉。

## 8. 当前状态

MarketIntelligenceService 和 MarketIntelligenceGraph 尚未实现。现有 EcommerceOperationsGraph 中的市场情报占位节点不能作为本模块实现复用。
