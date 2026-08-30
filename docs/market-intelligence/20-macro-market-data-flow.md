# 市场宏观数据流程

## 数据边界

市场宏观数据按 `tenant + platform + market + category + keyword + period` 管理。

| 类型 | 内容 | 责任方 |
| --- | --- | --- |
| 直接指标 | 市场规模、GMV、销量、订单量等数据源直接提供的数值 | 运营人员上传 |
| 来源信息 | 统计周期、数据来源、统计口径、授权说明、数据版本和原始文件 | 运营人员上传 |
| 派生指标 | 同比、环比、CAGR、平均成交价、GMV 占比等 | 系统计算 |
| 管理信息 | 文件摘要、计算时间、公式版本、数据冲突和过期状态 | 系统生成 |

直接指标保存为 `value_kind=direct`。派生指标保存为 `value_kind=derived`，并记录 `formula_code`、`formula_version` 和 `source_observation_ids`。缺少必要的前期数据时，派生指标保持不可用。

## 数据流程

```text
运营人员上传基础指标与来源信息
    ↓
MarketMetricUploadService 校验范围、周期、单位和来源
    ↓
market_metric_batch + market_metric_observation 保存 direct 指标
    ↓
MacroMarketMetricCalculator 计算并保存 derived 指标
    ↓
审核通过，batch.status = approved
    ↓
MarketDataTool 查询已审核宏观指标
    ↓
转换为 MarketMetric，进入 MarketIntelligenceGraph 和最终报告
```

计算在上传或基础数据变更时执行并固化。Agent 运行时读取已审核结果，保证报告可重复和可追溯。

## 实现思路

`MarketMetricUploadService` 负责批次创建、字段校验、文件摘要和重复版本检查；`MacroMarketMetricCalculator` 负责确定性公式及计算血缘；`MarketMetricRepository` 负责按租户、平台、市场、类目、关键词和周期保存、审核及查询；`MarketDataTool` 只负责选择数据来源并输出统一契约。

宏观指标读取优先级为：已审核数据库指标、固定数据集 `market_metrics.json`、商品样本统计、`unavailable`。数据库作为正式宏观指标来源，JSON 保留为演示和离线降级来源。

数据库使用 `market_metric_batch` 保存上传范围、来源和审核状态，使用 `market_metric_observation` 保存直接指标与派生指标。派生指标引用基础观测 ID，不重复保存前后期原始数值。
