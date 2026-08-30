# ReviewInsightTool

## 1. 作用

ReviewInsightTool把评论整理成主题、情感、痛点和需求，并保留能够回到原评论的引用。

## 2. 需求对应

对应 FR-022。聚合结果必须保留样本评论引用。

## 3. 当前数据来源

当前由 DatasetAdapter 提供固定评论数据。以后只有平台官方 API 明确提供评论接口且租户获得权限时，OfficialApiAdapter 才能返回真实评论；没有官方评论能力时结果为 unavailable。

## 4. 输入

| 字段 | 说明 |
| --- | --- |
| product_ids | 要分析的商品 |
| review_limit_per_product | 每件商品最多使用的评论数 |
| reviews | NormalizedReview 数组 |
| language | 评论语言 |
| evidence_refs | 评论证据 |

## 5. 处理过程

1. 校验评论与 product_id 的关联。
2. 去除空文本和重复评论。
3. 检查个人信息脱敏。
4. 统计评分和情感标签。
5. 聚合主题标签。
6. 按主题整理痛点和需求。
7. 为每个主题选择少量脱敏样本引用。
8. 输出样本范围和限制。

阶段一固定数据集中的 sentiment 和 themes 使用经过版本化的标注结果。Tool 做确定性聚合。以后增加自动分类时，必须记录 model_version、prompt_version 和分类 Schema 版本。

## 6. 输出

| 字段 | 说明 |
| --- | --- |
| sample_scope | 商品数、评论数、平台和时间范围 |
| sentiment_distribution | 正向、中性、负向数量和比例 |
| themes | 主题、数量、比例和证据 |
| pain_points | 痛点及评论引用 |
| unmet_needs | 未满足需求及评论引用 |
| representative_reviews | 脱敏样本评论 |
| data_status | available、partial 或 unavailable |
| evidence_refs | 评论证据 |

## 7. 引用要求

页面展示评论原文时只展示短片段。每条引用包含 review_id、product_id、platform、source_ref 和 review_time。评论聚合不能只引用商品页面。

## 8. 降级

- 没有评论数据：status=unavailable。
- 部分商品有评论：status=partial。
- 评论数量太少：保留结果，同时增加 REVIEW_SAMPLE_TOO_SMALL。
- 评论全部重复或为空：返回 DATA_EMPTY。

## 9. 测试

- 主题统计。
- 情感比例。
- 评论去重。
- 样本引用。
- 个人信息脱敏。
- 评论不足和部分商品缺失。
- 固定数据集重复运行结果一致。
