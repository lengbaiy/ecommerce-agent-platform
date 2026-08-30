from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
import json
from pathlib import Path
from sqlalchemy import func, select

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.commerce.commerce_adapter_base import AdapterContext, AdapterResult
from app.db.models import (
    Base,
    CollectionRunRecord,
    EvidenceReferenceRecord,
    ProductSnapshotRecord,
)
from app.repositories.collection_repository import (
    SQLAlchemyCollectionRepository,
)

from app.adapters.commerce.dataset.dataset_adapter import DatasetAdapter
from app.modules.market_intelligence.schemas import (
    AdapterCapabilities,
    AnalysisScope,
    CollectionRun,
    DataSourceMode,
    EvidenceReference,
    NormalizedProduct,
    ProductSearchRequest,
)
from app.tools import ToolRequest
from app.tools.product_search import ProductSearchTool


@pytest.fixture
def tool_session_factory():
    engine = create_engine(
        "sqlite:///test_market_intelligence.db"
    )

    Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )

    yield factory

    engine.dispose()

def test_product_search_with_real_amazon_dataset(
    tool_session_factory,
):
    # --------------------------------------------------
    # 1. 使用项目里真实的 Amazon 固定数据集
    # --------------------------------------------------

    backend_root = Path(__file__).resolve().parents[1]

    dataset_root = (
        backend_root
        / "data"
        / "market_intelligence"
    )

    dataset_dir = (
        dataset_root
        / "amazon_us_portable_coffee_v1"
    )

    manifest_path = dataset_dir / "manifest.json"

    assert manifest_path.is_file()
    assert (dataset_dir / "products.jsonl").is_file()

    # 直接读取真实 manifest
    # 避免测试代码自己猜 market/category/keyword
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    dataset_id = manifest["dataset_id"]

    # --------------------------------------------------
    # 2. 创建真实 DatasetAdapter
    # --------------------------------------------------

    adapter = DatasetAdapter(
        platform=manifest["platform"],
        dataset_root=dataset_root,

        # 允许测试 tenant 使用这份固定数据集
        public_dataset_ids={dataset_id},
    )

    # --------------------------------------------------
    # 3. Registry 暂时只负责返回真实 Adapter
    # --------------------------------------------------

    registry = Mock()
    registry.get.return_value = adapter

    # --------------------------------------------------
    # 4. 使用真实 Repository
    # --------------------------------------------------

    repository = SQLAlchemyCollectionRepository(
        tool_session_factory
    )

    tool = ProductSearchTool(
        adapter_registry=registry,
        repository=repository,
    )

    # --------------------------------------------------
    # 5. 请求参数也直接使用 manifest
    # --------------------------------------------------

    request = ToolRequest(
        tenant_id="tenant-001",
        user_id="user-001",
        trace_id="trace-real-amazon-001",
        parameters={
            "schema_version": "1.0",
            "task_id": "task-real-amazon-001",
            "tool_call_id": "tool-call-real-amazon-001",

            "platform": manifest["platform"],
            "market": manifest["market"],
            "category": manifest["category"],
            "keyword": manifest["keyword"],

            "product_limit": 5,
            "sort_by": "default",
            "data_source_mode": "fixed_dataset",
        },
    )

    # --------------------------------------------------
    # 6. 真正执行 ProductSearchTool
    # --------------------------------------------------

    response = tool.execute(request)

    assert response.success is True
    assert response.data["schema_version"] == "1.0"

    assert response.data["actual_count"] == 5
    assert len(response.data["products"]) == 5
    assert len(response.data["evidence_refs"]) == 5

    collection_run_id = response.data["collection_run_id"]

    # --------------------------------------------------
    # 7. 确认真正写入 SQLite
    # --------------------------------------------------

    with tool_session_factory() as session:

        saved_run = session.get(
            CollectionRunRecord,
            collection_run_id,
        )

        product_count = session.scalar(
            select(func.count())
            .select_from(ProductSnapshotRecord)
            .where(
                ProductSnapshotRecord.collection_run_id
                == collection_run_id
            )
        )

        evidence_count = session.scalar(
            select(func.count())
            .select_from(EvidenceReferenceRecord)
            .where(
                EvidenceReferenceRecord.collection_run_id
                == collection_run_id
            )
        )

        saved_products = session.scalars(
            select(ProductSnapshotRecord)
            .where(
                ProductSnapshotRecord.collection_run_id
                == collection_run_id
            )
            .order_by(ProductSnapshotRecord.price)
        ).all()

        # CollectionRun 真正写入
        assert saved_run is not None
        assert saved_run.actual_count == 5

        # 5 个真实商品
        assert product_count == 5

        # 5 条真实 Evidence
        assert evidence_count == 5

        # 确认不是之前手工造的假测试数据
        assert all(
            product.platform == "amazon"
            for product in saved_products
        )

        assert all(
            product.product_id != "B000001"
            for product in saved_products
        )

        # 打印出来方便人工观察
        for product in saved_products:
            print(
                product.product_id,
                product.title,
                product.price,
            )


