import json
from typing import Any

from app.core.config import Settings
from app.llm.providers.bailian import BailianStructuredLLMClient
from app.llm.contracts import (
    LLMClientConfig,
    LLMConfigurationError,
    StructuredLLMClient,
)


def build_structured_llm_client(settings: Settings) -> StructuredLLMClient:
    provider = _required_setting("LLM_PROVIDER", settings.llm_provider)
    config = LLMClientConfig(
        provider=provider,
        api_key=_required_setting("LLM_API_KEY", settings.llm_api_key),
        base_url=_required_setting("LLM_BASE_URL", settings.llm_base_url),
        model=_required_setting("LLM_MODEL", settings.llm_model),
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
        # Graph owns retries so each failed request produces one observable attempt.
        max_retries=0,
        structured_output_mode=settings.llm_structured_output_mode,
        extra_body=_parse_extra_body(settings.llm_extra_body_json),
    )

    if provider.casefold() == BailianStructuredLLMClient.provider:
        return BailianStructuredLLMClient(config)

    raise LLMConfigurationError(
        code="LLM_PROVIDER_UNSUPPORTED",
        message=f"Unsupported LLM provider: {provider}.",
        provider=provider,
        retryable=False,
    )


def _required_setting(name: str, value: str | None) -> str:
    if value is None or not value.strip():
        raise LLMConfigurationError(
            code="LLM_CONFIGURATION_INVALID",
            message=f"{name} is required.",
            provider="unconfigured",
            retryable=False,
        )
    return value.strip()


def _parse_extra_body(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise LLMConfigurationError(
            code="LLM_CONFIGURATION_INVALID",
            message="LLM_EXTRA_BODY_JSON must be valid JSON.",
            provider="unconfigured",
            retryable=False,
        ) from exc

    if not isinstance(payload, dict):
        raise LLMConfigurationError(
            code="LLM_CONFIGURATION_INVALID",
            message="LLM_EXTRA_BODY_JSON must contain a JSON object.",
            provider="unconfigured",
            retryable=False,
        )

    return payload
