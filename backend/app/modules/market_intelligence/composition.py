from dataclasses import dataclass
from pathlib import Path

from app.adapters.commerce import CommerceAdapterRegistry
from app.adapters.commerce.dataset import DatasetAdapter, DatasetCatalog, DatasetRegistry
from app.adapters.commerce.dataset.dataset_adapter import DEFAULT_DATASET_ROOT
from app.agents.market_intelligence_reporter import LLMMarketIntelligenceReporter
from app.core.config import Settings
from app.graph.market_intelligence_graph import (
    CancellationPort,
    CheckpointPort,
    MarketIntelligenceGraph,
    ReportPersistencePort,
    StepExecutionPort,
    ToolExecutionPort,
)
from app.llm.factory import build_structured_llm_client
from app.modules.market_intelligence.dataset_availability import DatasetAvailability
from app.modules.market_intelligence.database_market_metric_provider import (
    DatabaseMarketMetricProvider,
)
from app.modules.market_intelligence.data_source_availability import (
    MarketDataSourceAvailability,
)
from app.modules.market_intelligence.input_extractor import (
    MarketIntelligenceInputExtractor,
)
from app.modules.market_intelligence.market_metric_product_matcher import (
    MarketMetricProductMatcher,
)
from app.modules.market_intelligence.macro_market_metric_calculator import (
    MacroMarketMetricCalculator,
)
from app.modules.market_intelligence.persistence import (
    SQLAlchemyMarketCancellationPort,
    SQLAlchemyMarketCheckpointPort,
    SQLAlchemyStepExecutionPort,
    SQLAlchemyTaskEventPublisher,
    SQLAlchemyToolExecutionPort,
)
from app.modules.market_intelligence.task_executor import (
    MarketIntelligenceTaskExecutor,
)
from app.modules.task_center import TaskInputDispatcher
from app.repositories.collection_repository import (
    CollectionRepository,
    SQLAlchemyCollectionRepository,
)
from app.repositories.market_metric_repository import (
    SQLAlchemyMarketMetricRepository,
)
from app.services.market_intelligence_service import MarketIntelligenceService
from app.services.market_metric_approval_service import MarketMetricApprovalService
from app.services.market_metric_file_service import MarketMetricFileService
from app.services.market_metric_query_service import MarketMetricQueryService
from app.services.market_metric_upload_service import MarketMetricUploadService
from app.tools.market_data import MarketDataTool
from app.tools.product_search import ProductSearchTool
from app.tools.profit_calculator import ProfitCalculatorTool
from app.tools.review_insight import ProgressPublisher, ReviewInsightTool
from app.tools.support.llm_review_analyzer import LLMReviewAnalyzer


@dataclass(frozen=True)
class MarketIntelligenceComponents:
    dataset_registry: DatasetRegistry
    commerce_registry: CommerceAdapterRegistry
    input_extractor: MarketIntelligenceInputExtractor
    product_matcher: MarketMetricProductMatcher
    executor: MarketIntelligenceTaskExecutor


def build_dataset_registry() -> DatasetRegistry:
    return DatasetCatalog(DEFAULT_DATASET_ROOT).load()


def build_task_input_dispatcher(
    settings: Settings,
    dataset_registry: DatasetRegistry | None = None,
) -> TaskInputDispatcher:
    datasets = dataset_registry or build_dataset_registry()
    commerce_registry = build_commerce_adapter_registry(settings, datasets)
    extractor = build_market_intelligence_input_extractor(
        settings,
        datasets,
        commerce_registry,
    )
    return TaskInputDispatcher({"market_entry": extractor})


def build_market_intelligence_input_extractor(
    settings: Settings,
    dataset_registry: DatasetRegistry | None = None,
    commerce_registry: CommerceAdapterRegistry | None = None,
    market_metric_repository: SQLAlchemyMarketMetricRepository | None = None,
    product_matcher: MarketMetricProductMatcher | None = None,
) -> MarketIntelligenceInputExtractor:
    llm_settings = (
        settings.llm_provider,
        settings.llm_api_key,
        settings.llm_base_url,
        settings.llm_model,
    )
    llm_client = build_structured_llm_client(settings) if all(llm_settings) else None
    datasets = dataset_registry or build_dataset_registry()
    adapters = commerce_registry or build_commerce_adapter_registry(settings, datasets)
    matcher = product_matcher or build_market_metric_product_matcher(settings, datasets)
    return MarketIntelligenceInputExtractor(
        availability=DatasetAvailability(datasets),
        llm_client=llm_client,
        data_sources=MarketDataSourceAvailability(adapters),
        market_metric_repository=market_metric_repository,
        market_metric_product_matcher=matcher,
    )


