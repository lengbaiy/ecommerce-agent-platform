# ProductSearchTool

## 1. 作用

ProductSearchTool 根据平台和数据源模式选择 Adapter，返回统一商品列表、样本范围和证据。Graph 不直接调用 AdapterRegistry。

## 2. 输入

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| task_id | 是 | 任务 ID |
| platform | 是 | taobao、jd 等 |
| data_source_mode | 是 | 当前为 fixed_dataset，后期为 official_api |
| market | 是 | 目标市场 |
| category | 是 | 类目 |
| keyword | 是 | 单个关键词 |
| product_limit | 是 | 1 到服务端配置上限 |
| sort_by | 是 | 排序方式 |
| tool_call_id | 否 | 未提供时由系统生成 |

tenant_id、user_id 和 trace_id 来自 ToolRequest 公共字段。

## 3. 执行过程

1. 校验任务身份、关键词和数量。
2. 读取 AdapterRegistry。
3. 检查 AdapterCapabilities。
4. 执行 search_products。
5. 校验每个商品的统一 Schema。
6. 生成商品级 EvidenceReference。
7. 返回数量、采集状态、停止原因、版本和商品列表。

## 4. 输出 data

| 字段 | 说明 |
| --- | --- |
| collection_run_id | 本次读取或采集批次 |
| keyword | 实际关键词 |
| requested_count | 请求数量 |
| actual_count | 实际数量 |
| status | COMPLETED、PARTIAL 或 FAILED |
| stop_reason | 未完成原因 |
| adapter_version | Adapter 版本 |
| parser_version | 解析器版本；DatasetAdapter 可为空 |
| products | NormalizedProduct 数组 |
| evidence_refs | 商品证据 |
| source_snapshots | 允许返回给上层的数据源快照元数据 |

source_snapshots 不包含本地存储路径和敏感内容。

## 5. 去重和排序

- 同一次采集按 platform 和 product_id 去重。
- Adapter 首先按数据源能力执行排序。
- 数据源不支持指定排序时返回 UNSUPPORTED_SORT。
- Tool 不根据标题相似度合并不同 product_id。

## 6. 降级

实际商品数量少于 requested_count 时 success=true、degraded=true，并返回 PARTIAL。零商品返回 DATA_EMPTY。

## 7. 当前实现差距

现有 ProductSearchTool 与淘宝页面采集绑定，不再作为目标实现。完整模块需要保留 Tool 的公共职责，改为接入 CommerceAdapterRegistry、公共请求 Schema 和 DatasetAdapter，并补充 market、category 字段。以后 OfficialApiAdapter 继续通过相同 Registry 接入。

## 8. 测试

- 单关键词校验。
- product_limit 边界。
- Adapter 选择。
- 未授权租户。
- 空数据和部分数据。
- 商品去重。
- 证据引用。
- 错误码转换。
- ToolResponse 不泄露 storage_path。
