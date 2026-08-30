from typing import Literal

from pydantic import ConfigDict, BaseModel, Field
from decimal import Decimal

from app.modules.market_intelligence.schemas.common import CurrencyCode, Ratio


class ProfitInput(BaseModel):
    price: Decimal = Field(gt=Decimal("0"))
    product_cost: Decimal = Field(ge=Decimal("0"))
    platform_fee: Decimal = Field(ge=Decimal("0"))
    logistics_cost: Decimal = Field(ge=Decimal("0"))
    advertising_cost: Decimal = Field(ge=Decimal("0"))


class ProfitCalculatorParameters(ProfitInput):
    """市场情报利润测算所需的完整、版本化参数。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal["1.0"] = "1.0"
    minimum_margin: Ratio
    currency: CurrencyCode
