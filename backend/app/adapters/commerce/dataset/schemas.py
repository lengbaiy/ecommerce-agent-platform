from datetime import datetime
from decimal import Decimal
from typing import Any

from app.modules.market_intelligence.schemas.common import (
    MarketIntelligenceModel,
    MetricStatus,
    NonEmptyStr,
)


class DatasetMarketMetricRecord(MarketIntelligenceModel):
    """market_metrics.json 中单条指标的存储结构。"""

    metric_code: NonEmptyStr
    value: (
        Decimal
        | int
        | float
        | dict[str, Any]
        | list[Any]
        | None
    ) = None
    unit: NonEmptyStr | None = None
    status: MetricStatus
    reason_code: NonEmptyStr | None = None
    methodology: NonEmptyStr
    source_timestamp: datetime | None = None