def build_market_metric_product_matcher(
    settings: Settings,
    dataset_registry: DatasetRegistry,
) -> MarketMetricProductMatcher:
    llm_settings = (
        settings.llm_provider,
        settings.llm_api_key,
        settings.llm_base_url,
        settings.llm_model,
    )
    return MarketMetricProductMatcher(
        DatasetAvailability(dataset_registry),
        build_structured_llm_client(settings) if all(llm_settings) else None,
        model=settings.llm_model or None,
    )


def build_commerce_adapter_registry(
    settings: Settings,
    dataset_registry: DatasetRegistry | None = None,
) -> CommerceAdapterRegistry:
    registry = CommerceAdapterRegistry()

    if settings.environment.lower() in {
        "test",
        "demo",
        "local",
        "docker",
    }:
        fixed_dataset_registry = dataset_registry or build_dataset_registry()
        amazon_dataset_adapter = DatasetAdapter(
            platform="amazon",
            dataset_registry=fixed_dataset_registry,
            max_products=settings.market_max_product_limit,
            max_reviews_per_product=(settings.market_max_reviews_per_product),
            public_dataset_ids={
                entry.manifest.dataset_id
                for entry in fixed_dataset_registry.all()
                if entry.manifest.platform.casefold() == "amazon"
            },
        )
        registry.register(amazon_dataset_adapter)

    return registry

def build_repository(
    session_factory,
) -> CollectionRepository:
    return SQLAlchemyCollectionRepository(
        session_factory
    )


def build_product_search_tool(
    registry: CommerceAdapterRegistry,
    repository: CollectionRepository,
    settings: Settings,
) -> ProductSearchTool:
    return ProductSearchTool(
        adapter_registry=registry,
        repository=repository,
        max_product_limit=settings.market_max_product_limit,
    )

def build_review_insight_tool(
    registry: CommerceAdapterRegistry,
    repository: CollectionRepository,
    settings: Settings,
    progress_publisher: ProgressPublisher | None = None,
) -> ReviewInsightTool:
    llm_client = build_structured_llm_client(settings)

    review_analyzer = LLMReviewAnalyzer(
        client=llm_client,
        batch_size=settings.review_llm_batch_size,
        max_reviews=settings.review_llm_max_reviews,
        max_content_chars=settings.review_llm_max_content_chars,
        output_language=settings.review_llm_output_language,
    )
    return ReviewInsightTool(
        adapter_registry=registry,
        repository=repository,
        analyzer=review_analyzer,
        max_reviews_per_product=settings.market_max_reviews_per_product,
        progress_publisher=progress_publisher,
    )


def build_database_market_metric_provider(
    session_factory,
    repository: SQLAlchemyMarketMetricRepository | None = None,
) -> DatabaseMarketMetricProvider:
    return DatabaseMarketMetricProvider(
        repository or SQLAlchemyMarketMetricRepository(session_factory)
    )


def build_market_metric_upload_service(
    session_factory,
) -> MarketMetricUploadService:
    """装配宏观市场指标的计算、自动审核和持久化链路。"""
    return MarketMetricUploadService(
        repository=SQLAlchemyMarketMetricRepository(session_factory),
        calculator=MacroMarketMetricCalculator(),
        approval_service=MarketMetricApprovalService(),
    )


def build_market_metric_query_service(
    session_factory,
    product_matcher: MarketMetricProductMatcher | None = None,
) -> MarketMetricQueryService:
    return MarketMetricQueryService(
        SQLAlchemyMarketMetricRepository(session_factory),
        product_matcher,
    )


def build_market_metric_file_service(settings: Settings) -> MarketMetricFileService:
    return MarketMetricFileService(
        storage_root=Path(settings.market_metric_upload_storage_root),
        max_bytes=settings.market_metric_upload_max_bytes,
        max_uncompressed_bytes=settings.market_metric_upload_max_uncompressed_bytes,
        max_rows=settings.market_metric_upload_max_rows,
    )


