from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_market_overview_service
from app.core.security import TaskReadDependency
from app.modules.market_intelligence.overview import MarketOverview, MarketOverviewService

router = APIRouter(prefix="/analytics", tags=["分析"])


@router.get("/market", response_model=MarketOverview)
def market(
    principal: TaskReadDependency,
    service: Annotated[MarketOverviewService, Depends(get_market_overview_service)],
    market: Annotated[str, Query(min_length=1)] = "US",
    category: Annotated[str | None, Query(min_length=1)] = None,
) -> MarketOverview:
    return service.overview(principal.tenant_id, market, category)


@router.get("/operations")
def operations(shop_id: str, sku: str | None = Query(default=None)) -> dict:
    return {"shop_id": shop_id, "sku": sku, "data_status": "unavailable", "source": None}
