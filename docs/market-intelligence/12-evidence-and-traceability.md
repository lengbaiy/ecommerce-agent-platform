# 证据与来源追溯

## 1. 目标

用户看到的关键数字和结论都能追溯到数据来源、Tool 调用和任务。需求规格书要求从最终结论回到证据，再回到原始 Tool 或 RAG 调用。

## 2. EvidenceReference

| 字段 | 说明 |
| --- | --- |
| evidence_id | 证据 ID |
| evidence_type | product、review、market_metric、profit_input、dataset 或 api_response |
| data_level | A、B、C 或 D |
| data_source | 数据来源名称 |
| platform | 业务平台 |
| product_id | 商品证据使用 |
| review_id | 评论证据使用 |
| query_range | 查询条件和范围 |
| source_timestamp | 原始数据时间 |
| ingest_timestamp | 系统接收时间 |
| tool_call_id | 产生证据的 Tool 调用 |
| collection_run_id | 采集批次 |
| snapshot_ref | 固定数据集记录或官方 API 响应快照引用 |
| sha256 | 快照哈希 |
| data_version | 数据、Adapter 或解析器版本 |
| sample_scope | 实际样本范围 |

## 3. 数据等级

- A：数据库、授权 API、固定授权数据或确定性计算结果。
- B：带版本和引用的企业知识。
- C：Agent 根据 A 或 B 形成的推断。
- D：缺失、未知或质量不足。

合成固定数据集标记 demo_only，并在报告范围中说明。官方 API 数据只有在授权范围和数据状态有效时标记为业务事实。

## 4. 追溯链

官方 API 数据：

    task_id
      -> trace_id
      -> tool_call_id
      -> collection_run
      -> official_api_call
      -> source_snapshot
      -> product_snapshot
      -> evidence_id
      -> report statement

固定数据集：

    task_id
      -> tool_call_id
      -> dataset_id + dataset_version
      -> record_id
      -> evidence_id
      -> report statement

## 5. CollectionRun

至少保存 id、task_id、trace_id、tenant_id、keyword、requested_count、actual_count、status、stop_reason、adapter_version、parser_version、started_at 和 finished_at。

## 6. 数据源快照

- 固定数据集使用 dataset_id、dataset_version、record_id 和文件哈希。
- 官方 API 响应是否保存取决于官方数据保存规则。
- 允许保存时，响应先脱敏，再保存压缩内容和SHA-256。
- 禁止保存完整响应时，只保存接口、记录主键、查询范围、时间、版本和允许保留的摘要。
- 数据库保存 object_key，不向普通页面返回 storage_path。
- 快照读取需要租户权限。
- 页面只展示平台、接口、时间、哈希、版本和允许展示的摘要。

## 7. 报告证据规则

- 每个关键数字至少一个 evidence_id。
- 每个事实至少一个 evidence_id。
- 推断、机会和风险至少引用一个事实或证据。
- 评论主题至少引用一条脱敏评论。
- 竞品至少关联 platform、product_id 和 source。
- 数据冲突同时保留多个证据，不自动选择其中一个。

## 8. 覆盖率

Evidence Coverage 的计算口径：

    有有效 evidence_ids 的关键结论数 / 关键结论总数

关键结论包括 facts、opportunity_signals 和 risk_signals 中标记 critical=true 的项。目标不低于 95%。