def build_market_data_tool(
    registry: CommerceAdapterRegistry,
    repository: CollectionRepository,
    settings: Settings,
    market_metric_provider: DatabaseMarketMetricProvider | None = None,
) -> MarketDataTool:
    return MarketDataTool(
        registry=registry,
        market_metric_provider=market_metric_provider,
    )


def build_profit_calculator_tool() -> ProfitCalculatorTool:
    return ProfitCalculatorTool()


def build_market_intelligence_graph(
    registry: CommerceAdapterRegistry,
    repository: CollectionRepository,
    settings: Settings,
    *,
    cancellation_port: CancellationPort | None = None,
    checkpoint_port: CheckpointPort | None = None,
    report_persistence_port: ReportPersistencePort | None = None,
    tool_execution_port: ToolExecutionPort | None = None,
    step_execution_port: StepExecutionPort | None = None,
    market_metric_provider: DatabaseMarketMetricProvider | None = None,
) -> MarketIntelligenceGraph:
    return MarketIntelligenceGraph(
        product_search_tool=build_product_search_tool(
            registry, repository, settings
        ),
        market_data_tool=build_market_data_tool(
            registry,
            repository,
            settings,
            market_metric_provider,
        ),
        review_insight_tool=build_review_insight_tool(
            registry,
            repository,
            settings,
            progress_publisher=(
                getattr(tool_execution_port, "progress", None)
                if tool_execution_port is not None
                else None
            ),
        ),
        profit_calculator_tool=build_profit_calculator_tool(),
        report_synthesizer=LLMMarketIntelligenceReporter(
            build_structured_llm_client(settings)
        ),
        cancellation_port=cancellation_port,
        checkpoint_port=checkpoint_port,
        report_persistence_port=report_persistence_port,
        tool_execution_port=tool_execution_port,
        step_execution_port=step_execution_port,
        max_retries=settings.llm_max_retries,
        heartbeat_interval_seconds=max(
            5,
            min(30, settings.task_lease_seconds / 3),
        ),
    )


def build_market_intelligence_service(
    registry: CommerceAdapterRegistry,
    repository: CollectionRepository,
    settings: Settings,
    *,
    cancellation_port: CancellationPort | None = None,
    checkpoint_port: CheckpointPort | None = None,
    report_persistence_port: ReportPersistencePort | None = None,
    tool_execution_port: ToolExecutionPort | None = None,
    step_execution_port: StepExecutionPort | None = None,
    market_metric_provider: DatabaseMarketMetricProvider | None = None,
) -> MarketIntelligenceService:
    graph = build_market_intelligence_graph(
        registry,
        repository,
        settings,
        cancellation_port=cancellation_port,
        checkpoint_port=checkpoint_port,
        report_persistence_port=report_persistence_port,
        tool_execution_port=tool_execution_port,
        step_execution_port=step_execution_port,
        market_metric_provider=market_metric_provider,
    )
    return MarketIntelligenceService(graph)


def build_market_intelligence_components(
    settings: Settings,
    session_factory,
) -> MarketIntelligenceComponents:
    dataset_registry = build_dataset_registry()
    commerce_registry = build_commerce_adapter_registry(
        settings,
        dataset_registry,
    )
    repository = build_repository(session_factory)
    market_metric_repository = SQLAlchemyMarketMetricRepository(session_factory)
    product_matcher = build_market_metric_product_matcher(settings, dataset_registry)
    event_publisher = SQLAlchemyTaskEventPublisher(session_factory)
    service = build_market_intelligence_service(
        commerce_registry,
        repository,
        settings,
        cancellation_port=SQLAlchemyMarketCancellationPort(
            session_factory, settings.task_lease_seconds
        ),
        checkpoint_port=SQLAlchemyMarketCheckpointPort(session_factory),
        tool_execution_port=SQLAlchemyToolExecutionPort(
            session_factory, event_publisher
        ),
        step_execution_port=SQLAlchemyStepExecutionPort(
            session_factory, event_publisher
        ),
        market_metric_provider=build_database_market_metric_provider(
            session_factory,
            market_metric_repository,
        ),
    )
    return MarketIntelligenceComponents(
        dataset_registry=dataset_registry,
        commerce_registry=commerce_registry,
        input_extractor=build_market_intelligence_input_extractor(
            settings,
            dataset_registry,
            commerce_registry,
            market_metric_repository,
            product_matcher,
        ),
        product_matcher=product_matcher,
        executor=MarketIntelligenceTaskExecutor(service),
    )
