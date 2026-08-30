# 输入输出数据契约

## 1. 设计目标

页面、独立任务和未来主图都使用同一套输入输出结构。调用方只需要知道公开 Schema，不需要知道 Graph 节点、Tool 返回细节和 Adapter 实现。

所有公开 Schema 都带 schema_version。第一版使用 1.0。

## 2. MarketIntelligenceContext

运行上下文由系统提供：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| task_id | string | 是 | 统一任务 ID |
| tenant_id | string | 是 | 租户，来自鉴权 |
| user_id | string | 是 | 发起人，来自鉴权 |
| trace_id | string | 是 | 全链路追踪 ID |
| user_query | string | 是 | 用户原始目标 |
| constraints | object | 是 | 结构化约束，没有约束时为空对象 |

业务代码不能修改 tenant_id、user_id 和 task_id。

## 3. MarketIntelligenceRequest

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| schema_version | string | 是 | 当前为 1.0 |
| market | string | 是 | 目标市场，例如 CN 或 US |
| category | string | 是 | 业务类目 |
| keyword | string | 是 | 当前一次任务只允许一个关键词 |
| platforms | string array | 是 | 一期数组长度固定为1，只允许 taobao |
| data_source_mode | enum | 是 | 当前为 fixed_dataset，后期官方接口使用 official_api |
| collection | CollectionOptions | 是 | 采集范围 |
| profit_constraints | ProfitCalculatorParameters 或 null | 否 | 缺少时由Graph生成unavailable利润结果 |

CollectionOptions：

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| product_limit | integer | 1 到服务端配置上限，当前上限不超过 50 |
| review_limit_per_product | integer 或 null | DatasetAdapter可使用；后期由OfficialApiAdapter的capabilities决定是否支持 |
| sort_by | enum | default、sales_desc、price_asc、price_desc |

保留数组结构是为了以后增加授权平台。多平台阶段由 Graph 按平台分别调用 ProductSearchTool，再按平台保留样本范围和证据；当前固定数据集阶段不执行跨平台合并。

ProfitCalculatorParameters继承`app.tools`公开导出的ProfitInput，并补充currency和minimum_margin。Graph只使用完整参数调用ProfitCalculatorTool。

## 4. MarketIntelligenceReport

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| schema_version | string | 当前为 1.0 |
| report_id | string | 报告唯一 ID |
| task_id | string | 所属任务 |
| status | enum | COMPLETED、DEGRADED 或 FAILED |
| scope | AnalysisScope | 市场、类目、关键词、平台、时间和样本范围 |
| market_snapshot | MarketSnapshot | 市场或样本指标 |
| competitor_matrix | CompetitorItem array | TOP 商品结构化对比 |
| review_insights | ReviewInsight | 评论聚合结果 |
| profit_analysis | ProfitAnalysis | 利润和毛利约束结果 |
| entry_assessment | EntryAssessment | GO、CONDITIONAL_GO、NO_GO或INSUFFICIENT_DATA |
| facts | Statement array | Tool 数据可以直接支持的事实 |
| inferences | Statement array | 基于事实得到的推断 |
| opportunity_signals | Statement array | 市场机会 |
| risk_signals | Statement array | 风险 |
| suggested_actions | Statement array | 后续需要验证或执行的动作 |
| data_limitations | DataLimitation array | 缺失、部分、过期或冲突数据 |
| evidence_refs | EvidenceReference array | 报告使用的证据 |
| generated_at | datetime | 报告生成时间 |

## 5. Statement

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| statement_id | string | 结论 ID |
| text | string | 给用户看的内容 |
| confidence | number | 0 到 1 |
| evidence_ids | string array | 支持该内容的证据 |
| affected_by_limitations | string array | 影响该结论的数据限制 ID |

事实必须至少有一个证据。推断、机会和风险也必须引用支持它们的事实或证据。

EntryAssessment的每个判断必须关联evidence_ids和影响判断的limitation_ids。证据不足、关键成本缺失或数据冲突时使用INSUFFICIENT_DATA。该结构不包含建议定价、商品定位、规格组合和卖点。

## 6. DataLimitation

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| limitation_id | string | 限制 ID |
| field | string | 受影响字段 |
| status | enum | unavailable、partial、stale、conflict |
| reason_code | string | 稳定原因码 |
| message | string | 给用户看的原因 |
| affected_conclusions | string array | 受影响结论 ID |
| evidence_ids | string array | 能说明限制的证据 |

例如，固定数据集只有商品样本时，market_size、market_gmv 和 market_growth 返回 unavailable。

## 7. Tool 通用返回结构

所有 Tool 使用需求规格书规定的字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| success | boolean | 调用是否成功 |
| data | object | 结构化数据 |
| error_code | string 或 null | 稳定错误码 |
| error_message | string 或 null | 可读错误 |
| source | string | 数据来源或计算器名称 |
| timestamp | datetime | Tool 返回时间 |
| trace_id | string | 链路 ID |
| degraded | boolean | 是否为部分结果 |

## 8. 版本兼容

- 新增可选字段时增加小版本，例如 1.0 到 1.1。
- 删除字段、修改类型或改变字段语义时增加大版本。
- 调用方遇到不支持的大版本时返回 SCHEMA_VERSION_UNSUPPORTED。
- 已保存报告保留原始版本，不在读取时静默改写。
