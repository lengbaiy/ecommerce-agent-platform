# ProfitCalculatorTool

## 1. 作用

ProfitCalculatorTool完成确定性的利润和毛利计算。市场情报 Agent 只能引用计算结果，不能自己心算。

## 2. 需求对应

对应 FR-023：完成利润测算与进入约束判断。

## 3. 输入

ProfitCalculatorParameters继承`app.tools`公开导出的ProfitInput，并补充currency和minimum_margin。

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| price | Decimal | 大于 0 |
| product_cost | Decimal | 大于等于 0 |
| platform_fee | Decimal | 大于等于 0 |
| logistics_cost | Decimal | 大于等于 0 |
| advertising_cost | Decimal | 大于等于 0 |
| currency | string | 所有金额使用同一货币 |
| minimum_margin | Decimal | 0 到 1 |

## 4. 公式

    total_cost =
        product_cost
        + platform_fee
        + logistics_cost
        + advertising_cost

    profit = price - total_cost

    margin = profit / price

    meets_minimum_margin = margin >= minimum_margin

margin保留四位小数。输出中的selling_price由price映射。

## 5. 输出

| 字段 | 说明 |
| --- | --- |
| selling_price | 售价 |
| total_cost | 总成本 |
| profit | 单件利润 |
| margin | 毛利率 |
| minimum_margin | 目标毛利率 |
| meets_minimum_margin | 是否满足约束 |
| breakdown | 每项成本 |
| currency | 货币 |
| calculation_version | 计算公式版本 |
| evidence_ids | 输入来源 |

## 6. 数据来源

用户手工输入的成本也需要证据，source_type 标记为 user_input，并记录任务、用户和时间。固定数据集成本引用 dataset_id 和版本。Agent 推断的成本不能进入 Calculator。

## 7. 错误

- 售价小于等于 0：INVALID_ARGUMENT。
- 成本为负数：INVALID_ARGUMENT。
- 币种不一致：CURRENCY_MISMATCH。
- 参数已提供但不合法：INVALID_ARGUMENT。
- 缺少成本：Graph不调用本Tool，生成unavailable并决定DEGRADED。

## 8. 测试

- 正利润、零利润和负利润。
- 毛利刚好等于最低约束。
- margin 舍入。
- 负数和错误币种。
- 相同输入得到相同输出。
