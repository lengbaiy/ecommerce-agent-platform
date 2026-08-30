import json
from dataclasses import replace
from decimal import Decimal
from os import getenv
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.market_intelligence.composition import (
    build_commerce_adapter_registry,
    build_product_search_tool,
    build_repository,
    build_review_insight_tool,
)
from app.core.config import Settings
from app.db.models import Base
from app.db.session import build_engine
from app.tools import ToolRequest
from app.tools.support.llm_review_analyzer import LLMReviewAnalyzer


pytestmark = [
    pytest.mark.integration,
    pytest.mark.llm,
    pytest.mark.skipif(
        getenv("RUN_LLM_TESTS", "").strip() != "1",
        reason="Set RUN_LLM_TESTS=1 to run the real LLM integration test.",
    ),
]

DATASET_ID = "amazon_us_portable_coffee_v1"
PLATFORM = "amazon"
DATA_SOURCE_MODE = "fixed_dataset"
TENANT_ID = "review-insight-llm-test-tenant"
USER_ID = "review-insight-llm-test-user"
PRODUCT_SEARCH_LIMIT = 5
REVIEW_LIMIT_PER_PRODUCT = 2


@pytest.fixture
def test_settings() -> Settings:
    settings = Settings()

    return replace(
        settings,
        environment="test",
    )

@pytest.fixture
def session_factory(tmp_path: Path):
    """Use an isolated SQLite database so the test does not touch dev data."""
    database_path = tmp_path / "review-insight-llm.db"
    engine = build_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )

    try:
        yield factory
    finally:
        engine.dispose()


