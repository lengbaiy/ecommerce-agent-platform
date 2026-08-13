from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_task_service
from app.core.security import ApproverDependency
from app.domain import AgentTask
from app.repositories import ConcurrentTaskUpdateError
from app.services import TaskService

router = APIRouter(prefix="/approvals", tags=["审批"])
TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]


@router.post("/{task_id}/approve", response_model=AgentTask)
def approve(
    task_id: str,
    service: TaskServiceDependency,
    principal: ApproverDependency,
    reason: Annotated[str | None, Query(max_length=500)] = None,
) -> AgentTask:
    try:
        return service.approve(task_id, principal, reason)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ConcurrentTaskUpdateError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{task_id}/reject", response_model=AgentTask)
def reject(
    task_id: str,
    service: TaskServiceDependency,
    principal: ApproverDependency,
    reason: Annotated[str | None, Query(max_length=500)] = None,
) -> AgentTask:
    try:
        return service.reject(task_id, principal, reason)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ConcurrentTaskUpdateError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
