"""Live market-intelligence E2E test.

Run this file separately with a dedicated PostgreSQL URL and real LLM settings:

    $env:MARKET_INTELLIGENCE_E2E_DATABASE_URL = "postgresql+psycopg://..."
    python -m pytest tests/test_market_intelligence_full_chain_postgres.py -v -s

From the repository root, the isolated Compose runner is:

    docker compose --profile test run --rm market-intelligence-e2e

The test creates and drops an isolated PostgreSQL schema. It never replaces the
dataset adapter, LLM client, Graph, tools, repositories, or task services.
"""

# ruff: noqa: E402

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

E2E_DATABASE_URL = os.getenv("MARKET_INTELLIGENCE_E2E_DATABASE_URL")
if not E2E_DATABASE_URL:
    pytest.skip(
        "MARKET_INTELLIGENCE_E2E_DATABASE_URL is required for the live E2E test.",
        allow_module_level=True,
    )

required_llm = {
    "LLM_PROVIDER": os.getenv("LLM_PROVIDER"),
    "LLM_API_KEY": os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
    "LLM_BASE_URL": os.getenv("LLM_BASE_URL"),
    "LLM_MODEL": os.getenv("LLM_MODEL"),
}
missing_llm = [name for name, value in required_llm.items() if not value]
if missing_llm:
    pytest.skip(
        "Live LLM settings are required: " + ", ".join(missing_llm),
        allow_module_level=True,
    )

# These values must be set before importing application modules because Settings
# freezes environment values when app.core.config is imported.
os.environ.update(
    {
        "APP_ENV": "test",
        "AUTH_MODE": "jwt",
        "AUTO_CREATE_SCHEMA": "false",
        "DATABASE_URL": E2E_DATABASE_URL,
        "TASK_EXECUTION_MODE": "worker",
        "REVIEW_LLM_BATCH_SIZE": "3",
        "REVIEW_LLM_MAX_REVIEWS": "6",
    }
)

from app.api.dependencies import get_task_preview_service, get_task_service
from app.core.config import Settings
from app.core.security import (
    Principal,
    get_current_principal,
    permissions_for_roles,
)
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
    TaskEventRecord,
    ToolCallRecord,
)
from app.domain import TaskEventType, TaskStatus
from app.main import app
from app.modules.market_intelligence.composition import (
    build_market_intelligence_components,
)
from app.modules.market_intelligence.schemas import (
    CollectionOptions,
    MarketIntelligenceBusinessContext,
    ProfitCalculatorParameters,
)
from app.modules.task_center import TaskExecutorDispatcher, TaskInputDispatcher
from app.repositories import SQLAlchemyTaskRepository
from app.services import TaskPreviewService, TaskService


pytestmark = [pytest.mark.e2e_postgres, pytest.mark.llm]
TERMINAL_STATUSES = {TaskStatus.COMPLETED, TaskStatus.DEGRADED}
USER_QUERY = "分析美国亚马逊便携咖啡机的市场机会、用户痛点和利润空间。"


@dataclass(frozen=True)
class LiveRuntime:
    session_factory: sessionmaker[Session]
    task_service: TaskService
    client: TestClient


def _principal() -> Principal:
    roles = frozenset({"operator", "approver"})
    return Principal(
        tenant_id="tenant-live-e2e",
        user_id="user-live-e2e",
        username="user-live-e2e",
        roles=roles,
        permissions=permissions_for_roles(roles),
    )


def _create_isolated_engine(database_url: str) -> tuple[Engine, Engine, str]:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("MARKET_INTELLIGENCE_E2E_DATABASE_URL must use PostgreSQL.")

    schema = f"mi_e2e_{uuid4().hex}"
    admin_engine = create_engine(url, pool_pre_ping=True)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    return admin_engine, engine, schema


@pytest.fixture(scope="module")
def live_runtime() -> LiveRuntime:
    settings = Settings()
    settings.validate()
    admin_engine, engine, schema = _create_isolated_engine(settings.database_url)
    previous_overrides = dict(app.dependency_overrides)
    try:
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(
            bind=engine,
            class_=Session,
            expire_on_commit=False,
        )

        components = build_market_intelligence_components(settings, session_factory)
        input_dispatcher = TaskInputDispatcher(
            {"market_entry": components.input_extractor}
        )
        task_service = TaskService(
            repository=SQLAlchemyTaskRepository(session_factory),
            execution_mode="worker",
            input_dispatcher=input_dispatcher,
            executor_dispatcher=TaskExecutorDispatcher(
                {"market_entry": components.executor}
            ),
            worker_id="worker-live-e2e",
            lease_seconds=settings.task_lease_seconds,
        )
        preview_service = TaskPreviewService(input_dispatcher)

        app.dependency_overrides[get_current_principal] = _principal
        app.dependency_overrides[get_task_service] = lambda: task_service
        app.dependency_overrides[get_task_preview_service] = lambda: preview_service

        with TestClient(app) as client:
            yield LiveRuntime(
                session_factory=session_factory,
                task_service=task_service,
                client=client,
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()
        try:
            with admin_engine.begin() as connection:
                connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )
        finally:
            admin_engine.dispose()


def _preview(runtime: LiveRuntime) -> dict:
    response = runtime.client.post(
        "/api/v1/agent/tasks/preview",
        json={"intent": "market_entry", "user_query": USER_QUERY},
    )
    assert response.status_code == 200, response.text
    preview = response.json()

    assert preview["missing_fields"] == []
    assert preview["normalized_input"] is not None
    assert preview["normalized_input"]["platforms"] == ["amazon"]
    assert preview["normalized_input"]["market"] == "US"
    assert preview["normalized_input"]["keyword"] == "portable coffee maker"
    assert any(
        match["supported"]
        and match["dataset_id"] == "amazon_us_portable_coffee_v1"
        for match in preview["dataset_matches"]
    )
    assert "INPUT_EXTRACTION_FALLBACK" not in {
        warning["code"] for warning in preview["warnings"]
    }
    return preview


