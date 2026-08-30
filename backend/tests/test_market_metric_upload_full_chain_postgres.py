"""Real-PostgreSQL tests for the macro market metric upload chain.

Run this file separately with a dedicated PostgreSQL URL:

    $env:MARKET_METRIC_UPLOAD_TEST_DATABASE_URL = "postgresql+psycopg://..."
    python -m pytest tests/test_market_metric_upload_full_chain_postgres.py -v -s

Every test creates and drops an isolated PostgreSQL schema. No LLM request is made.
"""

# ruff: noqa: E402

from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker


DATABASE_URL = os.getenv("MARKET_METRIC_UPLOAD_TEST_DATABASE_URL") or os.getenv(
    "MARKET_INTELLIGENCE_E2E_DATABASE_URL"
)
if not DATABASE_URL:
    pytest.skip(
        "MARKET_METRIC_UPLOAD_TEST_DATABASE_URL is required.",
        allow_module_level=True,
    )

# Application modules freeze settings on import. Valid dummy LLM settings avoid
# external calls while allowing the shared application dependencies to load.
os.environ.update(
    {
        "APP_ENV": "test",
        "AUTH_MODE": "jwt",
        "AUTO_CREATE_SCHEMA": "false",
        "DATABASE_URL": DATABASE_URL,
        "LLM_PROVIDER": "bailian",
        "LLM_API_KEY": "unused-test-key",
        "LLM_BASE_URL": "http://127.0.0.1:9/v1",
        "LLM_MODEL": "unused-test-model",
    }
)

from app.adapters.commerce import AdapterContext, CommerceAdapterRegistry
from app.api.dependencies import (
    get_market_metric_file_service,
    get_market_metric_query_service,
    get_market_metric_upload_service,
)
from app.api.v1.market_metrics import router as market_metric_router
from app.core.security import Principal, get_current_principal, permissions_for_roles
from app.db.models import Base, MarketMetricBatchRecord, MarketMetricObservationRecord
from app.modules.market_intelligence.database_market_metric_provider import (
    DatabaseMarketMetricProvider,
)
from app.modules.market_intelligence.macro_market_metric_calculator import (
    MacroMarketMetricCalculator,
)
from app.modules.market_intelligence.schemas import (
    DataSourceMode,
    MarketDataRequest,
)
from app.repositories.market_metric_repository import SQLAlchemyMarketMetricRepository
from app.services import (
    MarketMetricApprovalService,
    MarketMetricFileService,
    MarketMetricQueryService,
    MarketMetricUploadService,
)
from app.tools import ToolRequest
from app.tools.market_data import MarketDataTool


pytestmark = [pytest.mark.integration, pytest.mark.e2e_postgres]


@dataclass
class PrincipalState:
    value: Principal


@dataclass(frozen=True)
class Runtime:
    client: TestClient
    session_factory: sessionmaker[Session]
    file_service: MarketMetricFileService
    provider: DatabaseMarketMetricProvider
    principal_state: PrincipalState


def _principal(*, tenant_id: str = "tenant-market-upload", roles=("operator",)) -> Principal:
    role_set = frozenset(roles)
    return Principal(
        tenant_id=tenant_id,
        user_id=f"user-{tenant_id}",
        username=f"user-{tenant_id}",
        roles=role_set,
        permissions=permissions_for_roles(role_set),
    )


def _isolated_engine(database_url: str) -> tuple[Engine, Engine, str]:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("MARKET_METRIC_UPLOAD_TEST_DATABASE_URL must use PostgreSQL.")
    schema = f"market_metric_upload_{uuid4().hex}"
    admin_engine = create_engine(url, pool_pre_ping=True)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    return admin_engine, engine, schema


@pytest.fixture
def runtime(tmp_path: Path) -> Runtime:
    admin_engine, engine, schema = _isolated_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )
    repository = SQLAlchemyMarketMetricRepository(session_factory)
    upload_service = MarketMetricUploadService(
        repository=repository,
        calculator=MacroMarketMetricCalculator(),
        approval_service=MarketMetricApprovalService(),
    )
    query_service = MarketMetricQueryService(repository)
    file_service = MarketMetricFileService(
        storage_root=tmp_path / "market-metric-files",
        max_bytes=65_536,
        max_uncompressed_bytes=1_048_576,
        max_rows=20,
    )
    provider = DatabaseMarketMetricProvider(repository)
    principal_state = PrincipalState(_principal())

    test_app = FastAPI()
    test_app.include_router(market_metric_router, prefix="/api/v1")
    test_app.dependency_overrides[get_current_principal] = lambda: principal_state.value
    test_app.dependency_overrides[get_market_metric_upload_service] = lambda: upload_service
    test_app.dependency_overrides[get_market_metric_query_service] = lambda: query_service
    test_app.dependency_overrides[get_market_metric_file_service] = lambda: file_service

    try:
        with TestClient(test_app) as client:
            yield Runtime(
                client=client,
                session_factory=session_factory,
                file_service=file_service,
                provider=provider,
                principal_state=principal_state,
            )
    finally:
        engine.dispose()
        try:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            admin_engine.dispose()


