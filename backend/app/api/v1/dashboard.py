from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_dashboard_service, get_task_service
from app.core.security import DashboardDependency as DashboardPrincipalDependency
from app.domain import TaskStatus
from app.schemas.dashboard import DashboardOverview
from app.services import DashboardService, TaskService

router = APIRouter(prefix="/dashboard", tags=["经营总览"])
DashboardDependency = Annotated[DashboardService, Depends(get_dashboard_service)]
TaskDependency = Annotated[TaskService, Depends(get_task_service)]


@router.get("/overview", response_model=DashboardOverview)
def overview(
    dashboard: DashboardDependency,
    tasks: TaskDependency,
    principal: DashboardPrincipalDependency,
    shop_id: str = Query(default="amazon-us-demo", min_length=1),
) -> DashboardOverview:
    waiting = len(tasks.list(principal, limit=100, status=TaskStatus.WAITING_APPROVAL))
    return dashboard.overview(shop_id, waiting)