def _task_payload(preview: dict) -> dict:
    request = dict(preview["normalized_input"])
    request["collection"] = CollectionOptions(
        product_limit=2,
        review_limit_per_product=3,
    ).model_dump(mode="json")
    request["profit_constraints"] = ProfitCalculatorParameters(
        price="99.00",
        product_cost="35.00",
        platform_fee="14.00",
        logistics_cost="10.00",
        advertising_cost="8.00",
        minimum_margin="0.20",
        currency="USD",
    ).model_dump(mode="json")
    context = MarketIntelligenceBusinessContext(
        market_intelligence_request=request
    )
    return {
        "user_query": USER_QUERY,
        "intent": "market_entry",
        "business_context": context.model_dump(mode="json"),
        "constraints": {},
    }


def _create_and_execute(runtime: LiveRuntime, payload: dict) -> dict:
    created_response = runtime.client.post("/api/v1/agent/tasks", json=payload)
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    assert created["status"] == TaskStatus.PENDING.value

    executed = runtime.task_service.run_next()
    assert executed is not None
    assert str(executed.id) == created["id"]
    assert executed.status in TERMINAL_STATUSES
    assert executed.error is None

    fetched_response = runtime.client.get(f"/api/v1/agent/tasks/{created['id']}")
    assert fetched_response.status_code == 200, fetched_response.text
    fetched = fetched_response.json()
    assert fetched["status"] in {status.value for status in TERMINAL_STATUSES}
    assert fetched["result"] is not None
    assert fetched["result_hash"]
    assert fetched["claimed_by"] is None
    assert fetched["lease_expires_at"] is None
    return fetched


def _assert_persisted_task(runtime: LiveRuntime, task: dict) -> set[str]:
    task_id = task["id"]
    report = task["result"]["payload"]["market_intelligence_report"]
    assert report["task_id"] == task_id
    assert report["competitor_matrix"]
    assert report["review_insights"]["evidence_ids"]
    assert report["profit_analysis"]["status"] == "available"
    assert report["evidence_refs"]

    with runtime.session_factory() as session:
        run_ids = set(
            session.scalars(
                select(CollectionRunRecord.id).where(
                    CollectionRunRecord.task_id == task_id
                )
            )
        )
        assert len(run_ids) == 2
        assert session.scalar(
            select(func.count())
            .select_from(ProductSnapshotRecord)
            .where(ProductSnapshotRecord.collection_run_id.in_(run_ids))
        ) == 2
        assert session.scalar(
            select(func.count())
            .select_from(ReviewSnapshotRecord)
            .where(ReviewSnapshotRecord.collection_run_id.in_(run_ids))
        ) == 6

        evidence_ids = set(
            session.scalars(
                select(EvidenceReferenceRecord.id).where(
                    EvidenceReferenceRecord.collection_run_id.in_(run_ids)
                )
            )
        )
        assert evidence_ids
        assert len(evidence_ids) == session.scalar(
            select(func.count())
            .select_from(EvidenceReferenceRecord)
            .where(EvidenceReferenceRecord.collection_run_id.in_(run_ids))
        )

        tool_calls = session.scalars(
            select(ToolCallRecord).where(ToolCallRecord.task_id == task_id)
        ).all()
        assert len(tool_calls) == 4
        assert all(call.status == "COMPLETED" for call in tool_calls)
        assert all(call.error_code is None for call in tool_calls)

        steps = session.scalars(
            select(AgentStepRecord).where(AgentStepRecord.task_id == task_id)
        ).all()
        assert len(steps) == 9
        assert all(step.status == "COMPLETED" for step in steps)
        assert session.scalar(
            select(func.count())
            .select_from(GraphCheckpointRecord)
            .where(GraphCheckpointRecord.task_id == task_id)
        ) == 9

        saved_report = session.scalar(
            select(MarketIntelligenceReportRecord).where(
                MarketIntelligenceReportRecord.task_id == task_id
            )
        )
        assert saved_report is not None
        assert saved_report.report_hash == task["result_hash"]
        assert saved_report.report_payload == report

        saved_task = session.get(AgentTaskRecord, task_id)
        assert saved_task is not None
        assert saved_task.claimed_by is None
        assert saved_task.lease_expires_at is None

        event_types = set(
            session.scalars(
                select(TaskEventRecord.event_type).where(
                    TaskEventRecord.task_id == task_id
                )
            )
        )
        assert TaskEventType.TOOL_PROGRESS.value in event_types
        assert TaskEventType.TASK_FAILED.value not in event_types

    events_response = runtime.client.get(f"/api/v1/agent/tasks/{task_id}/events")
    assert events_response.status_code == 200, events_response.text
    assert "event: tool.progress" in events_response.text
    assert (
        "event: task.completed" in events_response.text
        or "event: task.degraded" in events_response.text
    )
    return evidence_ids


def test_natural_language_to_report_twice_uses_real_postgres_and_llm(
    live_runtime: LiveRuntime,
) -> None:
    preview = _preview(live_runtime)
    payload = _task_payload(preview)

    first_task = _create_and_execute(live_runtime, payload)
    second_task = _create_and_execute(live_runtime, payload)

    first_evidence_ids = _assert_persisted_task(live_runtime, first_task)
    second_evidence_ids = _assert_persisted_task(live_runtime, second_task)

    assert first_task["id"] != second_task["id"]
    assert first_evidence_ids.isdisjoint(second_evidence_ids)
