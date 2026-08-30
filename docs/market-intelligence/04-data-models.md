# 统一数据模型

## 1. 这篇文档解决什么问题

Adapter负责把固定数据集或平台官方API的数据转成统一结构。Tool、Graph、页面和未来主图只使用这些统一结构，不读取平台专用字段。

数据分为两类：

- 事实与证据数据：商品、评论、市场指标和成本输入，由Tool返回。
- 分析与结论数据：竞品矩阵、评论洞察、利润结果和进入判断，由确定性分析或市场情报Agent生成。

Tool不直接生成完整市场进入报告。MarketIntelligenceGraph编排Tool，报告生成Agent根据结构化结果生成MarketIntelligenceReport。

## 2. AnalysisScope

AnalysisScope统一说明一项数据或一份报告覆盖什么范围。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| market | string | 目标市场，例如CN或US |
| platforms | string array | 数据对应的平台 |
| category | string | 商品类目 |
| keyword | string | 本次任务的单个关键词 |
| start_time | datetime或null | 数据时间范围起点 |
| end_time | datetime或null | 数据时间范围终点 |
| requested_product_count | integer | 请求商品数量 |
| actual_product_count | integer | 实际商品数量 |
| actual_review_count | integer | 实际评论数量 |
| data_source_mode | enum | fixed_dataset或official_api |

样本统计必须带AnalysisScope，不能省略平台、时间和实际样本数量。

## 3. NormalizedProduct

NormalizedProduct表示一个平台商品在某个时间点的标准化快照，主要用于竞品分析和样本统计。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| snapshot_id | string | 商品快照ID |
| collection_run_id | string | 本次数据读取批次 |
| platform | string | taobao、jd、pinduoduo、amazon等 |
| market | string | CN、US、UK等目标市场 |
| product_id | string | 平台商品ID |
| title | string | 商品标题 |
| brand | string或null | 品牌 |
| category | string或null | 商品类目 |
| price | decimal | 当前价格 |
| currency | string | ISO货币代码 |
| sales_display | string或null | 数据源原始销量文字 |
| sales_value | integer或null | 只有可靠解析时填写 |
| sales_value_type | enum | exact、lower_bound、range、unknown |
| shop_name | string或null | 店铺或卖家 |
| rating | decimal或null | 商品评分 |
| review_count | integer或null | 评论数量 |
| source_ref | string | 固定数据集记录或官方API记录引用 |
| source_url | string或null | 数据源允许提供时填写 |
| source_snapshot_ref | string | 固定数据集记录或官方API响应快照引用 |
| source_timestamp | datetime | 来源数据时间 |
| ingest_timestamp | datetime | 系统入库时间 |
| source_type | enum | fixed_dataset或official_api |
| data_status | enum | valid、demo_only、stale、partial |

金额字段使用Decimal语义。sales_value_type不允许由LLM推测；只有数据源能够说明语义时才填写exact、lower_bound或range。

## 4. NormalizedReview

NormalizedReview表示一条标准化评论证据。评论与商品分开保存，一个商品可以关联多条评论。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| review_id | string | 平台评论ID或稳定派生ID |
| collection_run_id | string | 本次数据读取批次 |
| platform | string | 来源平台 |
| market | string | 目标市场 |
| product_id | string | 所属商品 |
| content | string | 脱敏后的评论内容 |
| rating | decimal或null | 评论星级 |
| review_time | datetime或null | 评论时间 |
| verified_purchase | boolean或null | 数据源提供时填写 |
| helpful_count | integer或null | 有用数 |
| sentiment | enum或null | positive、neutral、negative |
| themes | string array | 主题标签 |
| source_ref | string | 评论来源引用 |
| source_timestamp | datetime | 来源数据时间 |
| ingest_timestamp | datetime | 系统入库时间 |
| data_status | enum | valid、demo_only、stale、partial |

评论展示前必须去除姓名、电话、地址和账号等个人信息。sentiment和themes是增强字段；尚未分析时允许为空。

## 5. MarketMetric

