from typing import Protocol

from app.core.security import Principal
from app.domain import TaskCreate, TaskError, TaskPreviewRequest, TaskPreviewResponse


class TaskInputValidationError(ValueError):
    def __init__(self, error: TaskError) -> None:
        super().__init__(error.message)
        self.error = error


class TaskInputExtractor(Protocol):
    def preview(
        self,
        payload: TaskPreviewRequest,
        principal: Principal | None = None,
    ) -> TaskPreviewResponse: ...

    def validate_task(self, payload: TaskCreate) -> None: ...


class TaskInputDispatcher:
    """按 intent 选择输入提取器，并复用同一规则校验正式任务。"""

    def __init__(self, extractors: dict[str, TaskInputExtractor]) -> None:
        self.extractors = dict(extractors)

    def preview(
        self,
        payload: TaskPreviewRequest,
        principal: Principal | None = None,
    ) -> TaskPreviewResponse:
        extractor = self.extractors.get(payload.intent)
        if extractor is None:
            raise TaskInputValidationError(
                TaskError(
                    code="PREVIEW_INTENT_NOT_SUPPORTED",
                    message=f"Preview does not support intent: {payload.intent}.",
                    step="preview",
                    details={"intent": payload.intent},
                )
            )
        if principal is None:
            return extractor.preview(payload)
        return extractor.preview(payload, principal)

    def validate_task(self, payload: TaskCreate) -> None:
        extractor = self.extractors.get(payload.intent)
        if extractor is not None:
            extractor.validate_task(payload)


__all__ = [
    "TaskInputDispatcher",
    "TaskInputExtractor",
    "TaskInputValidationError",
]
