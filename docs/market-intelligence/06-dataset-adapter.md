# DatasetAdapter

## 1. 作用

DatasetAdapter 提供稳定、可重复的数据，用来先验证完整市场机会链路。它需要覆盖商品、市场指标、评论和利润输入，避免页面和Graph依赖临时假数据。

利润输入使用`app.tools`公开导出的ProfitInput字段。

## 2. 数据目录

每个数据集使用独立目录：

    backend/tests/fixtures/market_intelligence/{dataset_id}/
      manifest.json
      products.json
      reviews.json
      market_metrics.json
      profit_inputs.json

演示数据可以放在单独的 demo 数据目录，但必须使用同一格式。

## 3. manifest.json

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| dataset_id | 是 | 数据集唯一 ID |
| dataset_version | 是 | 固定版本 |
| schema_version | 是 | 数据 Schema 版本 |
| platform | 是 | taobao、jd 等 |
| market | 是 | 市场 |
| category | 是 | 类目 |
| keyword | 是 | 对应关键词 |
| source_type | 是 | synthetic、authorized_export、anonymized_snapshot或"public_research_dataset" |
| source_description | 是 | 数据来源说明 |
| collected_from | 否 | 原数据时间范围 |
| generated_at | 是 | 数据集生成时间 |
| expires_at | 否 | 失效时间 |
| license_or_authorization | 是 | 使用权限说明 |
| checksums | 是 | 每个文件的 SHA-256 |

## 4. 读取规则

1. 根据 platform、market、category 和 keyword 找到数据集。
2. 校验 manifest、schema_version 和文件哈希。
3. 校验租户是否有权使用该数据集。
4. 按 product_limit 和 review_limit_per_product 截取数据。
5. 转成统一模型。
6. 生成 collection_run 和 evidence_refs。
7. 返回数据集版本、时间和样本范围。

## 5. 数据状态

- synthetic 数据标记 demo_only。
- 授权导出数据标记 valid。
- 超过 expires_at 标记 stale。
- 文件缺失、哈希不一致或 Schema 不合法时任务失败。
- 查询条件没有匹配数据集时返回 DATA_EMPTY。

## 6. 可重复性

相同数据集版本、相同参数和相同 Tool 版本必须得到相同的确定性统计结果。测试不能在运行时随机生成价格、销量、评论和成本。

## 7. 隐私

评论和店铺数据必须脱敏。数据集不能包含 Cookie、Token、手机号、地址、用户账号和未经授权的个人信息。

## 8. 验收

- 能返回商品、评论、市场指标和利润输入。
- 所有数据都能追溯到 dataset_id 和 dataset_version。
- 缺文件、错误哈希、错误版本和空数据都有稳定错误码。
- CI 全程使用固定数据集；以后测试 OfficialApiAdapter 时使用官方 API Mock，不访问真实平台。
