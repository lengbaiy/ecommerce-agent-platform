from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.specialists import build_specialists
from app.agents.state import AgentState
from app.agents.supervisor import SupervisorAgent
from app.domain import AgentResult, AgentTask, TaskEvent, TaskEventType, create_task_event


class GraphContext(TypedDict):
    task: AgentTask
    agent_state: AgentState
    selected_agent: str
    result: AgentResult | None
    events: list[TaskEvent]


class EcommerceOperationsGraph:
    """Supervisor + 4 个业务 Agent 的一期最小编排。"""

    def __init__(self) -> None:
        self.supervisor = SupervisorAgent()
        self.agents = build_specialists()
        self.graph = self._build_graph()

    def run(self, task: AgentTask) -> AgentState:
        state = AgentState(
            task_id=str(task.id),
            user_id=task.request.user_id,
            tenant_id=task.request.tenant_id,
            user_query=task.request.user_query,
            constraints=task.request.constraints,
            intent=task.request.intent,
            business_context=task.request.business_context,
        )
        output = self.graph.invoke(
            {
                "task": task,
                "agent_state": state,
                "selected_agent": "",
                "result": None,
                "events": [],
            }
        )
        task.result = output["result"]
        task.events.extend(output["events"])
        return output["agent_state"]

    def _build_graph(self):
        workflow = StateGraph(GraphContext)
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("judge", self._judge_node)
        for name in self.agents:
            workflow.add_node(name, self._specialist_node(name))
            workflow.add_edge(name, "judge")
        workflow.add_edge(START, "supervisor")
        workflow.add_conditional_edges(
            "supervisor", lambda context: context["selected_agent"], list(self.agents)
        )
        workflow.add_edge("judge", END)
        return workflow.compile()

    def _supervisor_node(self, context: GraphContext) -> GraphContext:
        selected, plan = self.supervisor.select(context["task"].request)
        context["selected_agent"] = selected
        context["agent_state"].task_plan = plan
        context["agent_state"].current_step = selected
        context["events"].append(
            create_task_event(
                context["task"],
                TaskEventType.NODE_COMPLETED,
                f"Supervisor routed task to {selected}.",
                step="supervisor",
            )
        )
        return context

    def _specialist_node(self, name: str):
        def run_specialist(context: GraphContext) -> GraphContext:
            result = self.agents[name].run(context["task"].request)
            context["result"] = result
            context["agent_state"].agent_outputs[name] = result.model_dump(mode="json")
            context["agent_state"].evidence_refs.extend(
                item.model_dump() for item in result.evidence_refs
            )
            context["events"].append(
                create_task_event(
                    context["task"],
                    TaskEventType.NODE_COMPLETED,
                    f"Agent {name} generated a result.",
                    step=name,
                )
            )
            return context

        return run_specialist

    def _judge_node(self, context: GraphContext) -> GraphContext:
        result = context["result"]
        if result is None:
            raise ValueError("specialist agent did not return a result")
        context["agent_state"].current_step = "judge"
        context["events"].append(
            create_task_event(
                context["task"],
                TaskEventType.NODE_COMPLETED,
                "Evidence check completed.",
                step="judge",
            )
        )
        if result.requires_approval:
            context["agent_state"].approval_status = "WAITING_APPROVAL"
            context["events"].append(
                create_task_event(
                    context["task"],
                    TaskEventType.TASK_WAITING_APPROVAL,
                    "Task requires approval.",
                    step="judge",
                )
            )
        else:
            context["agent_state"].final_result = result.model_dump(mode="json")
        return context
