# 模块架构

## 1. 当前独立调用链

    MarketOpportunityView
      -> POST /api/v1/agent/tasks
      -> TaskService
      -> MarketIntelligenceTaskDispatcher
      -> MarketIntelligenceService
      -> MarketIntelligenceGraph
      -> Tool
      -> CommerceAdapterRegistry
      -> DatasetAdapter
         后期可替换为各平台 OfficialApiAdapter
      -> MarketIntelligenceReport

浏览器只调用 HTTP API。浏览器不直接调用 Python Service 或 Graph。

## 2. 从运营需求到市场机会报告

下面的图从业务视角说明市场情报能力如何处理一条运营需求。图中的 MarketIntelligenceAgent 是整个市场情报业务能力的逻辑名称，内部由 MarketIntelligenceService、MarketIntelligenceGraph、报告生成 Agent 和证据校验节点共同完成。

用户示例：

``` text
用户：
“分析便携咖啡机在 US 市场是否值得进入，
目标毛利不低于30%，并给出产品机会点。”

                    ↓

          MarketIntelligenceGraph
                    │
     ┌──────────────┼────────────────┬──────────────────┐
     ↓              ↓                ↓                  ↓
MarketDataTool ProductSearchTool ReviewInsightTool ProfitCalculatorTool
     ↓              ↓                ↓                  ↓
MarketMetric  NormalizedProduct ReviewInsight      ProfitAnalysis
                    ↓
         build_competitor_matrix
                    ↓
             CompetitorItem
     └──────────────┴────────────────┴──────────────────┘
                    ↓
      synthesize_report + validate_evidence
                    ↓
          MarketIntelligenceReport
```

### 2.1 图中组件的职责

| 组件 | 说明 |
| --- | --- |
| MarketIntelligenceService | 对外提供统一执行入口 |
| MarketIntelligenceGraph | 编排四个Tool、竞品矩阵、报告生成和证据校验 |
| MarketDataTool | 返回全市场指标或明确标注的样本统计 |
| ProductSearchTool | 获取候选竞品和来源证据 |
| build_competitor_matrix | 把NormalizedProduct转换成CompetitorItem，不额外增加同义Tool |
| ReviewInsightTool | 返回评论样本、主题、情感、痛点、未满足需求和评论证据 |
| ProfitCalculatorTool | 根据完整ProfitCalculatorParameters返回确定性的ProfitAnalysis，基础字段复用contracts.py中的ProfitInput |
| synthesize_report | 综合四类结果，生成MarketIntelligenceReport |
| validate_evidence | 校验结论、约束、数据限制和证据 |

### 2.2 与现有架构的边界

- 当前独立页面把表单参数组装成 MarketIntelligenceRequest；未来根 Graph 中的 Supervisor 可以把自然语言需求解析成同一请求结构。MarketIntelligenceService 不承担通用意图识别。
- MarketIntelligenceGraph 调用 Tool 并控制执行顺序、重试和降级。报告生成 Agent 读取 Tool 的结构化结果，不直接访问 Adapter、数据库、网页或平台 API。
- MarketDataTool、ProductSearchTool生成的竞品矩阵和ReviewInsightTool结果共同进入分析层。Graph只把完整的ProfitCalculatorParameters交给ProfitCalculatorTool；成本缺失时生成unavailable结果。评论或市场指标不能直接生成成本。
- 竞品价格可以作为售价或价格带证据。进入利润计算前，Graph 必须把它转换成币种和口径明确的测算场景，Agent 不能自行猜测采购、物流、平台或广告成本。
- “产品机会点”在本模块中表示由市场空白、竞品差异、评论痛点和未满足需求支持的 opportunity_signals。涉及具体产品定位、规格组合、定价策略和卖点时，把证据化机会交给商品策略 Agent。
- 最终报告同时保留事实、推断、机会、风险、利润约束结果、数据限制和 evidence_ids。证据不足时把任务标记为 DEGRADED、记录 data_limitations，并删除无依据的强进入结论。

### 2.3 已确定的公开契约

本图与现有分层和依赖方向兼容，具体契约如下：

- CompetitorItem和EntryAssessment在04-data-models.md中定义，并进入MarketIntelligenceReport。
- MarketIntelligenceState保存competitor_matrix，Graph在search_products之后执行build_competitor_matrix。
- 明确 DatasetAdapter 中 `profit_inputs.json` 进入 Graph 的读取接口；Graph校验完整后调用ProfitCalculatorTool。现有 Adapter 公共接口没有利润输入读取方法。
- US市场示例属于目标业务流程。当前必须使用覆盖US市场、评论和成本的固定数据集；以后使用具备相应权限的OfficialApiAdapter。数据范围不足时必须降级，不能生成US全市场强结论。

## 3. 各层负责什么

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| 页面 | 收集参数、显示任务进度和结果 | 计算市场指标、拼接证据 |
| API | 鉴权、参数解析、HTTP 和 SSE 响应 | 执行业务分析 |
| TaskService | 创建任务、状态流转、取消和恢复 | 了解各个 Graph 的内部节点 |
| Dispatcher | 根据 intent 选择执行器 | 处理市场业务逻辑 |
| MarketIntelligenceService | 组织一次市场情报用例 | 访问页面组件或根图对象 |
| MarketIntelligenceGraph | 控制步骤顺序、重试、降级和持久化 | 直接访问固定数据文件或平台官方API |
| Agent | 根据结构化证据生成报告 | 计算利润、补造数据 |
| Tool | 查询、统计、聚合和确定性计算 | 处理 HTTP 页面和平台差异 |
| Adapter | 访问数据源、统一字段、映射错误 | 生成市场结论 |
| Repository | 保存任务、快照、证据和结果 | 做业务判断 |

## 4. 依赖方向

依赖只能沿下面方向：

    API 或未来主图
      -> MarketIntelligenceService
      -> MarketIntelligenceGraph
      -> Tool
      -> Adapter
      -> 外部数据源

MarketIntelligenceService 依赖独立的 Schema 和 Repository。市场情报模块不能导入根 Graph 或其他 Agent 的内部类型。

## 5. 当前入口与未来入口

当前入口是统一任务 API。未来入口是根 Graph 中的市场情报节点。两个入口共用下面的公开方法：

    MarketIntelligenceService.execute(request, context)
      -> MarketIntelligenceReport

一期只实现任务 API 入口。公开方法从第一版开始保持与页面无关，保证以后接入主图时不用改 Tool、Adapter 和报告结构。

## 6. 运行方式

TaskService 的 inline 模式和 worker 模式必须使用同一个 Dispatcher：

- inline：创建任务后由当前 API 进程执行。
- worker：创建任务后进入队列，由 worker 领取并执行。

两种模式只能在“谁来执行”上不同，intent 分派、Graph、状态和结果结构必须一致。

## 7. 数据存储

- PostgreSQL 保存任务、步骤、Tool 调用摘要、采集批次、商品快照和最终报告。
- Redis 保存运行中的状态、Checkpoint、缓存和分布式控制。
- 对象存储可以保存经过授权和脱敏的数据源响应快照。
- 当前固定数据集直接使用数据集版本、记录 ID 和文件哈希作为来源证据。

## 8. 安全边界

- tenant_id 和 user_id 来自鉴权上下文。
- 页面请求中的同名字段不能覆盖鉴权结果。
- Adapter 只接收业务参数，不接收用户提供的任意 URL。
- 原始快照存储路径不返回给普通页面。
- Tool 和 Adapter 日志不得记录 Cookie、Token 和完整凭据。
