import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_task_service
from app.core.security import TaskCancelDependency, TaskCreateDependency, TaskReadDependency
from app.domain import AgentTask, AgentTaskList, TaskCreate, TaskStatus
from app.repositories import ConcurrentTaskUpdateError
from app.services import TaskService

router = APIRouter(prefix="/agent/tasks", tags=["Agent 任务"])
TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]


@router.post("", response_model=AgentTask, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    service: TaskServiceDependency,
    principal: TaskCreateDependency,
) -> AgentTask:
    try:
        return service.create(payload, principal)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("", response_model=AgentTaskList)
def list_tasks(
    service: TaskServiceDependency,
    principal: TaskReadDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
) -> AgentTaskList:
    tasks = service.list(principal, limit, task_status)
    return AgentTaskList(items=tasks, total=len(tasks))


@router.get("/{task_id}", response_model=AgentTask)
def get_task(
    task_id: str,
    service: TaskServiceDependency,
    principal: TaskReadDependency,
) -> AgentTask:
    try:
        return service.get(task_id, principal)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{task_id}/events", response_class=StreamingResponse)
def task_events(
    task_id: str,
    service: TaskServiceDependency,
    principal: TaskReadDependency,
) -> StreamingResponse:
    try:
        task = service.get(task_id, principal)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    def stream():
        for index, event in enumerate(task.events, start=1):
            payload = json.dumps({"sequence": index, "event": event, "task_id": task_id})
            yield f"id: {index}\nevent: task-update\ndata: {payload}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/{task_id}/cancel", response_model=AgentTask)
def cancel_task(
    task_id: str,
    service: TaskServiceDependency,
    principal: TaskCancelDependency,
) -> AgentTask:
    try:
        return service.cancel(task_id, principal)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ConcurrentTaskUpdateError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
