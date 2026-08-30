from app.modules.market_intelligence.schemas import (
    MarketMetricBatchCandidate,
    MarketMetricBatchCandidateList,
    MarketMetricBatchDetail,
    MarketMetricBatchList,
    MarketMetricBatchStatus,
    MarketMetricValueKind,
)
from app.modules.market_intelligence.market_metric_product_matcher import (
    MarketMetricProductMatcher,
)
from app.repositories.market_metric_repository import MarketMetricRepository


class MarketMetricQueryService:
    """按租户查询宏观市场指标上传批次和审核结果。"""

    def __init__(
        self,
        repository: MarketMetricRepository,
        product_matcher: MarketMetricProductMatcher | None = None,
    ) -> None:
        self.repository = repository
        self.product_matcher = product_matcher

    def list_candidates(
        self,
        *,
        tenant_id: str,
        platform: str,
        market: str,
        category: str,
        keyword: str,
        limit: int = 50,
    ) -> MarketMetricBatchCandidateList:
        if self.product_matcher is None:
            raise RuntimeError("market metric product matcher is not configured")
        batches = self.repository.list_batches(
            tenant_id=tenant_id,
            status=MarketMetricBatchStatus.APPROVED,
            platform=platform,
            market=market,
            limit=limit,
        )
        return MarketMetricBatchCandidateList(
            items=[
                MarketMetricBatchCandidate(
                    batch=batch,
                    product_match=self.product_matcher.match(
                        requested_category=category,
                        requested_keyword=keyword,
                        batch=batch,
                    ),
                )
                for batch in batches
            ]
        )

    def list_batches(
        self,
        *,
        tenant_id: str,
        status: MarketMetricBatchStatus | None = None,
        platform: str | None = None,
        market: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> MarketMetricBatchList:
        return MarketMetricBatchList(
            items=self.repository.list_batches(
                tenant_id=tenant_id,
                status=status,
                platform=platform,
                market=market,
                limit=limit,
                offset=offset,
            ),
            total=self.repository.count_batches(
                tenant_id=tenant_id,
                status=status,
                platform=platform,
                market=market,
            ),
            limit=limit,
            offset=offset,
        )

    def get_batch(self, *, batch_id: str, tenant_id: str) -> MarketMetricBatchDetail:
        batch = self.repository.get_batch(batch_id, tenant_id)
        observations = self.repository.list_batch_observations(
            batch_id=batch_id,
            tenant_id=tenant_id,
        )
        return MarketMetricBatchDetail(
            batch=batch,
            direct_observations=[
                item
                for item in observations
                if item.value_kind is MarketMetricValueKind.DIRECT
            ],
            derived_observations=[
                item
                for item in observations
                if item.value_kind is MarketMetricValueKind.DERIVED
            ],
        )


__all__ = ["MarketMetricQueryService"]
