import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.v1 import api_v1_router
from app.core import settings
from app.db import database_ready
from app.services.auth_service import AuthService


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info is not None:
            exception_type, exception, _ = record.exc_info
            payload.update(
                {
                    "exception_type": exception_type.__name__,
                    "exception": str(exception),
                    "traceback": self.formatException(record.exc_info),
                }
            )
        if record.stack_info:
            payload["stacktrace"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.validate()
    configure_logging()
    if settings.auth_mode == "password":
        AuthService().ensure_bootstrap_admin()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description=(
        "电商智能运营 Agent 平台 API。身份和租户上下文由服务端认证边界提供，"
        "高风险写操作必须通过具名审批并匹配结果快照。"
    ),
    openapi_tags=[
        {"name": "经营总览", "description": "经营指标、预警和审批概览。"},
        {"name": "Agent 任务", "description": "任务创建、状态、事件和取消。"},
        {"name": "审批", "description": "高风险写操作的人工审批。"},
        {"name": "市场宏观指标", "description": "宏观指标上传、系统审核和批次查询。"},
    ],
    lifespan=lifespan,
)
app.include_router(api_v1_router)
logger = logging.getLogger("app.http")


def _request_id(value: str | None) -> str:
    try:
        return str(UUID(value)) if value else str(uuid4())
    except ValueError:
        return str(uuid4())


@app.middleware("http")
async def request_context(request: Request, call_next) -> Response:
    request_id = _request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    started = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (perf_counter() - started) * 1000,
        request_id,
    )
    return response


@app.get("/health", tags=["平台"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready", tags=["平台"])
def readiness() -> Response:
    if database_ready():
        return JSONResponse({"status": "ready", "database": "ok"})
    return JSONResponse(
        {"status": "not_ready", "database": "unavailable"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
