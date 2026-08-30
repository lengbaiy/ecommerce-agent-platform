from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

# Application composition requires an LLM configuration at import time. The
# test graph below replaces both external LLM boundaries and never uses it.
os.environ.setdefault("LLM_PROVIDER", "bailian")
os.environ.setdefault("LLM_API_KEY", "integration-test-placeholder")
os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:9/v1")
os.environ.setdefault("LLM_MODEL", "integration-test-placeholder")

from app.adapters.commerce import CommerceAdapterRegistry
from app.adapters.commerce.dataset import DatasetAdapter, DatasetCatalog
from app.adapters.commerce.dataset.dataset_adapter import DEFAULT_DATASET_ROOT
from app.agents.market_intelligence_reporter import ReportSynthesisOutput
from app.api.dependencies import get_task_preview_service, get_task_service
from app.core.security import Principal, get_current_principal, permissions_for_roles
from app.db.models import (
    AgentStepRecord,
    AgentTaskRecord,
    Base,
    CollectionRunRecord,
    EvidenceReferenceRecord,
    GraphCheckpointRecord,
    MarketIntelligenceReportRecord,
    ProductSnapshotRecord,
    ReviewSnapshotRecord,
    ToolCallRecord,
)
from app.domain import TaskPreviewRequest, TaskStatus
from app.graph.market_intelligence_graph import MarketIntelligenceGraph
from app.main import app
from app.modules.market_intelligence.dataset_availability import DatasetAvailability
from app.modules.market_intelligence.input_extractor import MarketIntelligenceInputExtractor
from app.modules.market_intelligence.persistence import (
    SQLAlchemyMarketCancellationPort,
    SQLAlchemyMarketCheckpointPort,
    SQLAlchemyStepExecutionPort,
    SQLAlchemyToolExecutionPort,
)
from app.modules.market_intelligence.schemas import (
    CollectionOptions,
    EntryAssessment,
    EntryDecision,
    MarketIntelligenceBusinessContext,
    MetricStatus,
    ProfitCalculatorParameters,
    ReviewInsight,
    Statement,
)
from app.modules.market_intelligence.task_executor import MarketIntelligenceTaskExecutor
from app.modules.task_center import TaskExecutorDispatcher, TaskInputDispatcher
from app.repositories import SQLAlchemyTaskRepository
from app.repositories.collection_repository import SQLAlchemyCollectionRepository
from app.services import MarketIntelligenceService, TaskPreviewService, TaskService
from app.tools.market_data import MarketDataTool
from app.tools.product_search import ProductSearchTool
from app.tools.profit_calculator import ProfitCalculatorTool
from app.tools.review_insight import ReviewInsightTool


class AvailableReviewAnalyzer:
    """Keeps database and dataset behavior real while replacing external LLM I/O."""

    def analyze(self, *, reviews, evidence_refs, sample_scope) -> ReviewInsight:
        return ReviewInsight(
            status=MetricStatus.AVAILABLE,
            sample_scope=sample_scope,
            sentiment_distribution={
                "total_count": len(reviews),
                "analyzed_count": len(reviews),
            },
            representative_review_ids=[review.review_id for review in reviews[:5]],
            evidence_ids=[evidence.evidence_id for evidence in evidence_refs],
        )


class DeterministicReportSynthesizer:
    """Produces a valid report from Graph evidence without an external provider."""

    def synthesize(self, state) -> ReportSynthesisOutput:
        evidence_id = state["evidence_refs"][0].evidence_id
        return ReportSynthesisOutput(
            entry_assessment=EntryAssessment(
                decision=EntryDecision.GO,
                summary="The fixed dataset supports a market-entry assessment.",
                evidence_ids=[evidence_id],
            ),
            facts=[
                Statement(
                    statement_id="fact-fixed-dataset-covered",
                    text="The requested product is covered by the fixed dataset.",
                    confidence=Decimal("0.95"),
                    evidence_ids=[evidence_id],
                )
            ],
            suggested_actions=[
                Statement(
                    statement_id="action-review-competitors",
                    text="Review the leading competitors before market entry.",
                    confidence=Decimal("0.85"),
                    evidence_ids=[evidence_id],
                )
            ],
        )


