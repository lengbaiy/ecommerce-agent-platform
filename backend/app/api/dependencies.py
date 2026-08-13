from app.core.config import settings
from app.db import SessionFactory, init_database
from app.repositories import SQLAlchemyTaskRepository
from app.services import DashboardService, TaskService

if settings.auto_create_schema and settings.environment.lower() not in {"production", "prod"}:
    init_database()
task_repository = SQLAlchemyTaskRepository(SessionFactory)
task_service = TaskService(repository=task_repository)
dashboard_service = DashboardService()


def get_task_service() -> TaskService:
    return task_service


def get_dashboard_service() -> DashboardService:
    return dashboard_service
