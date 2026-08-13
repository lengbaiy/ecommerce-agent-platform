from datetime import UTC, datetime, timedelta
from secrets import randbelow
from uuid import uuid4

import jwt
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import settings
from app.core.security import ROLE_PERMISSIONS, Principal, permissions_for_roles, unauthorized
from app.db.models import AuthSessionRecord, CaptchaChallengeRecord, UserAccountRecord
from app.db.session import SessionFactory

password_hasher = PasswordHash.recommended()


class LoginRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    captcha_id: str
    slider_position: int | None = Field(default=None, ge=0, le=1000)


class UserCreateRequest(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9._-]{3,64}$")
    display_name: str = Field(min_length=1, max_length=96)
    password: str = Field(min_length=10, max_length=128)
    roles: list[str] = Field(min_length=1)


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=96)
    roles: list[str] | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)


class AuthService:
    def ensure_bootstrap_admin(self) -> None:
        with SessionFactory() as session:
            existing = session.scalar(
                select(UserAccountRecord).where(
                    UserAccountRecord.tenant_id == settings.bootstrap_admin_tenant,
                    UserAccountRecord.username == settings.bootstrap_admin_username,
                )
            )
            if existing is not None:
                return
            session.add(
                UserAccountRecord(
                    tenant_id=settings.bootstrap_admin_tenant,
                    username=settings.bootstrap_admin_username,
                    display_name="平台管理员",
                    password_hash=password_hasher.hash(settings.bootstrap_admin_password),
                    roles=["admin"],
                )
            )
            session.commit()

    def create_captcha(self) -> dict:
        challenge_id = str(uuid4())
        target_x = 68 + randbelow(210)
        now = datetime.now(UTC)
        with SessionFactory() as session:
            session.add(
                CaptchaChallengeRecord(
                    id=challenge_id,
                    target_x=target_x,
                    created_at=now,
                    expires_at=now + timedelta(minutes=2),
                )
            )
            session.commit()
        return {
            "provider": "local_puzzle",
            "captcha_id": challenge_id,
            "track_length": 100,
            "canvas_width": 350,
            "canvas_height": 150,
            "puzzle_offset": target_x,
            "expires_in": 120,
        }

    def login(self, payload: LoginRequest) -> dict:
        now = datetime.now(UTC)
        with SessionFactory() as session:
            challenge = session.get(CaptchaChallengeRecord, payload.captcha_id)
            if (
                challenge is None
                or challenge.login_consumed
                or challenge.expires_at.replace(tzinfo=UTC) < now
            ):
                raise unauthorized("slider challenge is missing, expired or already used")
            challenge.login_consumed = True
            challenge.attempts += 1
            if (
                payload.slider_position is None
                or abs(challenge.target_x - payload.slider_position) > 4
            ):
                session.commit()
                raise unauthorized("slider verification failed")
            challenge.verified = True

            user = session.scalar(
                select(UserAccountRecord).where(
                    UserAccountRecord.tenant_id == payload.tenant_id,
                    UserAccountRecord.username == payload.username,
                )
            )
            if user is None or not user.enabled:
                session.commit()
                raise unauthorized("invalid username or password")
            locked_until = user.locked_until.replace(tzinfo=UTC) if user.locked_until else None
            if locked_until and locked_until > now:
                session.commit()
                raise unauthorized("account is temporarily locked")
            if not password_hasher.verify(payload.password, user.password_hash):
                user.failed_attempts += 1
                if user.failed_attempts >= 5:
                    user.locked_until = now + timedelta(minutes=15)
                    user.failed_attempts = 0
                session.commit()
                raise unauthorized("invalid username or password")

            user.failed_attempts = 0
            user.locked_until = None
            user.last_login_at = now
            session_id = str(uuid4())
            expires_at = now + timedelta(minutes=settings.access_token_minutes)
            session.add(
                AuthSessionRecord(
                    id=session_id,
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    created_at=now,
                    expires_at=expires_at,
                )
            )
            session.commit()
            roles = list(user.roles or [])
            token = jwt.encode(
                {
                    "sub": user.id,
                    "tenant_id": user.tenant_id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "roles": roles,
                    "jti": session_id,
                    "iat": now,
                    "exp": expires_at,
                    **({"iss": settings.jwt_issuer} if settings.jwt_issuer else {}),
                    **({"aud": settings.jwt_audience} if settings.jwt_audience else {}),
                },
                settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
            )
            return {
                "access_token": token,
                "token_type": "bearer",
                "expires_in": settings.access_token_minutes * 60,
                "user": self._serialize_user(user),
            }

    def session_active(self, session_id: str, tenant_id: str, user_id: str) -> bool:
        now = datetime.now(UTC)
        with SessionFactory() as session:
            auth_session = session.get(AuthSessionRecord, session_id)
            user = session.get(UserAccountRecord, user_id)
            return bool(
                auth_session
                and user
                and user.enabled
                and user.tenant_id == tenant_id
                and auth_session.tenant_id == tenant_id
                and auth_session.user_id == user_id
                and not auth_session.revoked
                and auth_session.expires_at.replace(tzinfo=UTC) > now
            )

    def logout(self, principal: Principal) -> None:
        if settings.auth_mode != "password" or not principal.session_id:
            return
        with SessionFactory() as session:
            auth_session = session.get(AuthSessionRecord, principal.session_id)
            if auth_session is not None:
                auth_session.revoked = True
                session.commit()

    def list_users(self, principal: Principal) -> list[dict]:
        with SessionFactory() as session:
            users = session.scalars(
                select(UserAccountRecord)
                .where(UserAccountRecord.tenant_id == principal.tenant_id)
                .order_by(UserAccountRecord.created_at)
            )
            return [self._serialize_user(user) for user in users]

    def create_user(self, payload: UserCreateRequest, principal: Principal) -> dict:
        self._validate_roles(payload.roles)
        with SessionFactory() as session:
            existing = session.scalar(
                select(UserAccountRecord).where(
                    UserAccountRecord.tenant_id == principal.tenant_id,
                    UserAccountRecord.username == payload.username,
                )
            )
            if existing is not None:
                raise ValueError("username already exists")
            user = UserAccountRecord(
                tenant_id=principal.tenant_id,
                username=payload.username,
                display_name=payload.display_name,
                password_hash=password_hasher.hash(payload.password),
                roles=sorted(set(payload.roles)),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return self._serialize_user(user)

    def update_user(self, user_id: str, payload: UserUpdateRequest, principal: Principal) -> dict:
        with SessionFactory() as session:
            user = session.scalar(
                select(UserAccountRecord).where(
                    UserAccountRecord.id == user_id,
                    UserAccountRecord.tenant_id == principal.tenant_id,
                )
            )
            if user is None:
                raise KeyError("user not found")
            if payload.roles is not None:
                self._validate_roles(payload.roles)
                if user.id == principal.user_id and "admin" not in payload.roles:
                    raise ValueError("you cannot remove your own admin role")
                self._guard_last_admin(session, user, roles=payload.roles)
                user.roles = sorted(set(payload.roles))
            if payload.display_name is not None:
                user.display_name = payload.display_name
            if payload.enabled is not None:
                if user.id == principal.user_id and not payload.enabled:
                    raise ValueError("you cannot disable your own account")
                if not payload.enabled:
                    self._guard_last_admin(session, user, enabled=False)
                user.enabled = payload.enabled
            if payload.password is not None:
                user.password_hash = password_hasher.hash(payload.password)
                user.failed_attempts = 0
                user.locked_until = None
            if (
                payload.roles is not None
                or payload.enabled is not None
                or payload.password is not None
            ):
                active_sessions = session.scalars(
                    select(AuthSessionRecord).where(
                        AuthSessionRecord.tenant_id == principal.tenant_id,
                        AuthSessionRecord.user_id == user.id,
                        AuthSessionRecord.revoked.is_(False),
                    )
                )
                for auth_session in active_sessions:
                    auth_session.revoked = True
            session.commit()
            return self._serialize_user(user)

    @staticmethod
    def _guard_last_admin(
        session,
        user: UserAccountRecord,
        roles: list[str] | None = None,
        enabled: bool | None = None,
    ) -> None:
        remains_admin = "admin" in (roles if roles is not None else user.roles)
        remains_enabled = enabled if enabled is not None else user.enabled
        if "admin" not in user.roles or (remains_admin and remains_enabled):
            return
        tenant_users = session.scalars(
            select(UserAccountRecord).where(UserAccountRecord.tenant_id == user.tenant_id)
        )
        other_admin_exists = any(
            candidate.id != user.id and candidate.enabled and "admin" in candidate.roles
            for candidate in tenant_users
        )
        if not other_admin_exists:
            raise ValueError("the tenant must keep at least one enabled admin")

    @staticmethod
    def _validate_roles(roles: list[str]) -> None:
        unknown = set(roles) - ROLE_PERMISSIONS.keys()
        if unknown:
            raise ValueError(f"unknown roles: {', '.join(sorted(unknown))}")

    @staticmethod
    def _serialize_user(user: UserAccountRecord) -> dict:
        roles = list(user.roles or [])
        return {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "username": user.username,
            "display_name": user.display_name,
            "roles": roles,
            "permissions": sorted(permissions_for_roles(roles)),
            "enabled": user.enabled,
            "last_login_at": user.last_login_at,
        }
