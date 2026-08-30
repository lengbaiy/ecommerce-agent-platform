from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.adapters.commerce import AdapterContext, AdapterError, AdapterResult, CommerceAdapterRegistry
from app.modules.market_intelligence.schemas import (
    AdapterCapabilities,
    AnalysisScope,
    CollectionRun,
    CollectionStatus,
    DataLevel,
    DataSourceMode,
    DataStatus,
    EvidenceReference,
    EvidenceType,
    MarketDataRequest,
    MarketMetric,
    MetricStatus,
    NormalizedProduct,
    SalesValueType,
)
from app.tools import ToolRequest
from app.tools.market_data import MarketDataTool


START_TIME = datetime(2026, 1, 1, tzinfo=UTC)
END_TIME = datetime(2026, 1, 31, 23, 59, 59, tzinfo=UTC)
FULL_MARKET_CODES = {
    "market_size",
    "gmv",
    "growth",
    "price_distribution",
    "brand_concentration",
    "product_concentration",
}
SAMPLE_CODES = {
    "sample_product_count",
    "sample_min_price",
    "sample_max_price",
    "sample_median_price",
    "sample_price_distribution",
    "sample_sales_display_distribution",
    "sample_shop_concentration",
    "sample_product_concentration",
}


class StubMarketAdapter:
    platform = "amazon"
    data_source_mode = "fixed_dataset"

    def __init__(
        self,
        *,
        supports_market_metrics: bool,
        result: AdapterResult[list[MarketMetric]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._capabilities = AdapterCapabilities(
            platform=self.platform,
            data_source_mode=self.data_source_mode,
            supports_products=True,
            supports_reviews=True,
            supports_market_metrics=supports_market_metrics,
            max_products=50,
            max_reviews_per_product=100,
            adapter_version="stub-market-v1",
            schema_version="1.0",
        )
        self.result = result
        self.error = error
        self.received_request: MarketDataRequest | None = None
        self.received_context: AdapterContext | None = None

    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    def get_market_metrics(
        self, request: MarketDataRequest, context: AdapterContext
    ) -> AdapterResult[list[MarketMetric]]:
        self.received_request = request
        self.received_context = context
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("sample fallback must not call get_market_metrics")
        return self.result


def _scope(*, product_count: int = 0) -> AnalysisScope:
    return AnalysisScope(
        market="US",
        platforms=["amazon"],
        category="portable_coffee",
        keyword="portable coffee",
        start_time=START_TIME,
        end_time=END_TIME,
        requested_product_count=product_count,
        actual_product_count=product_count,
        actual_review_count=0,
        data_source_mode=DataSourceMode.FIXED_DATASET,
    )


def _evidence(
    evidence_id: str,
    *,
    evidence_type: EvidenceType = EvidenceType.MARKET_METRIC,
    product_id: str | None = None,
    collection_run_id: str = "market-run-001",
    source_timestamp: datetime = END_TIME,
) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        data_level=DataLevel.D,
        data_source="authorized fixture",
        platform="amazon",
        product_id=product_id,
        query_range={
            "market": "US",
            "category": "portable_coffee",
            "keyword": "portable coffee",
            "start_time": START_TIME.isoformat(),
            "end_time": END_TIME.isoformat(),
        },
        source_timestamp=source_timestamp,
        ingest_timestamp=source_timestamp + timedelta(hours=1),
        tool_call_id="tool-call-001",
        collection_run_id=collection_run_id,
        snapshot_ref=f"fixture#{evidence_id}",
        sha256="a" * 64,
        data_version="1.0.0",
        sample_scope=_scope(product_count=1 if product_id else 0),
    )


def _product(
    product_id: str,
    *,
    price: str,
    sales_display: str | None,
    sales_value: int | None,
    sales_value_type: SalesValueType,
    shop_name: str | None,
    currency: str = "USD",
    platform: str = "amazon",
    market: str = "US",
    source_type: DataSourceMode = DataSourceMode.FIXED_DATASET,
    source_timestamp: datetime = START_TIME,
) -> NormalizedProduct:
    return NormalizedProduct(
        snapshot_id=f"snapshot-{product_id}",
        collection_run_id="product-run-001",
        platform=platform,
        market=market,
        product_id=product_id,
        title=f"Product {product_id}",
        brand="ExampleBrand",
        category="portable_coffee",
        price=Decimal(price),
        currency=currency,
        sales_display=sales_display,
        sales_value=sales_value,
        sales_value_type=sales_value_type,
        shop_name=shop_name,
        rating=Decimal("4.5"),
        review_count=100,
        source_ref=f"amazon:{product_id}",
        source_snapshot_ref=f"products.jsonl#{product_id}",
        source_timestamp=source_timestamp,
        ingest_timestamp=source_timestamp + timedelta(hours=1),
        source_type=source_type,
        data_status=DataStatus.VALID,
    )


def _sample_products() -> list[NormalizedProduct]:
    return [
        _product(
            "P1", price="10.00", sales_display="100 sold", sales_value=100,
            sales_value_type=SalesValueType.EXACT, shop_name="Shop A",
            source_timestamp=START_TIME,
        ),
        _product(
            "P2", price="20.00", sales_display="50 sold", sales_value=50,
            sales_value_type=SalesValueType.EXACT, shop_name="Shop A",
            source_timestamp=START_TIME + timedelta(days=1),
        ),
        _product(
            "P3", price="30.00", sales_display="200+ sold", sales_value=200,
            sales_value_type=SalesValueType.LOWER_BOUND, shop_name="Shop B",
            source_timestamp=START_TIME + timedelta(days=2),
        ),
        _product(
            "P4", price="40.00", sales_display="100-200 sold", sales_value=150,
            sales_value_type=SalesValueType.RANGE, shop_name="Shop B",
            source_timestamp=START_TIME + timedelta(days=3),
        ),
        _product(
            "P5", price="50.00", sales_display="销量未知", sales_value=None,
            sales_value_type=SalesValueType.UNKNOWN, shop_name=None,
            source_timestamp=START_TIME + timedelta(days=4),
        ),
    ]


def _product_evidence(products: list[NormalizedProduct]) -> list[EvidenceReference]:
    return [
        _evidence(
            f"evidence-{product.product_id}",
            evidence_type=EvidenceType.PRODUCT,
            product_id=product.product_id,
            collection_run_id=product.collection_run_id,
            source_timestamp=product.source_timestamp,
        )
        for product in products
    ]


def _request(**parameter_overrides: Any) -> ToolRequest:
    parameters: dict[str, Any] = {
        "schema_version": "1.0",
        "task_id": "task-001",
        "tool_call_id": "tool-call-001",
        "platform": "amazon",
        "data_source_mode": "fixed_dataset",
        "market": "US",
        "category": "portable_coffee",
        "keyword": "portable coffee",
        "start_time": START_TIME,
        "end_time": END_TIME,
    }
    parameters.update(parameter_overrides)
    return ToolRequest(
        tenant_id="tenant-001",
        user_id="user-001",
        trace_id="trace-001",
        parameters=parameters,
    )


def _collection_run() -> CollectionRun:
    return CollectionRun(
        id="market-run-001",
        task_id="task-001",
        trace_id="trace-001",
        tenant_id="tenant-001",
        keyword="portable coffee",
        requested_count=0,
        actual_count=0,
        status=CollectionStatus.COMPLETED,
        adapter_version="stub-market-v1",
        started_at=START_TIME,
        finished_at=END_TIME,
    )


def _available_metric(
    metric_code: str,
    value: Decimal | int | dict[str, Any],
    unit: str,
    *,
    status: MetricStatus = MetricStatus.AVAILABLE,
) -> MarketMetric:
    return MarketMetric(
        metric_code=metric_code,
        value=value,
        unit=unit,
        status=status,
        scope=_scope(),
        methodology=f"Authorized aggregate methodology for {metric_code}.",
        evidence_ids=["market-evidence-001"],
        source_timestamp=END_TIME,
    )


def _complete_market_metrics() -> list[MarketMetric]:
    return [
        _available_metric("market_size", 120000, "product_count"),
        _available_metric("gmv", Decimal("9800000.50"), "USD"),
        _available_metric("growth", Decimal("0.1250"), "ratio"),
        _available_metric(
            "price_distribution",
            {"bins": [{"lower": "0", "upper": "50", "count": 3000}]},
            "USD",
        ),
        _available_metric("brand_concentration", Decimal("0.4200"), "ratio"),
        _available_metric("product_concentration", Decimal("0.1800"), "ratio"),
    ]


def _tool_with_adapter(adapter: StubMarketAdapter) -> MarketDataTool:
    return MarketDataTool(registry=CommerceAdapterRegistry([adapter]))


def _metrics_by_code(response_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {metric["metric_code"]: metric for metric in response_data["metrics"]}


def _fallback_tool() -> tuple[MarketDataTool, StubMarketAdapter]:
    adapter = StubMarketAdapter(supports_market_metrics=False)
    return _tool_with_adapter(adapter), adapter


def test_complete_aggregate_metrics_preserve_request_context_and_output_contract() -> None:
    evidence = _evidence("market-evidence-001")
    result = AdapterResult(
        data=_complete_market_metrics(),
        run=_collection_run(),
        evidence_refs=[evidence],
        warnings=["authorized aggregate snapshot"],
        degraded=False,
    )
    adapter = StubMarketAdapter(supports_market_metrics=True, result=result)

    response = _tool_with_adapter(adapter).execute(_request())

    assert response.success is True
    assert response.error is None
    assert response.degraded is False
    assert response.source == "amazon:fixed_dataset"
    assert response.trace_id == "trace-001"
    assert response.data == {
        "schema_version": "1.0",
        "collection_run_id": "market-run-001",
        "status": "COMPLETED",
        "stop_reason": None,
        "adapter_version": "stub-market-v1",
        "metrics": [metric.model_dump(mode="json") for metric in result.data],
        "evidence_refs": [evidence.model_dump(mode="json")],
        "warnings": ["authorized aggregate snapshot"],
    }
    assert adapter.received_request == MarketDataRequest(
        platform="amazon",
        market="US",
        category="portable_coffee",
        keyword="portable coffee",
        start_time=START_TIME,
        end_time=END_TIME,
    )
    assert adapter.received_context == AdapterContext(
        tenant_id="tenant-001",
        user_id="user-001",
        trace_id="trace-001",
        task_id="task-001",
        tool_call_id="tool-call-001",
    )
    for metric in response.data["metrics"]:
        assert {"value", "unit", "status", "scope", "methodology", "evidence_ids"} <= metric.keys()
        assert metric["source_timestamp"] == END_TIME.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("degradation_source", ["missing", "stale", "adapter"])
def test_incomplete_stale_or_adapter_degraded_metrics_mark_the_response_degraded(
    degradation_source: str,
) -> None:
    metrics = _complete_market_metrics()
    if degradation_source == "missing":
        metrics = [metric for metric in metrics if metric.metric_code != "growth"]
    elif degradation_source == "stale":
        metrics = [
            _available_metric(
                "growth", Decimal("0.1250"), "ratio", status=MetricStatus.STALE
            )
            if metric.metric_code == "growth"
            else metric
            for metric in metrics
        ]
    result = AdapterResult(
        data=metrics,
        run=_collection_run(),
        evidence_refs=[_evidence("market-evidence-001")],
        degraded=degradation_source == "adapter",
    )

    response = _tool_with_adapter(
        StubMarketAdapter(supports_market_metrics=True, result=result)
    ).execute(_request())

    assert response.success is True
    assert response.degraded is True


def test_sample_fallback_returns_all_required_metrics_with_scope_and_evidence() -> None:
    products = _sample_products()
    evidence_refs = _product_evidence(products)
    tool, adapter = _fallback_tool()

    response = tool.execute(_request(products=products, evidence_refs=evidence_refs))

    assert response.success is True
    assert response.error is None
    assert response.degraded is True
    assert response.source == "amazon:fixed_dataset"
    assert response.data["status"] == "COMPLETED"
    assert response.data["stop_reason"] == "AGGREGATE_MARKET_DATA_MISSING"
    assert response.data["adapter_version"] == "stub-market-v1"
    assert response.data["source_collection_run_ids"] == ["product-run-001"]
    assert response.data["warnings"] == [
        "Aggregate market data is unavailable. Returned metrics describe only "
        "the supplied product sample."
    ]
    assert adapter.received_request is None
    metrics = _metrics_by_code(response.data)
    assert set(metrics) == FULL_MARKET_CODES | SAMPLE_CODES
    assert {item["evidence_id"] for item in response.data["evidence_refs"]} == {
        f"evidence-P{index}" for index in range(1, 6)
    }
    for metric in metrics.values():
        assert {"value", "unit", "status", "scope", "methodology", "evidence_ids"} <= metric.keys()
        assert metric["scope"]["market"] == "US"
        assert metric["scope"]["platforms"] == ["amazon"]
        assert metric["scope"]["keyword"] == "portable coffee"
        assert metric["scope"]["actual_product_count"] == 5
        assert metric["scope"]["start_time"] == START_TIME.isoformat().replace("+00:00", "Z")
        expected_end = (START_TIME + timedelta(days=4)).isoformat().replace("+00:00", "Z")
        assert metric["scope"]["end_time"] == expected_end
    for metric_code in FULL_MARKET_CODES:
        metric = metrics[metric_code]
        assert metric["value"] is None
        assert metric["status"] == "unavailable"
        assert metric.get("reason_code") == "AGGREGATE_MARKET_DATA_MISSING"
        assert "methodology_version=sample-market-v1" in metric["methodology"]
    assert all(metrics[code]["status"] in {"available", "partial"} for code in SAMPLE_CODES)


def test_sample_price_statistics_use_decimal_fixed_bins_and_are_repeatable() -> None:
    products = _sample_products()
    evidence_refs = _product_evidence(products)
    tool, _ = _fallback_tool()

    first = tool.execute(_request(products=products, evidence_refs=evidence_refs))
    second = tool.execute(_request(products=products, evidence_refs=evidence_refs))

    first_metrics = _metrics_by_code(first.data)
    second_metrics = _metrics_by_code(second.data)
    assert first_metrics == second_metrics
    assert first_metrics["sample_product_count"]["value"] == 5
    assert first_metrics["sample_min_price"]["value"] == "10.00"
    assert first_metrics["sample_max_price"]["value"] == "50.00"
    assert first_metrics["sample_median_price"]["value"] == "30.00"
    distribution = first_metrics["sample_price_distribution"]
    assert distribution["value"] == {
        "observed_count": 5,
        "currency": "USD",
        "binning_algorithm": "four_equal_width_bins",
        "bins": [
            {"lower": "10.0000", "upper": "20.0000", "upper_inclusive": False, "count": 1},
            {"lower": "20.0000", "upper": "30.0000", "upper_inclusive": False, "count": 1},
            {"lower": "30.0000", "upper": "40.0000", "upper_inclusive": False, "count": 1},
            {"lower": "40.0000", "upper": "50.0000", "upper_inclusive": True, "count": 2},
        ],
    }
    assert "methodology_version=sample-market-v1" in distribution["methodology"]


def test_sample_sales_semantics_preserve_display_and_exclude_non_exact_sales() -> None:
    products = _sample_products()
    tool, _ = _fallback_tool()

    response = tool.execute(_request(products=products, evidence_refs=_product_evidence(products)))

    metrics = _metrics_by_code(response.data)
    assert metrics["sample_sales_display_distribution"]["value"] == [
        {"sales_value_type": "exact", "sales_display": "100 sold", "product_count": 1},
        {"sales_value_type": "exact", "sales_display": "50 sold", "product_count": 1},
        {"sales_value_type": "lower_bound", "sales_display": "200+ sold", "product_count": 1},
        {"sales_value_type": "range", "sales_display": "100-200 sold", "product_count": 1},
        {"sales_value_type": "unknown", "sales_display": "销量未知", "product_count": 1},
    ]
    concentration = metrics["sample_product_concentration"]
    assert concentration["status"] == "partial"
    assert concentration["value"] == {
        "exact_sales_product_count": 2,
        "total_product_count": 5,
        "exact_sales_coverage_ratio": "0.4000",
        "exact_sales_total": 150,
        "top1_share": "0.6667",
        "top3_share": "1.0000",
        "top_products": [
            {"product_id": "P1", "sales_value": 100, "share": "0.6667"},
            {"product_id": "P2", "sales_value": 50, "share": "0.3333"},
        ],
    }
    assert "lower_bound, range, and unknown values are excluded" in concentration["methodology"]


def test_sample_shop_concentration_uses_only_products_with_shop_names() -> None:
    products = _sample_products()
    tool, _ = _fallback_tool()

    response = tool.execute(_request(products=products, evidence_refs=_product_evidence(products)))

    concentration = _metrics_by_code(response.data)["sample_shop_concentration"]
    assert concentration["status"] == "partial"
    assert concentration["value"] == {
        "observed_product_count": 4,
        "total_product_count": 5,
        "coverage_ratio": "0.8000",
        "distinct_shop_count": 2,
        "top1_share": "0.5000",
        "top3_share": "1.0000",
        "top_shops": [
            {"shop_name": "Shop A", "product_count": 2, "share": "0.5000"},
            {"shop_name": "Shop B", "product_count": 2, "share": "0.5000"},
        ],
    }


def test_mixed_currencies_mark_price_metrics_conflict_without_hiding_other_sample_metrics() -> None:
    products = _sample_products()
    products[4] = products[4].model_copy(update={"currency": "EUR"})
    tool, _ = _fallback_tool()

    response = tool.execute(_request(products=products, evidence_refs=_product_evidence(products)))

    metrics = _metrics_by_code(response.data)
    price_codes = {
        "sample_min_price",
        "sample_max_price",
        "sample_median_price",
        "sample_price_distribution",
    }
    for metric_code in price_codes:
        assert metrics[metric_code]["status"] == "conflict"
        assert metrics[metric_code]["value"] is None
        assert metrics[metric_code]["unit"] is None
        assert "PRICE_CURRENCY_CONFLICT" in metrics[metric_code]["methodology"]
    assert metrics["sample_product_count"]["status"] == "available"
    assert metrics["sample_sales_display_distribution"]["status"] == "available"


def test_empty_sample_returns_market_and_sample_metrics_as_unavailable() -> None:
    tool, _ = _fallback_tool()

    response = tool.execute(_request(products=[], evidence_refs=[]))

    assert response.success is True
    assert response.degraded is True
    assert response.data["source_collection_run_ids"] == []
    assert response.data["evidence_refs"] == []
    assert response.data["warnings"] == [
        "No product sample was provided. Market and sample metrics are unavailable."
    ]
    metrics = _metrics_by_code(response.data)
    assert set(metrics) == FULL_MARKET_CODES | SAMPLE_CODES
    assert all(metric["status"] == "unavailable" for metric in metrics.values())
    assert all(metric["value"] is None for metric in metrics.values())
    assert all(metric["scope"]["actual_product_count"] == 0 for metric in metrics.values())
    assert all(
        metric["scope"]["start_time"] == START_TIME.isoformat().replace("+00:00", "Z")
        for metric in metrics.values()
    )
    assert all(
        metric["scope"]["end_time"] == END_TIME.isoformat().replace("+00:00", "Z")
        for metric in metrics.values()
    )


@pytest.mark.parametrize(
    ("products", "evidence_refs", "message_fragment"),
    [
        (_sample_products()[:1], [], "product evidence is required for product_id: P1"),
        (
            [_sample_products()[0], _sample_products()[0]],
            _product_evidence([_sample_products()[0]]),
            "products must not contain duplicate product_id",
        ),
        (
            [_sample_products()[0].model_copy(update={"platform": "ebay"})],
            _product_evidence([_sample_products()[0]]),
            "does not match platform amazon",
        ),
        (
            [_sample_products()[0].model_copy(update={"market": "CA"})],
            _product_evidence([_sample_products()[0]]),
            "does not match market US",
        ),
        (
            [_sample_products()[0].model_copy(update={"source_type": DataSourceMode.OFFICIAL_API})],
            _product_evidence([_sample_products()[0]]),
            "does not match data_source_mode fixed_dataset",
        ),
    ],
)
def test_sample_fallback_rejects_untraceable_or_out_of_scope_products(
    products: list[NormalizedProduct],
    evidence_refs: list[EvidenceReference],
    message_fragment: str,
) -> None:
    tool, _ = _fallback_tool()

    response = tool.execute(_request(products=products, evidence_refs=evidence_refs))

    assert response.success is False
    assert response.degraded is False
    assert response.error is not None
    assert response.error.code == "INVALID_ARGUMENT"
    assert message_fragment in response.error.message


@pytest.mark.parametrize(
    "tool_request",
    [
        ToolRequest(
            tenant_id=" ", user_id="user-001", trace_id="trace-001",
            parameters=_request().parameters,
        ),
        _request(keyword=""),
        _request(start_time=END_TIME, end_time=START_TIME),
    ],
)
def test_invalid_identity_or_parameters_return_stable_invalid_argument(
    tool_request: ToolRequest,
) -> None:
    response = MarketDataTool(registry=CommerceAdapterRegistry()).execute(tool_request)

    assert response.success is False
    assert response.degraded is False
    assert response.error is not None
    assert response.error.code == "INVALID_ARGUMENT"
    assert response.error.retryable is False
    assert response.data == {"schema_version": "1.0"}


def test_unsupported_schema_version_returns_stable_error() -> None:
    response = MarketDataTool(registry=CommerceAdapterRegistry()).execute(
        _request(schema_version="2.0")
    )

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "SCHEMA_VERSION_UNSUPPORTED"
    assert response.error.retryable is False
    assert response.source == "amazon:fixed_dataset"
    assert response.data == {"schema_version": "1.0"}


def test_missing_adapter_returns_unsupported_data_source() -> None:
    response = MarketDataTool(registry=CommerceAdapterRegistry()).execute(_request())

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "UNSUPPORTED_DATA_SOURCE"
    assert response.error.retryable is False
    assert response.source == "amazon:fixed_dataset"


def test_adapter_error_preserves_code_retryability_and_collection_run() -> None:
    adapter = StubMarketAdapter(
        supports_market_metrics=True,
        error=AdapterError(
            "MARKET_DATA_TIMEOUT",
            "authorized source timed out",
            retryable=True,
            collection_run_id="market-run-timeout",
        ),
    )

    response = _tool_with_adapter(adapter).execute(_request())

    assert response.success is False
    assert response.degraded is False
    assert response.error is not None
    assert response.error.code == "MARKET_DATA_TIMEOUT"
    assert response.error.message == "authorized source timed out"
    assert response.error.retryable is True
    assert response.data == {
        "schema_version": "1.0",
        "collection_run_id": "market-run-timeout",
    }


def test_unexpected_adapter_failure_returns_retryable_internal_error() -> None:
    adapter = StubMarketAdapter(
        supports_market_metrics=True,
        error=RuntimeError("sensitive adapter detail"),
    )

    response = _tool_with_adapter(adapter).execute(_request())

    assert response.success is False
    assert response.degraded is False
    assert response.error is not None
    assert response.error.code == "MARKET_DATA_INTERNAL_ERROR"
    assert response.error.retryable is True
    assert "sensitive adapter detail" not in response.error.message
    assert response.data == {"schema_version": "1.0"}
