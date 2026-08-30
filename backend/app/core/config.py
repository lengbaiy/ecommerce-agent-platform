import json
from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv

load_dotenv()



def _optional_float(name: str) -> float | None:
    value = getenv(name)
    return float(value) if value is not None else None


def _optional_int(name: str) -> int | None:
    value = getenv(name)
    return int(value) if value is not None else None


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
    task_lease_seconds: int = int(getenv("TASK_LEASE_SECONDS", "300"))
    auto_create_schema: bool = getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true"
    access_token_minutes: int = int(getenv("ACCESS_TOKEN_MINUTES", "480"))
    bootstrap_admin_tenant: str = getenv("BOOTSTRAP_ADMIN_TENANT", "local")
    bootstrap_admin_username: str = getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    bootstrap_admin_password: str = getenv("BOOTSTRAP_ADMIN_PASSWORD", "Admin@123456")

    market_max_product_limit: int = int(getenv("MARKET_MAX_PRODUCT_LIMIT", "50"))
    market_max_reviews_per_product: int = int(
        getenv("MARKET_MAX_REVIEWS_PER_PRODUCT", "50")
    )
    market_metric_upload_storage_root: str = getenv(
        "MARKET_METRIC_UPLOAD_STORAGE_ROOT",
        "./data/uploads/market_metrics",
    )
    market_metric_upload_max_bytes: int = int(
        getenv("MARKET_METRIC_UPLOAD_MAX_BYTES", str(5 * 1024 * 1024))
    )
    market_metric_upload_max_uncompressed_bytes: int = int(
        getenv("MARKET_METRIC_UPLOAD_MAX_UNCOMPRESSED_BYTES", str(50 * 1024 * 1024))
    )
    market_metric_upload_max_rows: int = int(
        getenv("MARKET_METRIC_UPLOAD_MAX_ROWS", "500")
    )

    llm_provider: str | None = getenv("LLM_PROVIDER")
    llm_api_key: str | None = getenv("LLM_API_KEY") or getenv("DASHSCOPE_API_KEY")
    llm_base_url: str | None = getenv("LLM_BASE_URL")
    llm_model: str | None = getenv("LLM_MODEL")
    llm_temperature: float | None = _optional_float("LLM_TEMPERATURE")
    llm_top_p: float | None = _optional_float("LLM_TOP_P")
    llm_max_tokens: int | None = _optional_int("LLM_MAX_TOKENS")
    llm_timeout_seconds: float = float(getenv("LLM_TIMEOUT_SECONDS", "60"))
    llm_max_retries: int = int(getenv("LLM_MAX_RETRIES", "2"))
    llm_structured_output_mode: str = getenv(
        "LLM_STRUCTURED_OUTPUT_MODE", "json_object"
    )
    llm_extra_body_json: str = getenv("LLM_EXTRA_BODY_JSON", "{}")
    review_llm_batch_size: int = int(getenv("REVIEW_LLM_BATCH_SIZE", "20"))
    review_llm_max_reviews: int = int(getenv("REVIEW_LLM_MAX_REVIEWS", "60"))
    review_llm_max_content_chars: int = int(
        getenv("REVIEW_LLM_MAX_CONTENT_CHARS", "8000")
    )
    review_llm_output_language: str = getenv(
        "REVIEW_LLM_OUTPUT_LANGUAGE", "zh-CN"
    )

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
        if self.task_lease_seconds < 30:
            raise RuntimeError("TASK_LEASE_SECONDS must be at least 30")
        if self.market_metric_upload_max_bytes < 1:
            raise RuntimeError("MARKET_METRIC_UPLOAD_MAX_BYTES must be positive")
        if (
            self.market_metric_upload_max_uncompressed_bytes
            < self.market_metric_upload_max_bytes
        ):
            raise RuntimeError(
                "MARKET_METRIC_UPLOAD_MAX_UNCOMPRESSED_BYTES must be at least "
                "MARKET_METRIC_UPLOAD_MAX_BYTES"
            )
        if self.market_metric_upload_max_rows < 1:
            raise RuntimeError("MARKET_METRIC_UPLOAD_MAX_ROWS must be positive")
        if self.auto_create_schema:
            raise RuntimeError(
                "AUTO_CREATE_SCHEMA=true is no longer supported; run Alembic migrations"
            )

        required_llm_settings = {
            "LLM_PROVIDER": self.llm_provider,
            "LLM_API_KEY": self.llm_api_key,
            "LLM_BASE_URL": self.llm_base_url,
            "LLM_MODEL": self.llm_model,
        }
        missing_llm_settings = [
            name
            for name, value in required_llm_settings.items()
            if value is None or not value.strip()
        ]
        if missing_llm_settings:
            raise RuntimeError(
                "Missing required LLM settings: "
                + ", ".join(missing_llm_settings)
            )

        if (
            self.llm_temperature is not None
            and not 0 <= self.llm_temperature <= 2
        ):
            raise RuntimeError("LLM_TEMPERATURE must be between 0 and 2")
        if (
            self.llm_top_p is not None
            and not 0 < self.llm_top_p <= 1
        ):
            raise RuntimeError("LLM_TOP_P must be greater than 0 and at most 1")
        if self.llm_max_tokens is not None and self.llm_max_tokens < 1:
            raise RuntimeError("LLM_MAX_TOKENS must be positive")
        if self.llm_timeout_seconds <= 0:
            raise RuntimeError("LLM_TIMEOUT_SECONDS must be positive")
        if self.llm_max_retries < 0:
            raise RuntimeError("LLM_MAX_RETRIES must not be negative")
        if self.llm_structured_output_mode not in {"json_object", "prompt_only"}:
            raise RuntimeError(
                "LLM_STRUCTURED_OUTPUT_MODE must be json_object or prompt_only"
            )
        if self.review_llm_batch_size < 1:
            raise RuntimeError("REVIEW_LLM_BATCH_SIZE must be positive")
        if self.review_llm_max_reviews < 1:
            raise RuntimeError("REVIEW_LLM_MAX_REVIEWS must be positive")
        if self.review_llm_max_content_chars < 1:
            raise RuntimeError("REVIEW_LLM_MAX_CONTENT_CHARS must be positive")
        if not self.review_llm_output_language.strip():
            raise RuntimeError("REVIEW_LLM_OUTPUT_LANGUAGE is required")

        try:
            llm_extra_body = json.loads(self.llm_extra_body_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM_EXTRA_BODY_JSON must be valid JSON") from exc
        if not isinstance(llm_extra_body, dict):
            raise RuntimeError("LLM_EXTRA_BODY_JSON must contain a JSON object")


settings = Settings()