@dataclass(frozen=True)
class RuntimeHarness:
    session_factory: sessionmaker[Session]
    task_repository: SQLAlchemyTaskRepository
    task_service: TaskService
    preview_service: TaskPreviewService
    checkpoint_port: SQLAlchemyMarketCheckpointPort
    client: TestClient


def _principal() -> Principal:
    roles = frozenset({"operator", "approver"})
    return Principal(
        tenant_id="tenant-e2e",
        user_id="user-e2e",
        username="user-e2e",
        roles=roles,
        permissions=permissions_for_roles(roles),
    )


@pytest.fixture
def runtime(tmp_path) -> RuntimeHarness:
    database_path = tmp_path / "market-intelligence-e2e.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )

    dataset_registry = DatasetCatalog(DEFAULT_DATASET_ROOT).load()
    dataset_ids = {entry.manifest.dataset_id for entry in dataset_registry.all()}
    dataset_adapter = DatasetAdapter(
        platform="amazon",
        dataset_registry=dataset_registry,
        public_dataset_ids=dataset_ids,
        max_products=10,
        max_reviews_per_product=10,
    )
    commerce_registry = CommerceAdapterRegistry([dataset_adapter])
    collection_repository = SQLAlchemyCollectionRepository(session_factory)

    cancellation_port = SQLAlchemyMarketCancellationPort(
        session_factory,
        lease_seconds=300,
    )
    checkpoint_port = SQLAlchemyMarketCheckpointPort(session_factory)
    graph = MarketIntelligenceGraph(
        product_search_tool=ProductSearchTool(
            adapter_registry=commerce_registry,
            repository=collection_repository,
            max_product_limit=10,
        ),
        market_data_tool=MarketDataTool(commerce_registry),
        review_insight_tool=ReviewInsightTool(
            adapter_registry=commerce_registry,
            repository=collection_repository,
            analyzer=AvailableReviewAnalyzer(),
            max_reviews_per_product=10,
        ),
        profit_calculator_tool=ProfitCalculatorTool(),
        report_synthesizer=DeterministicReportSynthesizer(),
        cancellation_port=cancellation_port,
        checkpoint_port=checkpoint_port,
        tool_execution_port=SQLAlchemyToolExecutionPort(session_factory),
        step_execution_port=SQLAlchemyStepExecutionPort(session_factory),
    )

    extractor = MarketIntelligenceInputExtractor(
        DatasetAvailability(dataset_registry)
    )
    input_dispatcher = TaskInputDispatcher({"market_entry": extractor})
    task_repository = SQLAlchemyTaskRepository(session_factory)
    task_service = TaskService(
        repository=task_repository,
        execution_mode="worker",
        input_dispatcher=input_dispatcher,
        executor_dispatcher=TaskExecutorDispatcher(
            {
                "market_entry": MarketIntelligenceTaskExecutor(
                    MarketIntelligenceService(graph)
                )
            }
        ),
        worker_id="worker-e2e",
        lease_seconds=300,
    )
    preview_service = TaskPreviewService(input_dispatcher)

    app.dependency_overrides[get_current_principal] = _principal
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_task_preview_service] = lambda: preview_service
    client = TestClient(app)
    try:
        yield RuntimeHarness(
            session_factory=session_factory,
            task_repository=task_repository,
            task_service=task_service,
            preview_service=preview_service,
            checkpoint_port=checkpoint_port,
            client=client,
        )
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()


def _preview(runtime: RuntimeHarness) -> dict:
    response = runtime.client.post(
        "/api/v1/agent/tasks/preview",
        json={
            "intent": "market_entry",
            "user_query": "Analyze portable coffee maker opportunities on Amazon US.",
        },
    )
    assert response.status_code == 200
    preview = response.json()
    assert preview["missing_fields"] == []
    assert preview["normalized_input"]["keyword"] == "portable coffee maker"
    assert any(match["supported"] for match in preview["dataset_matches"])
    return preview


