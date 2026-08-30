import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_task_preview_service, get_task_service
from app.core.security import TaskCancelDependency, TaskCreateDependency, TaskReadDependency
from app.domain import (
    AgentTask,
    AgentTaskList,
    TaskCreate,
    TaskPreviewRequest,
    TaskPreviewResponse,
    TaskStatus,
)
from app.modules.task_center import TaskInputValidationError
from app.repositories import ConcurrentTaskUpdateError
from app.services import TaskPreviewService, TaskService

router = APIRouter(prefix="/agent/tasks", tags=["Agent 任务"])
TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]
TaskPreviewServiceDependency = Annotated[
    TaskPreviewService,
    Depends(get_task_preview_service),
]


@router.post("/preview", response_model=TaskPreviewResponse)
def preview_task(
    payload: TaskPreviewRequest,
    service: TaskPreviewServiceDependency,
    principal: TaskCreateDependency,
) -> TaskPreviewResponse:
    try:
        return service.preview(payload, principal)
    except TaskInputValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=error.error.model_dump(mode="json"),
        ) from error


@router.post("", response_model=AgentTask, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    service: TaskServiceDependency,
    principal: TaskCreateDependency,
) -> AgentTask:
    try:
        return service.create(payload, principal)
    except TaskInputValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=error.error.model_dump(mode="json"),
        ) from error
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
    request: Request,
    service: TaskServiceDependency,
    principal: TaskReadDependency,
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID"),
    ] = None,
) -> StreamingResponse:
    try:
        service.get(task_id, principal)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    terminal = {
        TaskStatus.COMPLETED,
        TaskStatus.DEGRADED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }

    async def stream():
        cursor = last_event_id
        idle_seconds = 0.0
        while True:
            if await request.is_disconnected():
                return
            current = service.get(task_id, principal)
            events = service.events(task_id, principal, cursor)
            for event in events:
                payload = json.dumps(
                    event.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                yield (
                    f"id: {event.event_id}\n"
                    f"event: {event.event_type.value}\n"
                    f"data: {payload}\n\n"
                )
                cursor = event.event_id
                idle_seconds = 0.0
            if current.status in terminal:
                return
            if not events:
                idle_seconds += 0.5
                if idle_seconds >= 15:
                    yield ": keep-alive\n\n"
                    idle_seconds = 0.0
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
