from app.composition import build_application_container
from app.core.config import settings
from app.db import SessionFactory
from app.services import (
    DashboardService,
    MarketMetricFileService,
    MarketMetricQueryService,
    MarketMetricUploadService,
    TaskPreviewService,
    TaskService,
)
from app.modules.market_intelligence.overview import MarketOverviewService

container = build_application_container(settings, SessionFactory)


def get_task_service() -> TaskService:
    return container.task_service


def get_task_preview_service() -> TaskPreviewService:
    return container.task_preview_service


def get_dashboard_service() -> DashboardService:
    return container.dashboard_service


def get_market_overview_service() -> MarketOverviewService:
    return container.market_overview_service


def get_market_metric_upload_service() -> MarketMetricUploadService:
    return container.market_metric_upload_service


def get_market_metric_query_service() -> MarketMetricQueryService:
    return container.market_metric_query_service


def get_market_metric_file_service() -> MarketMetricFileService:
    return container.market_metric_file_service