def _task_payload(preview: dict, *, include_profit: bool) -> dict:
    request = dict(preview["normalized_input"])
    request["collection"] = CollectionOptions(
        product_limit=1,
        review_limit_per_product=1,
    ).model_dump(mode="json")
    request["profit_constraints"] = (
        ProfitCalculatorParameters(
            price="99.00",
            product_cost="35.00",
            platform_fee="14.00",
            logistics_cost="10.00",
            advertising_cost="8.00",
            minimum_margin="0.20",
            currency="USD",
        ).model_dump(mode="json")
        if include_profit
        else None
    )
    business_context = MarketIntelligenceBusinessContext(
        market_intelligence_request=request
    )
    return {
        "user_query": "Analyze portable coffee maker opportunities on Amazon US.",
        "intent": "market_entry",
        "business_context": business_context.model_dump(mode="json"),
        "constraints": {},
    }


def _create_pending_task(
    runtime: RuntimeHarness,
    *,
    include_profit: bool,
) -> dict:
    created = runtime.client.post(
        "/api/v1/agent/tasks",
        json=_task_payload(_preview(runtime), include_profit=include_profit),
    )
    assert created.status_code == 201
    task = created.json()
    assert task["status"] == TaskStatus.PENDING.value
    return task


@pytest.mark.integration
def test_market_opportunity_flow_persists_complete_report_structure_and_progress(
    runtime: RuntimeHarness,
) -> None:
    created = _create_pending_task(runtime, include_profit=True)

    executed = runtime.task_service.run_next()

    assert executed is not None
    assert str(executed.id) == created["id"]
    assert executed.status is TaskStatus.DEGRADED
    assert executed.completed_at is not None
    assert executed.result_hash is not None

    fetched = runtime.client.get(f"/api/v1/agent/tasks/{created['id']}")
    assert fetched.status_code == 200
    task = fetched.json()
    report = task["result"]["payload"]["market_intelligence_report"]
    assert task["status"] == TaskStatus.DEGRADED.value
    assert report["status"] == TaskStatus.DEGRADED.value
    assert report["task_id"] == created["id"]
    assert report["competitor_matrix"]
    assert report["review_insights"]["evidence_ids"]
    assert report["profit_analysis"]["status"] == "available"
    assert report["evidence_refs"]
    assert report["data_limitations"]

    events = runtime.client.get(f"/api/v1/agent/tasks/{created['id']}/events")
    assert events.status_code == 200
    assert "event: task.degraded" in events.text

    with runtime.session_factory() as session:
        assert session.scalar(
            select(func.count()).select_from(ProductSnapshotRecord)
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(ReviewSnapshotRecord)
        ) > 0
        assert session.scalar(
            select(func.count()).select_from(EvidenceReferenceRecord)
        ) > 0
        assert session.scalar(
            select(func.count()).select_from(CollectionRunRecord)
        ) == 2
        assert session.scalar(
            select(func.count()).select_from(AgentStepRecord)
        ) == 9
        assert session.scalar(
            select(func.count()).select_from(GraphCheckpointRecord)
        ) == 9
        assert session.scalar(
            select(func.count()).select_from(ToolCallRecord)
        ) == 4
        saved_report = session.scalar(
            select(MarketIntelligenceReportRecord).where(
                MarketIntelligenceReportRecord.task_id == created["id"]
            )
        )
        assert saved_report is not None
        assert saved_report.status == TaskStatus.DEGRADED.value
        assert saved_report.report_hash == task["result_hash"]
        assert saved_report.report_payload == report

    checkpoint = runtime.checkpoint_port.load(created["id"])
    assert checkpoint is not None
    assert checkpoint["final_report"] is not None
    assert checkpoint["final_report"].report_id == report["report_id"]


