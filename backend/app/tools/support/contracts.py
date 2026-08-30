from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.modules.market_intelligence.schemas import ProfitInput

MONEY_QUANT = Decimal("0.01")
MARGIN_QUANT = Decimal("0.0001")


class ToolRequest(BaseModel):
    tenant_id: str
    user_id: str
    trace_id: str
    task_id: str | None = None
    step_name: str | None = None
    attempt: int = Field(default=1, ge=1)
    idempotency_key: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ToolResponse(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: ToolError | None = None
    source: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trace_id: str
    degraded: bool = False

    @model_validator(mode="after")
    def validate_status_consistency(self) -> "ToolResponse":
        if self.success and self.error is not None:
            raise ValueError(
                "successful ToolResponse must not contain an error"
            )

        if not self.success and self.error is None:
            raise ValueError(
                "failed ToolResponse must contain an error"
            )

        return self


# class ProfitInput(BaseModel):
#     price: Decimal = Field(gt=Decimal("0"))
#     product_cost: Decimal = Field(ge=Decimal("0"))
#     platform_fee: Decimal = Field(ge=Decimal("0"))
#     logistics_cost: Decimal = Field(ge=Decimal("0"))
#     advertising_cost: Decimal = Field(ge=Decimal("0"))

def calculate_profit(payload: ProfitInput) -> dict[str, Decimal]:
    total_cost = (
        payload.product_cost
        + payload.platform_fee
        + payload.logistics_cost
        + payload.advertising_cost
    )
    profit = payload.price - total_cost
    margin = (profit / payload.price).quantize(MARGIN_QUANT,rounding=ROUND_HALF_UP)
    revenue = payload.price.quantize(MONEY_QUANT,rounding=ROUND_HALF_UP)
    total_cost = total_cost.quantize(MONEY_QUANT,rounding=ROUND_HALF_UP)
    profit = profit.quantize(MONEY_QUANT,rounding=ROUND_HALF_UP)

    return {
        "revenue": revenue,
        "total_cost": total_cost,
        "profit": profit,
        "margin": margin,
    }
