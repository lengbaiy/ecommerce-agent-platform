from fastapi import APIRouter, HTTPException, status

from app.core.security import (
    Principal,
    PrincipalDependency,
    UserReadDependency,
    UserWriteDependency,
)
from app.services.auth_service import (
    AuthService,
    LoginRequest,
    UserCreateRequest,
    UserUpdateRequest,
)

router = APIRouter(prefix="/auth", tags=["身份与权限"])


@router.post("/captcha", status_code=status.HTTP_201_CREATED)
def create_captcha() -> dict:
    return AuthService().create_captcha()


@router.post("/login")
def login(payload: LoginRequest) -> dict:
    return AuthService().login(payload)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(principal: PrincipalDependency) -> None:
    AuthService().logout(principal)


@router.get("/me")
def me(principal: PrincipalDependency) -> Principal:
    return principal


@router.get("/users")
def list_users(principal: UserReadDependency) -> dict:
    users = AuthService().list_users(principal)
    return {"items": users, "total": len(users)}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateRequest, principal: UserWriteDependency) -> dict:
    try:
        return AuthService().create_user(payload, principal)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    principal: UserWriteDependency,
) -> dict:
    try:
        return AuthService().update_user(user_id, payload, principal)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