MarketMetric表示一项市场指标，对应FR-020。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| metric_code | string | market_size、gmv、growth、price_distribution、brand_concentration、product_concentration或sample前缀指标 |
| value | number、object、array或null | 指标值 |
| unit | string或null | CNY、USD、percent、count、ratio等 |
| status | enum | available、unavailable、partial、stale、conflict |
| reason_code | string或null | unavailable、partial、stale或conflict的稳定原因码 |
| scope | AnalysisScope | 统计范围 |
| methodology | string | 数据来源和统计口径 |
| evidence_ids | string array | 支撑指标的证据 |
| source_timestamp | datetime或null | 来源数据时间 |

商品样本只能生成sample_price_distribution、sample_sales_distribution、sample_concentration和sample_rating_distribution等样本指标。

样本统计不能写成全市场指标。缺少市场规模、GMV或增长数据时使用status=unavailable，LLM不能根据商品样本补算。

## 6. CompetitorItem

CompetitorItem表示竞品矩阵中的一行，对应FR-021。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| rank | integer | 当前比较范围内的排序 |
| platform | string | 商品平台 |
| market | string | 目标市场 |
| product_id | string | 平台商品ID |
| title | string | 商品标题 |
| brand | string或null | 品牌 |
| price | decimal | 当前价格 |
| currency | string | 货币 |
| sales_display | string或null | 原始销量文字 |
| sales_value | integer或null | 可可靠解析的销量 |
| sales_value_type | enum | exact、lower_bound、range、unknown |
| rating | decimal或null | 商品评分 |
| review_count | integer或null | 评论数量 |
| shop_name | string或null | 店铺或卖家 |
| source_ref | string | 商品来源 |
| evidence_ids | string array | 商品证据 |

竞品排序只代表当前查询和样本范围。每一项必须关联platform、product_id、source_ref和evidence_ids。

## 7. ProfitInput

ProfitInput是`app/tools/support/contracts.py`定义并由`app.tools`公开导出的基础利润输入契约，对应FR-023。

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| price | float | 大于0 |
| product_cost | float | 大于等于0 |
| platform_fee | float | 平台佣金或费用金额，大于等于0 |
| logistics_cost | float | 物流成本，大于等于0 |
| advertising_cost | float | 广告分摊成本，大于等于0 |

如果只有平台佣金比例，需要先按确定性公式转换为platform_fee，并保留原比例、计算过程和证据。LLM不能生成缺失成本。

ProfitCalculatorParameters继承ProfitInput，并补充currency和minimum_margin。输出中的selling_price由price映射。Graph负责检查参数完整性，只在完整时调用ProfitCalculatorTool。

## 8. ProfitAnalysis

ProfitAnalysis由ProfitCalculatorTool确定性计算。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| status | enum | available或unavailable |
| selling_price | decimal或null | 售价 |
| total_cost | decimal或null | 总成本 |
| profit | decimal或null | 单件利润 |
| margin | decimal或null | 毛利率 |
| minimum_margin | decimal或null | 目标毛利率 |
| meets_minimum_margin | boolean或null | 是否满足约束 |
| breakdown | object | 各成本项目 |
| currency | string或null | 货币 |
| calculation_version | string | 计算公式版本 |
| evidence_ids | string array | 输入和计算证据 |

第一版公式：

    total_cost =
        product_cost
        + platform_fee
        + logistics_cost
        + advertising_cost

    profit = price - total_cost
    margin = profit / price
    meets_minimum_margin = margin >= minimum_margin

缺少完整ProfitCalculatorParameters时，Graph不调用ProfitCalculatorTool，直接生成status=unavailable的ProfitAnalysis。

## 9. ReviewInsight

ReviewInsight表示评论聚合结果，对应FR-022。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| status | enum | available、unavailable、partial、stale、conflict |
| sample_scope | AnalysisScope | 评论样本范围 |
| sentiment_distribution | object | 正向、中性和负向数量与比例 |
| themes | ReviewTheme array | 评论主题 |
| pain_points | ReviewTheme array | 用户痛点 |
| unmet_needs | ReviewTheme array | 未满足需求 |
| representative_review_ids | string array | 代表性评论ID |
| evidence_ids | string array | 评论和聚合证据 |

其中
**ReviewTheme**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| theme | string | 主题的稳定标识，例如 `cleaning`、`battery_life`、`heating_speed`、`leakage` |
| mention_count | integer | 当前评论样本中提及该主题的评论数量，大于等于 0 |
| mention_ratio | decimal | 提及该主题的评论数占当前分析评论样本的比例，范围为 0 到 1 |
| summary | string | 对该主题下消费者主要观点的简要归纳，不得引入评论证据未支持的事实 |
| representative_review_ids | string array | 能代表该主题主要观点的评论 ID，用于展示和人工核 |
| evidence_ids | string array | 支撑该主题识别、统计和总结的证据 ID，用于完整证据追溯 |

