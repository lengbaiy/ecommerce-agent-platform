from collections.abc import Callable
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.core.config import Settings, settings

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "operator": frozenset(
        {
            "dashboard:read",
            "task:read",
            "task:create",
            "task:cancel",
            "market_metric:read",
            "market_metric:write",
        }
    ),
    "approver": frozenset(
        {"dashboard:read", "task:read", "approval:decide", "market_metric:read"}
    ),
    "admin": frozenset(
        {
            "dashboard:read",
            "task:read",
            "task:create",
            "task:cancel",
            "approval:decide",
            "user:read",
            "user:write",
            "market_metric:read",
            "market_metric:write",
        }
    ),
}


class Principal(BaseModel):
    tenant_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    username: str | None = None
    display_name: str | None = None
    roles: frozenset[str] = Field(default_factory=frozenset)
    permissions: frozenset[str] = Field(default_factory=frozenset)
    session_id: str | None = None

    def has_any_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


bearer_scheme = HTTPBearer(auto_error=False)


def permissions_for_roles(roles: list[str] | frozenset[str]) -> frozenset[str]:
    permissions: set[str] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS.get(role, frozenset()))
    return frozenset(permissions)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_jwt_principal(token: str, configuration: Settings = settings) -> Principal:
    options = {"require": ["exp", "sub", "tenant_id", "jti"]}
    claims: dict[str, Any] = jwt.decode(
        token,
        configuration.jwt_secret,
        algorithms=[configuration.jwt_algorithm],
        issuer=configuration.jwt_issuer,
        audience=configuration.jwt_audience,
        options=options,
    )
    raw_roles = claims.get("roles", [])
    if isinstance(raw_roles, str):
        raw_roles = [role.strip() for role in raw_roles.split(",")]
    roles = frozenset(str(role) for role in raw_roles)
    return Principal(
        tenant_id=str(claims["tenant_id"]),
        user_id=str(claims["sub"]),
        username=str(claims.get("username") or claims["sub"]),
        display_name=str(claims.get("display_name") or claims.get("username") or claims["sub"]),
        roles=roles,
        permissions=permissions_for_roles(roles),
        session_id=str(claims["jti"]),
    )


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized("bearer token is required")
    try:
        principal = decode_jwt_principal(credentials.credentials)
    except jwt.PyJWTError as error:
        raise unauthorized("invalid bearer token") from error

    if settings.auth_mode == "password":
        from app.services.auth_service import AuthService

        if not principal.session_id or not AuthService().session_active(
            principal.session_id, principal.tenant_id, principal.user_id
        ):
            raise unauthorized("session is expired or revoked")
    return principal


PrincipalDependency = Annotated[Principal, Depends(get_current_principal)]


def require_permission(permission: str) -> Callable[[PrincipalDependency], Principal]:
    def dependency(principal: PrincipalDependency) -> Principal:
        if not principal.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"permission is required: {permission}",
            )
        return principal

    return dependency


TaskReadDependency = Annotated[Principal, Depends(require_permission("task:read"))]
TaskCreateDependency = Annotated[Principal, Depends(require_permission("task:create"))]
TaskCancelDependency = Annotated[Principal, Depends(require_permission("task:cancel"))]
DashboardDependency = Annotated[Principal, Depends(require_permission("dashboard:read"))]
ApproverDependency = Annotated[Principal, Depends(require_permission("approval:decide"))]
UserReadDependency = Annotated[Principal, Depends(require_permission("user:read"))]
UserWriteDependency = Annotated[Principal, Depends(require_permission("user:write"))]
MarketMetricReadDependency = Annotated[
    Principal,
    Depends(require_permission("market_metric:read")),
]
MarketMetricWriteDependency = Annotated[
    Principal,
    Depends(require_permission("market_metric:write")),
]
