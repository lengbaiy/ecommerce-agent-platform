from app.domain import AgentResult


class LocalCommerceAdapter:
    """不连接真实电商平台的开发期商品方案幂等写入模拟器。"""

    def __init__(self) -> None:
        self._executed: set[str] = set()

    def save_product_plan(self, result: AgentResult, idempotency_key: str) -> str:
        if idempotency_key in self._executed:
            return f"adapter:duplicate_ignored:{idempotency_key}"
        self._executed.add(idempotency_key)
        return f"adapter:product_plan_saved:{result.result_type}:{idempotency_key}"
