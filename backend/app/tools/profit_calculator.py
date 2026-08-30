from decimal import Decimal

from pydantic import ValidationError

from app.modules.market_intelligence.schemas.analysis import ProfitAnalysis
from app.modules.market_intelligence.schemas.common import ProfitStatus
from app.modules.market_intelligence.schemas.profit import (
    ProfitCalculatorParameters,
)
from app.tools.support.contracts import (
    ToolError,
    ToolRequest,
    ToolResponse,
    calculate_profit,
)


class ProfitCalculatorTool:
    """
    根据已有 ProfitInput 执行确定性的利润计算。

    本 Tool 不负责：
    - 获取成本数据
    - 查询数据库
    - 读取 Excel
    - 推测缺失成本
    """

    name = "profit_calculator"
    schema_version = "1.0"
    calculation_version = "profit-v1"

    def execute(self, request: ToolRequest) -> ToolResponse:
        # 1. 校验 Tool 公共身份字段
        identity_error = self._validate_tool_identity(request)
        if identity_error is not None:
            return self._error_response(
                request=request,
                code="INVALID_ARGUMENT",
                message=identity_error,
            )

        # 2. 校验 ProfitCalculatorTool 参数
        try:
            parameters = ProfitCalculatorParameters.model_validate(
                request.parameters
            )
        except ValidationError as exc:
            return self._error_response(
                request=request,
                code="INVALID_ARGUMENT",
                message=self._error_summary(exc),
            )

        if parameters.schema_version != self.schema_version:
            return self._error_response(
                request=request,
                code="SCHEMA_VERSION_UNSUPPORTED",
                message=(
                    "Unsupported ProfitCalculatorTool schema version: "
                    f"{parameters.schema_version}."
                ),
            )

        try:
            # 4. 复用 support/contracts.py 中已有的利润计算函数
            result = calculate_profit(parameters)

            # 5. 转换成 Market Intelligence 的 ProfitAnalysis
            analysis = self._build_analysis(
                parameters,
                result,
            )
        except Exception:
            return self._error_response(
                request=request,
                code="PROFIT_CALCULATION_FAILED",
                message=("Profit calculation failed because of an internal error."),
            )

        # 6. 返回统一 ToolResponse
        return ToolResponse(
            success=True,
            data={
                "schema_version": self.schema_version,
                "profit_analysis": analysis.model_dump(mode="json"),
            },
            error=None,
            source=self.name,
            trace_id=request.trace_id,
            degraded=False,
        )

    def _build_analysis(
        self,
        parameters: ProfitCalculatorParameters,
        result: dict[str, Decimal],
    ) -> ProfitAnalysis:
        margin = result["margin"]

        return ProfitAnalysis(
            status=ProfitStatus.AVAILABLE,
            selling_price=result["revenue"],
            total_cost=result["total_cost"],
            profit=result["profit"],
            margin=margin,
            minimum_margin=parameters.minimum_margin,
            meets_minimum_margin=(
                margin >= parameters.minimum_margin
            ),
            breakdown={
                "product_cost": parameters.product_cost,
                "platform_fee": parameters.platform_fee,
                "logistics_cost": parameters.logistics_cost,
                "advertising_cost": parameters.advertising_cost,
            },
            currency=parameters.currency,
            calculation_version=self.calculation_version,
        )

    
    def _error_response(
        self,
        *,
        request: ToolRequest,
        code: str,
        message: str,
    ) -> ToolResponse:
        return ToolResponse(
            success=False,
            data={"schema_version": self.schema_version},
            error=ToolError(
                code=code,
                message=message,
                retryable=False,
            ),
            source=self.name,
            trace_id=request.trace_id,
            degraded=False,
        )

    @staticmethod
    def _validate_tool_identity(
        request: ToolRequest,
    ) -> str | None:
        """
        与其他 Tool 一致，确保公共身份字段有效。
        """

        for field_name in (
            "tenant_id",
            "user_id",
            "trace_id",
        ):
            value = getattr(
                request,
                field_name,
                None,
            )

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                return f"{field_name} is required"

        return None


    @staticmethod
    def _error_summary(
        error: ValidationError,
    ) -> str:
        first = error.errors()[0]
        location = ".".join(str(item) for item in first.get("loc", ()))
        message = str(first.get("msg","validation failed"))

        if location:
            return f"{location}: {message}"

        return message
