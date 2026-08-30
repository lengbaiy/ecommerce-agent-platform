# 市场机会页面

## 1. 页面目标

把当前静态“市场机会”占位页替换为真实任务页面。页面只负责输入、任务状态和结果展示。

## 2. 页面结构

### 分析条件

- 目标市场
- 商品类目
- 单个关键词
- 平台
- 数据源模式
- 商品数量
- 每件商品评论数量
- 排序
- 售价和成本
- 最低毛利

当前页面的数据源模式固定为 fixed_dataset。后期注册 OfficialApiAdapter 后，页面根据 capabilities 显示平台支持的商品、评论和市场指标范围。官方 API 不支持评论时，评论数量输入禁用并说明原因。

### 执行进度

显示：

- 当前任务状态。
- 当前节点。
- 已完成节点。
- Tool 名称和安全摘要。
- 重试和降级提示。
- 取消按钮。

### 结果

按下面顺序展示：

1. 分析范围和数据时间。
2. 数据限制。
3. 市场快照。
4. 竞品矩阵。
5. 评论洞察。
6. 利润分析。
7. 进入判断。
8. 事实。
9. 推断。
10. 市场机会。
11. 风险。
12. 后续动作。
13. 证据来源。

数据限制放在报告前部，避免用户先看到强结论再发现数据不足。

## 3. 交互规则

- 提交期间禁用重复点击。
- 参数错误显示到对应字段。
- 创建成功后把 task_id 写入路由或本地恢复状态。
- 页面刷新后先查询任务，再恢复 SSE。
- 任务运行中允许取消。
- FAILED 显示错误码、可读原因和已经保留的结果。
- DEGRADED 显示黄色提示和受影响字段。
- unavailable 字段显示“当前数据无法提供”，不显示 0。
- 进入判断为INSUFFICIENT_DATA时，直接展示缺少的数据和受影响结论。

## 4. 证据查看

用户点击关键数字或结论时可以查看：

- 数据来源。
- 平台和商品 ID。
- 查询范围。
- 来源时间和入库时间。
- 数据版本。
- 样本数量。
- 页面或数据集快照引用。

普通运营用户不能看到服务器存储路径、Cookie、Token 和未脱敏页面内容。

## 5. 前端模块

建立独立 market-intelligence 目录，包含：

    views/MarketOpportunityView.vue
    components/MarketIntelligenceForm.vue
    components/TaskProgress.vue
    components/MarketIntelligenceReport.vue
    components/EvidenceDrawer.vue
    api/marketIntelligence.ts
    store/marketIntelligence.ts
    types/marketIntelligence.ts

前端类型由后端 OpenAPI Schema 生成或严格同步，不能自行增加后端不存在的字段。

## 6. 当前状态

当前 App.vue 仍使用通用 ModuleWorkspace，createMarketTask 仍提交固定示例。阶段五需要替换为独立页面和真实参数。

## 7. 页面验收

- 不再显示固定指标和固定报告。
- 能创建、查询、恢复和取消真实任务。
- SSE 能显示节点和 Tool 进度。
- 完整固定数据集报告可以展示。
- 固定数据集中的商品、评论和市场指标可以展示和追溯。
- 后期官方API数据可以追溯到平台接口、查询范围和调用时间。
- 空数据、降级和停止原因清楚可见。
