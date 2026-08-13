from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class Settings:
    app_name: str = "E-commerce Operations Intelligence Agent API"
    environment: str = getenv("APP_ENV", "local")
    database_url: str = getenv("DATABASE_URL", "sqlite:///./ecommerce_agent.db")
    redis_url: str = getenv("REDIS_URL", "redis://localhost:6379/0")
    qdrant_url: str = getenv("QDRANT_URL", "http://localhost:6333")
    object_storage_endpoint: str = getenv("MINIO_ENDPOINT", "localhost:9000")
    auth_mode: str = getenv("AUTH_MODE", "password")
    jwt_secret: str | None = getenv(
        "JWT_SECRET", "local-development-session-secret-change-before-production"
    )
    jwt_algorithm: str = getenv("JWT_ALGORITHM", "HS256")
    jwt_issuer: str | None = getenv("JWT_ISSUER")
    jwt_audience: str | None = getenv("JWT_AUDIENCE")
    task_execution_mode: str = getenv("TASK_EXECUTION_MODE", "inline")
    auto_create_schema: bool = getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true"
    access_token_minutes: int = int(getenv("ACCESS_TOKEN_MINUTES", "480"))
    bootstrap_admin_tenant: str = getenv("BOOTSTRAP_ADMIN_TENANT", "local")
    bootstrap_admin_username: str = getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    bootstrap_admin_password: str = getenv("BOOTSTRAP_ADMIN_PASSWORD", "Admin@123456")

    def validate(self) -> None:
        if self.auth_mode not in {"password", "jwt"}:
            raise RuntimeError("AUTH_MODE must be 'password' or 'jwt'")
        if not self.jwt_secret:
            raise RuntimeError("JWT_SECRET is required")
        if self.jwt_algorithm not in {"HS256", "HS384", "HS512"}:
            raise RuntimeError("JWT_ALGORITHM must be HS256, HS384 or HS512")
        if self.jwt_secret and len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must contain at least 32 characters")
        if self.environment.lower() in {"production", "prod"}:
            if self.jwt_secret.startswith("local-development-"):
                raise RuntimeError("the development JWT secret is forbidden in production")
            if self.bootstrap_admin_password == "Admin@123456":
                raise RuntimeError("the default bootstrap password is forbidden in production")
            if self.auth_mode == "jwt" and (not self.jwt_issuer or not self.jwt_audience):
                raise RuntimeError("JWT_ISSUER and JWT_AUDIENCE are required in production")
        if self.task_execution_mode not in {"inline", "worker"}:
            raise RuntimeError("TASK_EXECUTION_MODE must be 'inline' or 'worker'")
        if self.environment.lower() in {"production", "prod"} and self.auto_create_schema:
            raise RuntimeError("AUTO_CREATE_SCHEMA=true is forbidden in production; run Alembic")


settings = Settings()
