# 未来主图接入契约

## 1. 当前范围

本文件只规定未来主图如何调用市场情报模块。当前阶段不修改 SupervisorAgent、EcommerceOperationsGraph 和其他 Agent。

## 2. 唯一公开入口

未来主图调用：

    MarketIntelligenceService.execute(
        request: MarketIntelligenceRequest,
        context: MarketIntelligenceContext,
    ) -> MarketIntelligenceReport

主图不能直接调用 MarketIntelligenceGraph 的内部节点，也不能直接调用市场情报 Adapter。

## 3. 主图需要提供的数据

- task_id
- tenant_id
- user_id
- trace_id
- user_query
- constraints
- market
- category
- keyword
- platforms
- data_source_mode
- collection
- profit_constraints，可为空

这些字段与独立页面使用的结构完全相同。

## 4. 返回给主图的数据

主图只接收：

| 字段 | 说明 |
| --- | --- |
| report_id | 报告 ID |
| schema_version | 报告 Schema 版本 |
| status | COMPLETED、DEGRADED 或 FAILED |
| report | 完整 MarketIntelligenceReport |
| evidence_refs | 报告证据 |

建议写入统一状态的位置是：

    AgentState.agent_outputs.market_intelligence

这里只规定字段契约，不修改当前 AgentState 代码。

## 5. 下游使用规则

后续业务节点可以读取 market_snapshot、competitor_matrix、review_insights、profit_analysis、opportunity_signals、risk_signals、data_limitations 和 evidence_refs。

下游不能依赖：

- 市场情报 Graph 节点名称。
- Tool 原始返回对象。
- Adapter 类和注册键。
- collection_run 数据库表结构。
- 页面 Store。

## 6. 状态映射

| 市场情报结果 | 主图可见状态 |
| --- | --- |
| COMPLETED | 节点成功 |
| DEGRADED | 节点完成，同时保留 degraded_flags |
| FAILED | 节点失败，由主图决定是否终止或请求补充数据 |

主图不得把 DEGRADED 自动改成完整成功。

## 7. 版本规则

- 主图声明自己支持的 MarketIntelligenceReport 大版本。
- Service 返回不兼容大版本时，接入层返回 SCHEMA_VERSION_UNSUPPORTED。
- 下游使用字段名和类型以公开 Schema 为准。
- Graph 内部重构不影响公开契约。

## 8. 后期接入验收

- 主图和页面调用得到相同结构。
- 主图 Trace 保留同一个 task_id 和 trace_id。
- 证据引用进入下游后仍可追溯。
- 市场情报模块可以独立测试。
- 接入不要求页面、Tool 或 Adapter 改接口。

