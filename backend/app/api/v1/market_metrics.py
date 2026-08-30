from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import ValidationError

from app.api.dependencies import (
    get_market_metric_file_service,
    get_market_metric_query_service,
    get_market_metric_upload_service,
)
from app.core.security import (
    MarketMetricReadDependency,
    MarketMetricWriteDependency,
)
from app.modules.market_intelligence.schemas import (
    MarketMetricBatchCreate,
    MarketMetricBatchCandidateList,
    MarketMetricBatchDetail,
    MarketMetricBatchList,
    MarketMetricBatchStatus,
    MarketMetricUploadContext,
    MarketMetricUploadRequest,
    MarketMetricUploadResult,
)
from app.services import (
    MarketMetricFileError,
    MarketMetricFileService,
    MarketMetricQueryService,
    MarketMetricUploadConflictError,
    MarketMetricUploadService,
)


router = APIRouter(
    prefix="/market-intelligence/market-metrics",
    tags=["市场宏观指标"],
)
UploadServiceDependency = Annotated[
    MarketMetricUploadService,
    Depends(get_market_metric_upload_service),
]
QueryServiceDependency = Annotated[
    MarketMetricQueryService,
    Depends(get_market_metric_query_service),
]
FileServiceDependency = Annotated[
    MarketMetricFileService,
    Depends(get_market_metric_file_service),
]


@router.post(
    "",
    response_model=MarketMetricUploadResult,
    status_code=status.HTTP_201_CREATED,
)
def upload_market_metrics(
    request: Request,
    upload_service: UploadServiceDependency,
    file_service: FileServiceDependency,
    principal: MarketMetricWriteDependency,
    batch: Annotated[str, Form(min_length=2, max_length=20_000)],
    file: Annotated[UploadFile, File()],
) -> MarketMetricUploadResult:
    try:
        batch_contract = MarketMetricBatchCreate.model_validate_json(batch)
    except ValidationError as exc:
        raise _http_error(
            422,
            "MARKET_METRIC_BATCH_INVALID",
            "批次范围或来源信息无效。",
            _validation_errors(exc),
        ) from exc

    if file.filename and len(file.filename) > 255:
        raise _http_error(422, "UPLOAD_FILENAME_TOO_LONG", "上传文件名过长。")
    try:
        content = file.file.read(file_service.max_bytes + 1)
    except OSError as exc:
        raise _http_error(500, "UPLOAD_FILE_READ_FAILED", "读取上传文件失败。") from exc
    finally:
        file.file.close()
    try:
        parsed = file_service.ingest(
            tenant_id=principal.tenant_id,
            filename=file.filename,
            content_type=file.content_type,
            content=content,
        )
    except MarketMetricFileError as exc:
        raise _file_http_error(exc) from exc

    try:
        upload_request = MarketMetricUploadRequest(
            batch=batch_contract,
            metrics=parsed.metrics,
        )
        return upload_service.upload(
            context=MarketMetricUploadContext(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                trace_id=str(getattr(request.state, "request_id", None) or uuid4()),
            ),
            request=upload_request,
            stored_file=parsed.stored_file,
        )
    except MarketMetricUploadConflictError as exc:
        file_service.discard(parsed.stored_file)
        raise _http_error(409, "MARKET_METRIC_UPLOAD_CONFLICT", str(exc)) from exc
    except (ValidationError, ValueError) as exc:
        file_service.discard(parsed.stored_file)
        errors = _validation_errors(exc) if isinstance(exc, ValidationError) else None
        raise _http_error(
            422,
            "MARKET_METRIC_UPLOAD_INVALID",
            str(exc),
            errors,
        ) from exc
    except Exception:
        file_service.discard(parsed.stored_file)
        raise


@router.get("", response_model=MarketMetricBatchList)
def list_market_metric_batches(
    service: QueryServiceDependency,
    principal: MarketMetricReadDependency,
    batch_status: Annotated[
        MarketMetricBatchStatus | None,
        Query(alias="status"),
    ] = None,
    platform: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    market: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MarketMetricBatchList:
    return service.list_batches(
        tenant_id=principal.tenant_id,
        status=batch_status,
        platform=platform,
        market=market,
        limit=limit,
        offset=offset,
    )


@router.get("/candidates", response_model=MarketMetricBatchCandidateList)
def list_market_metric_candidates(
    service: QueryServiceDependency,
    principal: MarketMetricReadDependency,
    platform: Annotated[str, Query(min_length=1, max_length=64)],
    market: Annotated[str, Query(min_length=1, max_length=32)],
    category: Annotated[str, Query(min_length=1, max_length=128)],
    keyword: Annotated[str, Query(min_length=1, max_length=256)],
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
) -> MarketMetricBatchCandidateList:
    return service.list_candidates(
        tenant_id=principal.tenant_id,
        platform=platform,
        market=market,
        category=category,
        keyword=keyword,
        limit=limit,
    )


@router.get("/{batch_id}", response_model=MarketMetricBatchDetail)
def get_market_metric_batch(
    batch_id: str,
    service: QueryServiceDependency,
    principal: MarketMetricReadDependency,
) -> MarketMetricBatchDetail:
    try:
        return service.get_batch(batch_id=batch_id, tenant_id=principal.tenant_id)
    except KeyError as exc:
        raise _http_error(404, "MARKET_METRIC_BATCH_NOT_FOUND", "指标批次不存在。") from exc


def _file_http_error(error: MarketMetricFileError) -> HTTPException:
    if error.code == "UPLOAD_FILE_TOO_LARGE":
        status_code = status.HTTP_413_CONTENT_TOO_LARGE
    elif error.code in {"UNSUPPORTED_FILE_TYPE", "CONTENT_TYPE_MISMATCH"}:
        status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif error.code == "UPLOAD_FILE_STORAGE_FAILED":
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    return _http_error(status_code, error.code, str(error))


def _http_error(
    status_code: int,
    code: str,
    message: str,
    errors: list[dict] | None = None,
) -> HTTPException:
    detail: dict = {"code": code, "message": message}
    if errors:
        detail["errors"] = errors
    return HTTPException(status_code=status_code, detail=detail)


def _validation_errors(error: ValidationError) -> list[dict]:
    return [
        {
            "location": [str(part) for part in item["loc"]],
            "message": item["msg"],
            "type": item["type"],
        }
        for item in error.errors(include_url=False)
    ]


__all__ = ["router"]
