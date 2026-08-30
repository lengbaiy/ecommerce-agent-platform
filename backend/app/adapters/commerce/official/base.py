from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.adapters.commerce.commerce_adapter_base import AdapterContext, AdapterError
from app.modules.market_intelligence.schemas import DataSourceMode


class OfficialApiAuthorizationProvider(Protocol):
    """按租户提供官方 API 授权信息，调用方不得记录返回内容。"""

    def is_authorized(self, tenant_id: str, platform: str) -> bool: ...

    def authorization_headers(
        self,
        tenant_id: str,
        platform: str,
    ) -> Mapping[str, str]: ...


@dataclass(frozen=True)
class OfficialApiResponse:
    status_code: int
    headers: Mapping[str, str]
    payload: Mapping[str, Any]


class OfficialApiTransport(Protocol):
    """隔离具体 HTTP SDK，便于统一处理超时、限流和平台错误。"""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        timeout_seconds: float,
    ) -> OfficialApiResponse: ...


class OfficialApiAdapter(ABC):
    """具体平台 Adapter 的公共依赖和授权入口。"""

    data_source_mode = DataSourceMode.OFFICIAL_API.value

    def __init__(
        self,
        *,
        authorization: OfficialApiAuthorizationProvider,
        transport: OfficialApiTransport,
    ) -> None:
        self.authorization = authorization
        self.transport = transport

    def authorization_headers(self, context: AdapterContext) -> Mapping[str, str]:
        if not self.is_authorized(context.tenant_id):
            raise AdapterError(
                "API_PERMISSION_DENIED",
                f"Tenant is not authorized for official platform: {self.platform}.",
            )
        return self.authorization.authorization_headers(
            context.tenant_id,
            self.platform,
        )

    def is_authorized(self, tenant_id: str) -> bool:
        return self.authorization.is_authorized(tenant_id, self.platform)

    @property
    @abstractmethod
    def platform(self) -> str:
        ...


__all__ = [
    "OfficialApiAdapter",
    "OfficialApiAuthorizationProvider",
    "OfficialApiResponse",
    "OfficialApiTransport",
]
