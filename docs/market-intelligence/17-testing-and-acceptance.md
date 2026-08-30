# 测试与验收

## 1. 测试原则

数据、计算、Graph、API和页面分层测试。当前 CI 只使用固定数据集。后期 OfficialApiAdapter 使用 Mock Server 或 Mock Client，不访问真实平台生产接口。

## 2. Adapter 测试

DatasetAdapter：

- 正确读取完整数据集。
- manifest 和 SHA-256 校验。
- 数据集版本和租户权限。
- 商品和评论数量截取。
- 缺文件、空数据和过期数据。

OfficialApiAdapter 合同测试，后期接入时执行：

- 官方字段到统一字段的映射。
- 商品和评论分页。
- 动态 product_limit 和 review_limit_per_product。
- 销量原文、精确值和下界语义。
- Token刷新、权限不足和凭据缺失。
- 429、配额耗尽、5xx和超时。
- 部分结果和零结果。
- 响应快照遵守官方保存规则。
- 凭据不进入日志、Trace和ToolResponse。

## 3. Tool 测试

- ProductSearchTool：Adapter选择、商品Schema、证据和部分结果。
- MarketDataTool：完整指标、样本指标、unavailable和统计口径。
- ReviewInsightTool：主题、情感、引用、脱敏和空评论。
- ProfitCalculatorTool：ProfitInput公式、margin舍入、最低毛利和非法输入。

## 4. Graph 测试

- 正常全链路。
- 无评论降级。
- 无市场聚合指标降级。
- 无成本时不调用ProfitCalculatorTool并生成unavailable结果。
- 商品数据全空失败。
- 节点临时错误重试。
- 不可重试错误立即停止。
- 取消任务。
- Checkpoint恢复。
- 证据不足时删除强结论。
- 关键数据齐全时生成带证据的EntryAssessment。
- 关键成本缺失或数据冲突时EntryAssessment为INSUFFICIENT_DATA。

## 5. API 测试

- 鉴权字段覆盖请求字段。
- market_entry 路由到 MarketIntelligenceService。
- inline 和 worker 使用同一 Dispatcher。
- 创建、查询、事件和取消。
- SSE 断线恢复。
- 跨租户读取被拒绝。
- 报告 Schema 版本。

## 6. 页面测试

- 表单校验。
- 防止重复提交。
- 任务进度。
- 完整、降级、失败和取消状态。
- 刷新恢复。
- unavailable 的展示。
- 证据抽屉。
- 不显示 storage_path 和敏感内容。

## 7. 需求验收

| 需求 | 验收 |
| --- | --- |
| FR-003 | SSE 展示节点和 Tool，断线可恢复 |
| FR-004 | 事实、推断和建议分区，关键数字带证据 |
| FR-020 | 市场指标或明确 unavailable |
| FR-021 | TOP竞品关联 platform、product_id 和 source |
| FR-022 | 评论主题和情感保留样本引用 |
| FR-023 | 利润由 Calculator Tool 计算 |
| FR-024 | EntryAssessment、机会和风险关联证据 |
| FR-010 至 FR-013 | 状态、Trace、恢复和取消可用 |

## 8. 质量指标

使用固定版本评测集计算：

| 指标 | 目标 |
| --- | --- |
| Tool Selection Accuracy | 不低于 95% |
| Tool Success Rate | 不低于 98% |
| Structured Output Pass Rate | 不低于 98% |
| Evidence Coverage | 不低于 95% |
| Critical Fact Hallucination | 不高于 2% |
| Task Completion Rate | 不低于 90% |
| Recovery Success Rate | 不低于 85% |

市场进入评估评测集使用需求规格书建议的30条用例，覆盖不同市场、类目、约束和数据缺失。

## 9. 分阶段退出条件

- 数据阶段：统一 Schema 冻结，固定数据集和 Adapter 测试通过。
- Tool阶段：四个 Tool 可以独立调用，错误和证据结构稳定。
- 后台阶段：API下完整任务可以运行、恢复、取消和追溯。
- 页面阶段：市场机会页面不依赖固定展示内容。
- 主图接入阶段：另行验收，本次不实现。
