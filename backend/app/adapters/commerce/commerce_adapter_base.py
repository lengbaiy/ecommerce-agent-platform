from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from app.modules.market_intelligence.schemas import (
    AdapterCapabilities,
    CollectionRun,
    EvidenceReference,
    NormalizedProduct,
    NormalizedReview,
    MarketMetric,
    ProductSearchRequest,
    ReviewSearchRequest,
    MarketDataRequest, 
)


class AdapterError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        collection_run_id: str | None = None,
        run: CollectionRun | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.collection_run_id = collection_run_id
        self.run = run


@dataclass(frozen=True)
class AdapterContext:
    tenant_id: str
    user_id: str
    trace_id: str
    task_id: str
    tool_call_id: str


T = TypeVar("T")


@dataclass(frozen=True)
class AdapterResult(Generic[T]):
    data: T
    run: CollectionRun
    evidence_refs: list[EvidenceReference] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False


class CommerceAdapter(Protocol):
    platform: str
    data_source_mode: str

    def capabilities(self) -> AdapterCapabilities: ...

    def search_products(
        self,
        request: ProductSearchRequest,
        context: AdapterContext,
    ) -> AdapterResult[list[NormalizedProduct]]: ...

    def search_reviews(
        self,
        request: ReviewSearchRequest,
        context: AdapterContext,
    ) -> AdapterResult[list[NormalizedReview]]: ...


    def get_market_metrics(
        self,
        request: MarketDataRequest,
        context: AdapterContext,
    ) -> AdapterResult[list[MarketMetric]]: ...


CollectionContext = AdapterContext
CollectionError = AdapterError
