from decimal import Decimal

import pytest

from app.tools import ToolRequest
from app.tools.profit_calculator import ProfitCalculatorTool


def make_request(**overrides) -> ToolRequest:
    """
    创建一份默认合法的 ProfitCalculatorTool 请求。
    每个测试只覆盖自己关心的字段。
    """
    parameters = {
        "price": 100.0,
        "product_cost": 30.0,
        "platform_fee": 10.0,
        "logistics_cost": 8.0,
        "advertising_cost": 12.0,
        "minimum_margin": "0.30",
        "currency": "USD",
    }

    parameters.update(overrides)

    return ToolRequest(
        tenant_id="tenant-001",
        user_id="user-001",
        trace_id="trace-001",
        parameters=parameters,
    )


def test_calculates_profit_successfully() -> None:
    tool = ProfitCalculatorTool()

    response = tool.execute(make_request())

    assert response.success is True
    assert response.error is None
    assert response.data["schema_version"] == "1.0"
    assert response.source == "profit_calculator"
    assert response.trace_id == "trace-001"
    assert response.degraded is False

    analysis = response.data["profit_analysis"]

    assert analysis["status"] == "available"
    assert Decimal(analysis["selling_price"]) == Decimal("100.0")
    assert Decimal(analysis["total_cost"]) == Decimal("60.0")
    assert Decimal(analysis["profit"]) == Decimal("40.0")
    assert Decimal(analysis["margin"]) == Decimal("0.4")
    assert Decimal(analysis["minimum_margin"]) == Decimal("0.30")
    assert analysis["meets_minimum_margin"] is True
    assert analysis["currency"] == "USD"

    assert analysis["breakdown"] == {
        "product_cost": "30.0",
        "platform_fee": "10.0",
        "logistics_cost": "8.0",
        "advertising_cost": "12.0",
    }


@pytest.mark.parametrize(
    (
        "product_cost",
        "platform_fee",
        "logistics_cost",
        "advertising_cost",
        "expected_profit",
        "expected_margin",
    ),
    [
        # 正利润
        (30.0, 10.0, 10.0, 10.0, "40.0", "0.4"),

        # 零利润
        (50.0, 20.0, 20.0, 10.0, "0.0", "0.0"),

        # 负利润
        (80.0, 20.0, 10.0, 10.0, "-20.0", "-0.2"),
    ],
)
def test_supports_positive_zero_and_negative_profit(
    product_cost: float,
    platform_fee: float,
    logistics_cost: float,
    advertising_cost: float,
    expected_profit: str,
    expected_margin: str,
) -> None:
    tool = ProfitCalculatorTool()

    response = tool.execute(
        make_request(
            product_cost=product_cost,
            platform_fee=platform_fee,
            logistics_cost=logistics_cost,
            advertising_cost=advertising_cost,
        )
    )

    assert response.success is True

    analysis = response.data["profit_analysis"]

    assert Decimal(analysis["profit"]) == Decimal(expected_profit)
    assert Decimal(analysis["margin"]) == Decimal(expected_margin)

def test_rounds_money_and_margin() -> None:
    tool = ProfitCalculatorTool()

    response = tool.execute(
        make_request(
            price="99.999",
            product_cost="30.001",
            platform_fee="10.004",
            logistics_cost="8.001",
            advertising_cost="12.001",
        )
    )

    assert response.success is True

    analysis = response.data["profit_analysis"]

    assert Decimal(
        analysis["selling_price"]
    ) == Decimal("100.00")

    assert Decimal(
        analysis["total_cost"]
    ) == Decimal("60.01")

    assert Decimal(
        analysis["profit"]
    ) == Decimal("39.99")

    assert Decimal(
        analysis["margin"]
    ) == Decimal("0.3999")

def test_margin_equal_to_minimum_margin_is_accepted() -> None:
    tool = ProfitCalculatorTool()

    # 总成本 = 70
    # profit = 30
    # margin = 0.30
    response = tool.execute(
        make_request(
            product_cost=40.0,
            platform_fee=10.0,
            logistics_cost=10.0,
            advertising_cost=10.0,
            minimum_margin="0.30",
        )
    )

    assert response.success is True

    analysis = response.data["profit_analysis"]

    assert Decimal(analysis["margin"]) == Decimal("0.3")
    assert analysis["meets_minimum_margin"] is True


def test_margin_below_minimum_margin_is_rejected() -> None:
    tool = ProfitCalculatorTool()

    # 总成本 = 70
    # margin = 0.30
    # 最低要求 = 0.40
    response = tool.execute(
        make_request(
            product_cost=40.0,
            platform_fee=10.0,
            logistics_cost=10.0,
            advertising_cost=10.0,
            minimum_margin="0.40",
        )
    )

    assert response.success is True

    analysis = response.data["profit_analysis"]

    assert Decimal(analysis["margin"]) == Decimal("0.3")
    assert analysis["meets_minimum_margin"] is False


def test_negative_cost_returns_invalid_argument() -> None:
    tool = ProfitCalculatorTool()

    response = tool.execute(
        make_request(product_cost=-1.0)
    )

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "INVALID_ARGUMENT"
    assert response.error.retryable is False


def test_zero_price_returns_invalid_argument() -> None:
    tool = ProfitCalculatorTool()

    response = tool.execute(
        make_request(price=0)
    )

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "INVALID_ARGUMENT"


def test_invalid_minimum_margin_returns_invalid_argument() -> None:
    tool = ProfitCalculatorTool()

    response = tool.execute(
        make_request(minimum_margin="1.01")
    )

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "INVALID_ARGUMENT"


def test_invalid_currency_returns_invalid_argument() -> None:
    tool = ProfitCalculatorTool()

    response = tool.execute(
        make_request(currency="US")
    )

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "INVALID_ARGUMENT"


def test_missing_cost_returns_invalid_argument() -> None:
    tool = ProfitCalculatorTool()

    request = make_request()

    del request.parameters["logistics_cost"]

    response = tool.execute(request)

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "INVALID_ARGUMENT"


def test_empty_trace_id_returns_invalid_argument() -> None:
    tool = ProfitCalculatorTool()

    request = make_request()
    request.trace_id = ""

    response = tool.execute(request)

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "INVALID_ARGUMENT"


def test_same_input_produces_same_profit_result() -> None:
    tool = ProfitCalculatorTool()

    request1 = make_request()
    request2 = make_request()

    response1 = tool.execute(request1)
    response2 = tool.execute(request2)

    assert response1.success is True
    assert response2.success is True

    assert (
        response1.data["profit_analysis"]
        == response2.data["profit_analysis"]
    )


def test_profit_calculator_rejects_unsupported_schema_version() -> None:
    tool = ProfitCalculatorTool()

    response = tool.execute(make_request(schema_version="2.0"))

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "SCHEMA_VERSION_UNSUPPORTED"
    assert response.data["schema_version"] == "1.0"
    