def _batch(
    *,
    period_start: str,
    period_end: str,
    source_timestamp: str,
    data_version: str,
    keyword: str = "portable coffee maker",
) -> dict:
    return {
        "platform": "amazon",
        "market": "US",
        "category": "portable_coffee",
        "keyword": keyword,
        "period_start": period_start,
        "period_end": period_end,
        "source_name": "Operations Macro Upload",
        "source_type": "manual_import",
        "source_description": "Authorized annual category statistics.",
        "source_timestamp": source_timestamp,
        "methodology": "Annual market totals from the authorized operations export.",
        "license_or_authorization": "Internal authorized use.",
        "data_version": data_version,
    }


def _csv(*, market_size: int | None, gmv: int | None, sales_volume: int) -> bytes:
    rows = ["metric_code,value,unit,currency"]
    if market_size is not None:
        rows.append(f"market_size,{market_size},USD,USD")
    if gmv is not None:
        rows.append(f"gmv,{gmv},USD,USD")
    rows.append(f"sales_volume,{sales_volume},units,")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _upload(
    client: TestClient,
    batch: dict,
    content: bytes,
    filename="metrics.csv",
    content_type="text/csv",
):
    return client.post(
        "/api/v1/market-intelligence/market-metrics",
        data={"batch": json.dumps(batch)},
        files={"file": (filename, content, content_type)},
    )


