from dataclasses import dataclass

from app.core.config import Settings
from app.graph.operations_graph import EcommerceOperationsGraph
from app.modules.market_intelligence.composition import (
    build_market_metric_file_service,
    build_market_metric_query_service,
    build_market_metric_upload_service,
    build_market_intelligence_components,
)
from app.modules.market_intelligence.overview import MarketOverviewService
from app.modules.task_center import (
    LegacyOperationsTaskExecutor,
    TaskExecutorDispatcher,
    TaskInputDispatcher,
)
from app.repositories import SQLAlchemyTaskRepository
from app.repositories.market_metric_repository import SQLAlchemyMarketMetricRepository
from app.services import (
    DashboardService,
    MarketMetricFileService,
    MarketMetricQueryService,
    MarketMetricUploadService,
    TaskPreviewService,
    TaskService,
)


@dataclass(frozen=True)
class ApplicationContainer:
    task_service: TaskService
    task_preview_service: TaskPreviewService
    dashboard_service: DashboardService
    market_overview_service: MarketOverviewService
    market_metric_upload_service: MarketMetricUploadService
    market_metric_query_service: MarketMetricQueryService
    market_metric_file_service: MarketMetricFileService


def build_application_container(
    settings: Settings,
    session_factory,
) -> ApplicationContainer:
    """汇总各 Agent 模块，保持任务系统与具体 Graph 解耦。"""

    market = build_market_intelligence_components(settings, session_factory)
    task_repository = SQLAlchemyTaskRepository(session_factory)
    input_dispatcher = TaskInputDispatcher(
        {"market_entry": market.input_extractor}
    )

    legacy_executor = LegacyOperationsTaskExecutor(EcommerceOperationsGraph())
    executor_dispatcher = TaskExecutorDispatcher(
        {
            "market_entry": market.executor,
            "product_strategy": legacy_executor,
            "listing_generation": legacy_executor,
            "operations_diagnosis": legacy_executor,
        }
    )
    task_service = TaskService(
        repository=task_repository,
        input_dispatcher=input_dispatcher,
        executor_dispatcher=executor_dispatcher,
    )
    return ApplicationContainer(
        task_service=task_service,
        task_preview_service=TaskPreviewService(input_dispatcher),
        dashboard_service=DashboardService(),
        market_overview_service=MarketOverviewService(
            market.dataset_registry,
            task_repository,
            market.commerce_registry,
            SQLAlchemyMarketMetricRepository(session_factory),
        ),
        market_metric_upload_service=build_market_metric_upload_service(
            session_factory
        ),
        market_metric_query_service=build_market_metric_query_service(
            session_factory,
            market.product_matcher,
        ),
        market_metric_file_service=build_market_metric_file_service(settings),
    )


__all__ = ["ApplicationContainer", "build_application_container"]
