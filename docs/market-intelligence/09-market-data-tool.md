# MarketDataTool

## 1. 作用

MarketDataTool获取市场指标，或者对已有商品样本做明确标注的样本统计。它必须区分“完整市场指标”和“当前样本统计”。

## 2. 需求对应

对应 FR-020：

- 类目规模
- 销量或 GMV
- 增长
- 价格分布
- 品牌或商品集中度

缺失项必须返回 unavailable。

## 3. 输入

| 字段 | 说明 |
| --- | --- |
| platform、market、category、keyword | 查询范围 |
| data_source_mode | 数据源模式 |
| date_range | 指标时间范围 |
| products | ProductSearchTool 商品样本 |
| evidence_refs | 商品或市场数据证据 |

## 4. 指标来源

处理顺序：

1. Adapter 提供授权聚合指标时，使用 fetch_market_metrics。
2. Adapter 没有聚合指标时，只计算商品样本指标。
3. 无法得到的全市场字段返回 unavailable。

## 5. 可以从商品样本计算的内容

- sample_product_count
- sample_min_price
- sample_max_price
- sample_median_price
- sample_price_distribution
- sample_sales_display_distribution
- sample_shop_concentration
- sample_product_concentration

字段名称必须带 sample 前缀，scope 中写明实际商品数、平台、关键词和采集时间。

## 6. 不能从普通搜索样本推导的内容

- 全市场规模
- 全市场 GMV
- 类目增长率
- 完整品牌份额
- 完整商品份额

这些字段返回 status=unavailable 和 reason_code=AGGREGATE_MARKET_DATA_MISSING。

## 7. 统计规则

- 金额计算使用 Decimal。
- 中位数和价格分箱使用固定算法，算法版本写入 methodology。
- sales_display 保留原文。
- lower_bound 销量只能用于下界说明，不能当作精确销量。
- unknown 销量不进入销量合计。
- 不同货币不能直接合并。

## 8. 输出

输出 MarketSnapshot，其中每个指标都有 value、unit、status、scope、methodology 和 evidence_ids。

## 9. 降级

只得到样本统计时 Tool 调用可以成功，degraded=true。报告必须告诉用户结果只代表样本。

## 10. 测试

- 完整市场指标读取。
- 只有商品样本。
- 不同销量语义。
- 不同货币冲突。
- 空样本。
- 过期指标。
- 统计结果可重复。