每个主题、痛点和需求都必须保留样本评论引用。

## 10. EntryAssessment

EntryAssessment是FR-024要求的机器可读进入判断。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| decision | enum | GO、CONDITIONAL_GO、NO_GO、INSUFFICIENT_DATA |
| summary | string | 判断说明 |
| evidence_ids | string array | 支撑判断的证据 |
| limitation_ids | string array | 影响判断的数据限制 |

证据不足、关键成本缺失或数据冲突时使用INSUFFICIENT_DATA。该结构不包含建议定价、商品定位、规格组合和卖点。

## 11. 正式Tool与数据模型的对应关系

Tool名称以需求规格书第7.1节为准：

| Tool | 主要输入 | data字段的主要输出 |
| --- | --- | --- |
| ProductSearchTool | platform、market、category、keyword、filter、product_limit、sort_by | NormalizedProduct array |
| MarketDataTool | category、market、date_range、商品样本 | MarketMetric array |
| ReviewInsightTool | product_ids、filter、review_limit_per_product | NormalizedReview array和ReviewInsight |
| ProfitCalculatorTool | ProfitCalculatorParameters，继承ProfitInput | ProfitAnalysis |

评论读取、标签处理和聚合可以拆成内部组件，对Graph公开的名称保持ReviewInsightTool。

## 12. Tool统一返回结构

上表只描述ToolResponse.data中的内容。每个Tool的完整返回结构必须包含：

| 字段 | 类型 | 说明 |
| --------- | ---------------- | ---------------------------------------------- |
| success | boolean | Tool 调用是否成功 |
| data | object 或 null | 结构化业务数据；失败时可包含已产生的部分上下文，例如 `collection_run_id` |
| error | ToolError 或 null | 错误信息；成功时为 null |
| source | string | 数据源、平台或计算器标识 |
| timestamp | datetime | Tool 返回时间 |
| trace_id | string | 链路追踪 ID |
| degraded | boolean | 是否为降级或部分结果 |

其中
**ToolError**

| 字段 | 类型 | 说明 |
| --------- | ------- | -------------------------------------------------------------------- |
| code | string | 稳定错误码，例如 `SOURCE_LOGIN_REQUIRED`、`SOURCE_TIMEOUT`、`INVALID_ARGUMENT` |
| message | string | 面向开发者或上层调用方的可读错误说明 |
| retryable | boolean | 当前错误是否适合自动重试 |

Tool Schema必须版本化。外部调用必须设置timeout、retry、backoff、circuit breaker和rate limit。

## 13. MarketIntelligenceReport中的位置

本篇不再定义另一套报告类型。对外输出统一使用03-data-contracts.md中的MarketIntelligenceReport：

| 报告字段 | 使用的数据模型 |
| --- | --- |
| scope | AnalysisScope |
| market_snapshot | MarketMetric array或聚合后的MarketSnapshot |
| competitor_matrix | CompetitorItem array |
| review_insights | ReviewInsight |
| profit_analysis | ProfitAnalysis |
| entry_assessment | EntryAssessment |
| facts、inferences、opportunity_signals、risk_signals、suggested_actions | Statement array |
| data_limitations | DataLimitation array |
| evidence_refs | EvidenceReference array |

页面可以把报告显示为“市场机会报告”，API、Service和未来主图仍使用MarketIntelligenceReport。

## 14. 缺失值和证据规则

- 数据源没有提供的普通字段使用null。
- 无法获得的指标使用status=unavailable。
- 部分样本使用status=partial。
- 过期数据使用status=stale。
- 多来源冲突使用status=conflict，并保留各来源值。
- 合成固定测试数据使用data_status=demo_only。
- LLM不能根据标题、常识或相似商品补齐销量、市场规模、成本、评分和其他数字。
- 所有关键指标、评论洞察、利润结果和进入判断必须关联evidence_ids。
- 关键证据缺失时返回unavailable或DEGRADED，并写入DataLimitation。
- 原始证据和分析结论分开保存。