def test_upload_to_approved_query_and_market_data_tool_uses_real_postgres(
    runtime: Runtime,
) -> None:
    previous_file = _csv(market_size=1_000_000, gmv=250_000, sales_volume=5_000)
    previous = _upload(
        runtime.client,
        _batch(
            period_start="2024-01-01T00:00:00Z",
            period_end="2024-12-31T23:59:59Z",
            source_timestamp="2025-01-10T00:00:00Z",
            data_version="2024-final",
        ),
        previous_file,
    )
    assert previous.status_code == 201, previous.text
    assert previous.json()["status"] == "approved"
    assert previous.json()["approval_codes"] == []
    assert previous.json()["direct_metric_count"] == 3
    assert previous.json()["derived_metric_count"] == 2

    current_file = _csv(market_size=1_200_000, gmv=300_000, sales_volume=6_000)
    current = _upload(
        runtime.client,
        _batch(
            period_start="2025-01-01T00:00:00Z",
            period_end="2025-12-31T23:59:59Z",
            source_timestamp="2026-01-10T00:00:00Z",
            data_version="2025-final",
        ),
        current_file,
    )
    assert current.status_code == 201, current.text
    created = current.json()
    assert created["status"] == "approved"
    assert created["reviewed_by"] == "system:market-metric-validator"
    assert created["direct_metric_count"] == 3
    assert created["derived_metric_count"] == 3

    listed = runtime.client.get(
        "/api/v1/market-intelligence/market-metrics",
        params={"status": "approved", "limit": 10, "offset": 0},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 2
    assert listed.json()["items"][0]["id"] == created["batch_id"]

    detail_response = runtime.client.get(
        f"/api/v1/market-intelligence/market-metrics/{created['batch_id']}"
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["batch"]["review_codes"] == []
    assert detail["batch"]["original_file_sha256"] == hashlib.sha256(
        current_file
    ).hexdigest()
    direct = {item["metric_code"]: item for item in detail["direct_observations"]}
    derived = {item["metric_code"]: item for item in detail["derived_observations"]}
    assert Decimal(direct["market_size"]["value"]) == Decimal("1200000")
    assert Decimal(derived["growth"]["value"]) == Decimal("20")
    assert Decimal(derived["average_transaction_price"]["value"]) == Decimal("50")
    assert Decimal(derived["gmv_market_share"]["value"]) == Decimal("25")

    relative = detail["batch"]["original_file_ref"].removeprefix(
        runtime.file_service.reference_prefix
    )
    assert (runtime.file_service.storage_root / relative).read_bytes() == current_file

    tool = MarketDataTool(
        registry=CommerceAdapterRegistry(),
        market_metric_provider=runtime.provider,
    )
    tool_response = tool.execute(
        ToolRequest(
            tenant_id="tenant-market-upload",
            user_id="user-tenant-market-upload",
            trace_id="trace-market-upload",
            task_id="task-market-upload",
            parameters={
                "schema_version": "1.0",
                "task_id": "task-market-upload",
                "platform": "amazon",
                "market": "US",
                "category": "portable_coffee",
                "keyword": "portable coffee maker",
                "data_source_mode": "fixed_dataset",
            },
        )
    )
    assert tool_response.success is True
    assert tool_response.degraded is True
    assert "DATABASE_MARKET_METRICS_APPLIED" in tool_response.data["warnings"]
    tool_metrics = {
        item["metric_code"]: item for item in tool_response.data["metrics"]
    }
    assert Decimal(tool_metrics["market_size"]["value"]) == Decimal("1200000")
    assert Decimal(tool_metrics["growth"]["value"]) == Decimal("20")
    assert tool_response.data["source_market_metric_batch_ids"]
    assert tool_response.data["evidence_refs"]

    duplicate = _upload(
        runtime.client,
        _batch(
            period_start="2025-01-01T00:00:00Z",
            period_end="2025-12-31T23:59:59Z",
            source_timestamp="2026-01-10T00:00:00Z",
            data_version="2025-final",
        ),
        current_file,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "MARKET_METRIC_UPLOAD_CONFLICT"
    assert len(list(runtime.file_service.storage_root.rglob("*.csv"))) == 2

    with runtime.session_factory() as session:
        assert session.scalar(
            select(func.count()).select_from(MarketMetricBatchRecord)
        ) == 2
        assert session.scalar(
            select(func.count()).select_from(MarketMetricObservationRecord)
        ) == 11


@pytest.mark.parametrize("file_format", ["json", "xlsx"])
def test_json_and_xlsx_uploads_are_parsed_and_approved(
    runtime: Runtime,
    file_format: str,
) -> None:
    rows = [
        {"metric_code": "market_size", "value": 1000, "unit": "USD", "currency": "USD"},
        {"metric_code": "gmv", "value": 250, "unit": "USD", "currency": "USD"},
        {"metric_code": "sales_volume", "value": 10, "unit": "units"},
    ]
    if file_format == "json":
        content = json.dumps({"metrics": rows}).encode("utf-8")
        filename = "metrics.json"
        content_type = "application/json"
    else:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["metric_code", "value", "unit", "currency"])
        for row in rows:
            worksheet.append(
                [row["metric_code"], row["value"], row["unit"], row.get("currency")]
            )
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()
        content = output.getvalue()
        filename = "metrics.xlsx"
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    response = _upload(
        runtime.client,
        _batch(
            period_start="2025-01-01T00:00:00Z",
            period_end="2025-12-31T23:59:59Z",
            source_timestamp="2026-01-10T00:00:00Z",
            data_version=f"{file_format}-v1",
            keyword=f"portable coffee maker {file_format}",
        ),
        content,
        filename=filename,
        content_type=content_type,
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "approved"
    assert response.json()["direct_metric_count"] == 3


def test_system_rejection_is_persisted_and_excluded_from_provider(runtime: Runtime) -> None:
    keyword = "category without core metric"
    response = _upload(
        runtime.client,
        _batch(
            period_start="2025-01-01T00:00:00Z",
            period_end="2025-12-31T23:59:59Z",
            source_timestamp="2026-01-10T00:00:00Z",
            data_version="rejected-v1",
            keyword=keyword,
        ),
        _csv(market_size=None, gmv=None, sales_volume=100),
    )
    assert response.status_code == 201, response.text
    rejected = response.json()
    assert rejected["status"] == "rejected"
    assert rejected["approval_codes"] == ["CORE_MARKET_METRIC_MISSING"]

    detail = runtime.client.get(
        f"/api/v1/market-intelligence/market-metrics/{rejected['batch_id']}"
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["batch"]["review_codes"] == [
        "CORE_MARKET_METRIC_MISSING"
    ]

    provider_result = runtime.provider.get_metrics(
        request=MarketDataRequest(
            platform="amazon",
            market="US",
            category="portable_coffee",
            keyword=keyword,
        ),
        context=AdapterContext(
            tenant_id="tenant-market-upload",
            user_id="user-tenant-market-upload",
            trace_id="trace-rejected",
            task_id="task-rejected",
            tool_call_id="tool-rejected",
        ),
        data_source_mode=DataSourceMode.FIXED_DATASET,
    )
    assert provider_result.metrics == []
    assert provider_result.evidence_refs == []


def test_upload_permissions_tenant_isolation_and_file_limits(runtime: Runtime) -> None:
    payload = _batch(
        period_start="2025-01-01T00:00:00Z",
        period_end="2025-12-31T23:59:59Z",
        source_timestamp="2026-01-10T00:00:00Z",
        data_version="security-v1",
    )
    content = _csv(market_size=100, gmv=25, sales_volume=5)
    created = _upload(runtime.client, payload, content)
    assert created.status_code == 201, created.text
    batch_id = created.json()["batch_id"]

    runtime.principal_state.value = _principal(roles=("approver",))
    forbidden = _upload(runtime.client, {**payload, "data_version": "forbidden"}, content)
    assert forbidden.status_code == 403

    runtime.principal_state.value = _principal(tenant_id="another-tenant")
    hidden = runtime.client.get(
        f"/api/v1/market-intelligence/market-metrics/{batch_id}"
    )
    assert hidden.status_code == 404

    runtime.principal_state.value = _principal()
    oversized = _upload(
        runtime.client,
        {**payload, "data_version": "oversized"},
        b"x" * 65_537,
    )
    assert oversized.status_code == 413
    assert oversized.json()["detail"]["code"] == "UPLOAD_FILE_TOO_LARGE"

    unsupported = _upload(
        runtime.client,
        {**payload, "data_version": "unsupported"},
        b"metric_code,value,unit\nmarket_size,100,USD\n",
        filename="metrics.txt",
    )
    assert unsupported.status_code == 415
    assert unsupported.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"

    with runtime.session_factory() as session:
        assert session.scalar(
            select(func.count()).select_from(MarketMetricBatchRecord)
        ) == 1