def _load_dataset_scope(registry) -> dict[str, str]:
    """
    Read the actual fixed-dataset manifest instead of hard-coding scope values.

    DatasetAdapter selects datasets by exact platform/market/category/keyword
    matching, so using the manifest keeps this test aligned with the fixture.
    """
    adapter = registry.get(PLATFORM, DATA_SOURCE_MODE)
    dataset_dir = Path(adapter.dataset_root) / DATASET_ID
    manifest_path = dataset_dir / "manifest.json"

    assert manifest_path.is_file(), (
        f"Fixed dataset manifest not found: {manifest_path}. "
        "Ensure amazon_us_portable_coffee_v1 is present under the configured "
        "market intelligence dataset root."
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for field_name in ("market", "category", "keyword"):
        assert manifest.get(field_name), (
            f"manifest.json must contain non-empty {field_name!r}"
        )

    return {
        "market": manifest["market"],
        "category": manifest["category"],
        "keyword": manifest["keyword"],
    }


def _pick_product_id(products: list[dict]) -> str:
    """Prefer a product whose metadata says it has reviews."""
    assert products, "ProductSearchTool returned no products"

    def review_count(product: dict) -> int:
        value = product.get("review_count")
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    product = max(products, key=review_count)
    product_id = product.get("product_id")
    assert product_id, "Selected product does not contain product_id"
    return str(product_id)


def test_review_insight_tool_runs_complete_flow_with_real_llm(
    test_settings,
    session_factory,
) -> None:
    """
    End-to-end integration test for ReviewInsightTool.

    Covered path:
      composition
        -> DatasetAdapter
        -> review persistence
        -> LLMReviewAnalyzer
        -> real configured StructuredLLMClient
        -> ReviewInsight
        -> ToolResponse

    This test intentionally does not assert exact theme wording because real LLM
    labels are non-deterministic. It asserts the stable public contract instead.
    """
    registry = build_commerce_adapter_registry(test_settings)
    repository = build_repository(session_factory)

    product_search_tool = build_product_search_tool(
        registry,
        repository,
        test_settings,
    )
    review_insight_tool = build_review_insight_tool(
        registry,
        repository,
        test_settings,
    )

    # Verify composition really wired the LLM analyzer rather than the
    # precomputed fallback analyzer.
    assert isinstance(review_insight_tool.analyzer, LLMReviewAnalyzer)
    assert (
        review_insight_tool.analyzer.client.provider.casefold()
        == test_settings.llm_provider.casefold()
    )

    scope = _load_dataset_scope(registry)

    product_search_limit = min(
        PRODUCT_SEARCH_LIMIT,
        int(test_settings.market_max_product_limit),
    )
    review_limit_per_product = min(
        REVIEW_LIMIT_PER_PRODUCT,
        int(test_settings.market_max_reviews_per_product),
    )
    assert product_search_limit >= 1
    assert review_limit_per_product >= 1

    # First discover a real product_id through the public ProductSearchTool.
    product_response = product_search_tool.execute(
        ToolRequest(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            trace_id=f"product-trace-{uuid4()}",
            parameters={
                "schema_version": "1.0",
                "task_id": str(uuid4()),
                "tool_call_id": str(uuid4()),
                "platform": PLATFORM,
                "data_source_mode": DATA_SOURCE_MODE,
                **scope,
                "product_limit": product_search_limit,
                "sort_by": "default",
            },
        )
    )

    assert product_response.success is True, product_response.model_dump_json(indent=2)
    assert product_response.error is None
    assert product_response.source == f"{PLATFORM}:{DATA_SOURCE_MODE}"

    products = product_response.data["products"]
    product_id = _pick_product_id(products)

    # Now execute ReviewInsightTool. This path performs the real LLM request.
    review_trace_id = f"review-trace-{uuid4()}"
    review_tool_call_id = str(uuid4())

    response = review_insight_tool.execute(
        ToolRequest(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            trace_id=review_trace_id,
            parameters={
                "schema_version": "1.0",
                "task_id": str(uuid4()),
                "tool_call_id": review_tool_call_id,
                "platform": PLATFORM,
                "data_source_mode": DATA_SOURCE_MODE,
                **scope,
                "product_ids": [product_id],
                "review_limit_per_product": review_limit_per_product,
            },
        )
    )

    # Print the full response when running pytest with -s. This is useful while
    # validating a real provider integration.
    print(response.model_dump_json(indent=2))

    assert response.success is True, response.model_dump_json(indent=2)
    assert response.error is None
    assert response.source == f"{PLATFORM}:{DATA_SOURCE_MODE}"
    assert response.trace_id == review_trace_id

    data = response.data
    assert data["schema_version"] == "1.0"
    assert data["collection_run_id"]
    assert data["status"] in {"COMPLETED", "PARTIAL", "completed", "partial"}

    reviews = data["reviews"]
    evidence_refs = data["evidence_refs"]
    insight = data["review_insight"]

    assert 1 <= len(reviews) <= review_limit_per_product
    assert len(evidence_refs) == len(reviews)

    # Every returned review must be evidence-backed.
    review_ids = {review["review_id"] for review in reviews}
    evidence_review_ids = {
        evidence["review_id"]
        for evidence in evidence_refs
    }
    assert review_ids == evidence_review_ids

    for evidence in evidence_refs:
        assert evidence["collection_run_id"] == data["collection_run_id"]
        assert evidence["tool_call_id"] == review_tool_call_id
        assert evidence["product_id"] == product_id

    # LLMReviewAnalyzer should analyze every collected review.
    sentiment = insight["sentiment_distribution"]
    assert sentiment["total_count"] == len(reviews)
    assert sentiment["analyzed_count"] == len(reviews)
    assert Decimal(str(sentiment["coverage_ratio"])) == Decimal("1")

    sentiment_count = sum(
        int(sentiment[f"{name}_count"])
        for name in ("positive", "neutral", "negative")
    )
    assert sentiment_count == len(reviews)

    # Do not assert exact labels from a real LLM. Assert their stable shape.
    assert isinstance(insight["themes"], list)
    assert isinstance(insight["pain_points"], list)
    assert isinstance(insight["unmet_needs"], list)

    assert str(insight["status"]).casefold() in {
        "available",
        "stale",
    }

    assert insight["representative_review_ids"]
    assert set(insight["representative_review_ids"]).issubset(review_ids)
    assert len(insight["representative_review_ids"]) <= 5

    evidence_ids = {
        evidence["evidence_id"]
        for evidence in evidence_refs
    }
    assert set(insight["evidence_ids"]) == evidence_ids
    assert len(insight["evidence_ids"]) == len(evidence_ids)

    sample_scope = insight["sample_scope"]
    assert sample_scope["actual_review_count"] == len(reviews)
    assert sample_scope["actual_product_count"] == 1
    assert sample_scope["platforms"] == [PLATFORM]

    semantic_group_count = sum(
        len(insight[group_name])
        for group_name in ("themes", "pain_points", "unmet_needs")
    )
    assert semantic_group_count >= 1

    # Any semantic group produced by the LLM must remain traceable to reviews
    # and evidence returned by this Tool call.
    for group_name in ("themes", "pain_points", "unmet_needs"):
        for item in insight[group_name]:
            assert item["theme"].strip()
            assert 1 <= item["mention_count"] <= len(reviews)
            mention_ratio = Decimal(str(item["mention_ratio"]))
            assert Decimal("0") < mention_ratio <= Decimal("1")
            assert mention_ratio == (
                Decimal(item["mention_count"])
                / Decimal(len(reviews))
            )
            assert set(item["representative_review_ids"]).issubset(review_ids)
            assert 1 <= len(item["representative_review_ids"]) <= 3
            assert set(item["evidence_ids"]).issubset(evidence_ids)

    if str(insight["status"]).casefold() == "stale":
        assert response.degraded is True