def test_fixed_dataset_evidence_ids_are_scoped_to_collection_run() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    dataset_root = backend_root / "data" / "market_intelligence"
    dataset_dir = dataset_root / "amazon_us_portable_coffee_v1"
    manifest = json.loads(
        (dataset_dir / "manifest.json").read_text(encoding="utf-8")
    )
    adapter = DatasetAdapter(
        platform=manifest["platform"],
        dataset_root=dataset_root,
        public_dataset_ids={manifest["dataset_id"]},
    )
    request = ProductSearchRequest(
        platform=manifest["platform"],
        market=manifest["market"],
        category=manifest["category"],
        keyword=manifest["keyword"],
        product_limit=2,
        sort_by="default",
    )

    results = [
        adapter.search_products(
            request,
            AdapterContext(
                tenant_id="tenant-001",
                user_id="user-001",
                trace_id=f"trace-{index}",
                task_id=f"task-{index}",
                tool_call_id=f"tool-call-{index}",
            ),
        )
        for index in (1, 2)
    ]

    assert results[0].run.id != results[1].run.id
    assert {
        evidence.evidence_id for evidence in results[0].evidence_refs
    }.isdisjoint(
        evidence.evidence_id for evidence in results[1].evidence_refs
    )


def test_product_search_persists_result_to_database(
    tool_session_factory,
):
    now = datetime.now(UTC)

    # ---------- Adapter 返回的数据 ----------

    run = CollectionRun(
        id="run-001",
        task_id="task-001",
        trace_id="trace-001",
        tenant_id="tenant-001",
        keyword="portable coffee maker",
        requested_count=1,
        actual_count=1,
        status="COMPLETED",
        adapter_version="amazon-dataset-v1",
        parser_version=None,
        started_at=now,
        finished_at=now,
    )

    product = NormalizedProduct(
        snapshot_id="snapshot-001",
        collection_run_id=run.id,
        platform="amazon",
        market="US",
        product_id="B000001",
        title="Portable Coffee Maker",
        brand="Example",
        category="Coffee Makers",
        price=Decimal("49.99"),
        currency="USD",
        sales_display=None,
        sales_value=None,
        sales_value_type="unknown",
        shop_name="Example Store",
        rating=Decimal("4.5"),
        review_count=100,
        source_ref="amazon:B000001",
        source_url=None,
        source_snapshot_ref="products.jsonl#1",
        source_timestamp=now,
        ingest_timestamp=now,
        source_type="fixed_dataset",
        data_status="valid",
    )

    scope = AnalysisScope(
        market="US",
        platforms=["amazon"],
        category="Coffee Makers",
        keyword="portable coffee maker",
        start_time=None,
        end_time=now,
        requested_product_count=1,
        actual_product_count=1,
        actual_review_count=0,
        data_source_mode="fixed_dataset",
    )

    evidence = EvidenceReference(
        evidence_id="evidence-001",
        evidence_type="product",
        data_level="D",
        data_source="Amazon Reviews 2023",
        platform="amazon",
        product_id="B000001",
        query_range={
            "market": "US",
            "category": "Coffee Makers",
            "keyword": "portable coffee maker",
            "product_limit": 1,
            "sort_by": "default",
        },
        source_timestamp=now,
        ingest_timestamp=now,
        tool_call_id="tool-call-001",
        collection_run_id=run.id,
        snapshot_ref="products.jsonl#1",
        sha256="a" * 64,
        data_version="v1",
        sample_scope=scope,
    )

    # ---------- Mock Adapter ----------

    adapter = Mock()

    adapter.capabilities.return_value = AdapterCapabilities(
        platform="amazon",
        data_source_mode=DataSourceMode.FIXED_DATASET,
        supports_products=True,
        supports_reviews=False,
        supports_market_metrics=False,
        max_products=50,
        max_reviews_per_product=0,
        adapter_version="amazon-dataset-v1",
        schema_version="1.0",
    )

    adapter.search_products.return_value = AdapterResult(
        data=[product],
        run=run,
        evidence_refs=[evidence],
        warnings=[],
        degraded=False,
    )

    registry = Mock()
    registry.get.return_value = adapter

    # ---------- 使用真实 Repository ----------

    repository = SQLAlchemyCollectionRepository(
        tool_session_factory
    )

    tool = ProductSearchTool(
        adapter_registry=registry,
        repository=repository,
    )

    request = ToolRequest(
        tenant_id="tenant-001",
        user_id="user-001",
        trace_id="trace-001",
        parameters={
            "schema_version": "1.0",
            "task_id": "task-001",
            "tool_call_id": "tool-call-001",
            "platform": "amazon",
            "market": "US",
            "category": "Coffee Makers",
            "keyword": "portable coffee maker",
            "product_limit": 1,
            "sort_by": "default",
            "data_source_mode": "fixed_dataset",
        },
    )

    # ---------- 执行 Tool ----------

    response = tool.execute(request)

    assert response.success is True
    assert response.data["collection_run_id"] == "run-001"
    assert response.data["actual_count"] == 1

    # ---------- 验证数据库 ----------

    with tool_session_factory() as session:
        saved_run = session.get(
            CollectionRunRecord,
            "run-001",
        )

        saved_product = session.get(
            ProductSnapshotRecord,
            "snapshot-001",
        )

        saved_evidence = session.get(
            EvidenceReferenceRecord,
            "evidence-001",
        )

        assert saved_run is not None
        assert saved_run.tenant_id == "tenant-001"
        assert saved_run.status == "COMPLETED"
        assert saved_run.actual_count == 1

        assert saved_product is not None
        assert saved_product.collection_run_id == "run-001"
        assert saved_product.product_id == "B000001"
        assert saved_product.title == "Portable Coffee Maker"
        assert saved_product.price == Decimal("49.9900")
        assert saved_product.currency == "USD"

        assert saved_evidence is not None
        assert saved_evidence.collection_run_id == "run-001"
        assert saved_evidence.product_id == "B000001"
        assert saved_evidence.tool_call_id == "tool-call-001"
        assert saved_evidence.sample_scope["market"] == "US"


def test_product_search_rejects_unsupported_schema_version() -> None:
    tool = ProductSearchTool(
        adapter_registry=object(),
        repository=object(),
    )
    request = ToolRequest(
        tenant_id="tenant-001",
        user_id="user-001",
        trace_id="trace-001",
        parameters={
            "schema_version": "2.0",
            "task_id": "task-001",
            "platform": "amazon",
            "market": "US",
            "category": "Coffee Makers",
            "keyword": "portable coffee maker",
            "product_limit": 1,
            "sort_by": "default",
            "data_source_mode": "fixed_dataset",
        },
    )

    response = tool.execute(request)

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "SCHEMA_VERSION_UNSUPPORTED"
    assert response.data["schema_version"] == "1.0"
