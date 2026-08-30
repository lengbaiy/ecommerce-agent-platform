# Tool 目录约定

`app/tools` 根目录除 `__init__.py` 外，只保存公开 Tool 入口模块；辅助协议、计算器和分析器统一放在
`app/tools/support` 子包。调用方优先从 `app.tools` 导入公共契约，Tool 内部直接引用 `app.tools.support`。

## 一期 Tool

| Tool | 入口文件 | 状态 |
| --- | --- | --- |
| MarketData | `market_data.py` | 已实现 |
| ProductSearch | `product_search.py` | 已实现 |
| ReviewInsight | `review_insight.py` | 已实现 |
| SalesMetrics | `sales_metrics.py` | 待实现 |
| Inventory | `inventory.py` | 待实现 |
| ProfitCalculator | `profit_calculator.py` | 已实现 |
| KnowledgeSearch | `knowledge_search.py` | 待实现 |
| PolicyCheck | `policy_check.py` | 待实现 |
| ProductPlanSave | `product_plan_save.py` | 待实现 |

统一返回 `success/data/error/source/timestamp/trace_id`，错误使用稳定错误码；读操作可按策略
重试，写操作必须同时具备审批和幂等键。

## support 子包

| 文件 | 职责 |
| --- | --- |
| `contracts.py` | Tool 通用请求、响应、错误和基础确定性计算契约 |
| `market_sample_metrics.py` | MarketDataTool 的商品样本回退统计 |
| `review_analyzer.py` | ReviewInsightTool 的预计算标签聚合器和分析协议 |
| `llm_review_analyzer.py` | ReviewInsightTool 的 LLM 语义分析器 |