@pytest.mark.integration
def test_missing_profit_input_completes_as_degraded_and_persists_limitations(
    runtime: RuntimeHarness,
) -> None:
    created = _create_pending_task(runtime, include_profit=False)

    executed = runtime.task_service.run_next()

    assert executed is not None
    assert executed.status is TaskStatus.DEGRADED
    response = runtime.client.get(f"/api/v1/agent/tasks/{created['id']}")
    report = response.json()["result"]["payload"]["market_intelligence_report"]
    assert report["status"] == TaskStatus.DEGRADED.value
    assert report["entry_assessment"]["decision"] == "INSUFFICIENT_DATA"
    assert report["profit_analysis"]["status"] == "unavailable"
    assert "COST_INPUT_UNAVAILABLE" in {
        limitation["reason_code"] for limitation in report["data_limitations"]
    }

    with runtime.session_factory() as session:
        saved_task = session.get(AgentTaskRecord, created["id"])
        saved_report = session.scalar(
            select(MarketIntelligenceReportRecord).where(
                MarketIntelligenceReportRecord.task_id == created["id"]
            )
        )
        assert saved_task is not None
        assert saved_task.status == TaskStatus.DEGRADED.value
        assert saved_report is not None
        assert saved_report.status == TaskStatus.DEGRADED.value
        assert saved_task.result_hash == saved_report.report_hash


@pytest.mark.integration
def test_running_task_cancellation_is_observed_by_graph_and_finalized(
    runtime: RuntimeHarness,
) -> None:
    created = _create_pending_task(runtime, include_profit=True)
    claimed = runtime.task_repository.claim_next("worker-abandoned", 300)
    assert claimed is not None

    cancelled = runtime.client.post(f"/api/v1/agent/tasks/{created['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["cancel_requested_at"] is not None

    with runtime.session_factory() as session:
        session.execute(
            update(AgentTaskRecord)
            .where(AgentTaskRecord.id == created["id"])
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()

    executed = runtime.task_service.run_next()

    assert executed is not None
    assert executed.status is TaskStatus.CANCELLED
    assert executed.completed_at is not None
    assert executed.claimed_by is None
    with runtime.session_factory() as session:
        assert session.scalar(
            select(func.count())
            .select_from(MarketIntelligenceReportRecord)
            .where(MarketIntelligenceReportRecord.task_id == created["id"])
        ) == 0
        steps = session.scalars(
            select(AgentStepRecord).where(AgentStepRecord.task_id == created["id"])
        ).all()
        assert len(steps) == 1
        assert steps[0].status == "FAILED"
        assert steps[0].error_code == "TASK_CANCELLED"


@pytest.mark.integration
def test_expired_worker_lease_can_be_reclaimed_without_losing_task_identity(
    runtime: RuntimeHarness,
) -> None:
    created = _create_pending_task(runtime, include_profit=True)
    first_claim = runtime.task_repository.claim_next("worker-one", 300)
    assert first_claim is not None

    with runtime.session_factory() as session:
        session.execute(
            update(AgentTaskRecord)
            .where(AgentTaskRecord.id == created["id"])
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()

    second_claim = runtime.task_repository.claim_next("worker-two", 300)

    assert second_claim is not None
    assert str(second_claim.id) == created["id"]
    assert second_claim.claimed_by == "worker-two"
    assert second_claim.state_version > first_claim.state_version
    assert second_claim.lease_expires_at is not None
    assert second_claim.lease_expires_at > datetime.now(UTC)


def test_preview_service_and_database_runtime_share_the_same_market_contract(
    runtime: RuntimeHarness,
) -> None:
    preview = runtime.preview_service.preview(
        TaskPreviewRequest(
            intent="market_entry",
            user_query="Analyze portable coffee maker opportunities on Amazon US.",
        )
    )
    assert preview.normalized_input is not None
    business_context = MarketIntelligenceBusinessContext(
        market_intelligence_request=preview.normalized_input
    )
    assert preview.normalized_input.keyword == "portable coffee maker"
    assert business_context.schema_version == "1.0"
    assert business_context.market_intelligence_request == preview.normalized_input
