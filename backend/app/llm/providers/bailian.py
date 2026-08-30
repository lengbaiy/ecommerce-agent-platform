import json
from collections.abc import Sequence
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from app.llm.contracts import (
    LLMClientConfig,
    LLMClientError,
    LLMConfigurationError,
    LLMMessage,
    LLMResponseError,
    StructuredResponseT,
)


class BailianStructuredLLMClient:
    """Alibaba Cloud Model Studio adapter using its OpenAI-compatible API."""

    provider = "bailian"

    def __init__(self, config: LLMClientConfig) -> None:
        if config.provider.casefold() != self.provider:
            raise LLMConfigurationError(
                code="LLM_PROVIDER_MISMATCH",
                message=(
                    f"Bailian adapter cannot use provider {config.provider!r}."
                ),
                provider=self.provider,
                retryable=False,
            )

        self.config = config
        self.client = OpenAI(
            api_key=config.api_key.get_secret_value(),
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    def generate_structured(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[StructuredResponseT],
    ) -> StructuredResponseT:
        if not messages:
            raise LLMConfigurationError(
                code="LLM_MESSAGES_REQUIRED",
                message="At least one LLM message is required.",
                provider=self.provider,
                retryable=False,
            )

        request_messages = self._request_messages(
            messages=messages,
            response_model=response_model,
        )
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": request_messages,
        }

        if self.config.structured_output_mode == "json_object":
            request["response_format"] = {"type": "json_object"}

        optional_parameters = {
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.max_tokens,
        }
        request.update(
            {
                key: value
                for key, value in optional_parameters.items()
                if value is not None
            }
        )

        if self.config.extra_body:
            request["extra_body"] = self.config.extra_body

        try:
            completion = self.client.chat.completions.create(**request)
            content = completion.choices[0].message.content
        except AuthenticationError as exc:
            raise self._provider_error(
                code="LLM_AUTHENTICATION_FAILED",
                message="Bailian authentication failed.",
                retryable=False,
            ) from exc
        except RateLimitError as exc:
            raise self._provider_error(
                code="LLM_RATE_LIMITED",
                message="Bailian rate limit was reached.",
                retryable=True,
            ) from exc
        except APITimeoutError as exc:
            raise self._provider_error(
                code="LLM_TIMEOUT",
                message="Bailian request timed out.",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise self._provider_error(
                code="LLM_CONNECTION_FAILED",
                message="Bailian connection failed.",
                retryable=True,
            ) from exc
        except BadRequestError as exc:
            raise self._provider_error(
                code="LLM_BAD_REQUEST",
                message="Bailian rejected the generation request.",
                retryable=False,
            ) from exc
        except APIStatusError as exc:
            raise self._provider_error(
                code="LLM_PROVIDER_ERROR",
                message=f"Bailian returned HTTP status {exc.status_code}.",
                retryable=exc.status_code >= 500,
            ) from exc
        except (AttributeError, IndexError) as exc:
            raise LLMResponseError(
                code="LLM_INVALID_RESPONSE",
                message="Bailian returned an incomplete response.",
                provider=self.provider,
                retryable=False,
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError(
                code="LLM_EMPTY_RESPONSE",
                message="Bailian returned empty structured content.",
                provider=self.provider,
                retryable=False,
            )

        try:
            payload = self._decode_json_content(content)
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMResponseError(
                code="LLM_INVALID_JSON",
                message="Bailian output does not contain a valid JSON object.",
                provider=self.provider,
                retryable=False,
            ) from exc

        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            raise LLMResponseError(
                code="LLM_SCHEMA_MISMATCH",
                message="Bailian output does not match the requested schema.",
                provider=self.provider,
                retryable=False,
            ) from exc

    @staticmethod
    def _request_messages(
        *,
        messages: Sequence[LLMMessage],
        response_model: type[BaseModel],
    ) -> list[dict[str, str]]:
        schema = json.dumps(
            response_model.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        schema_instruction = (
            "Return one JSON object only. The JSON must conform exactly to "
            f"this JSON Schema: {schema}"
        )
        result = [
            {"role": message.role, "content": message.content}
            for message in messages
        ]

        if result and result[0]["role"] == "system":
            result[0]["content"] = (
                f"{result[0]['content']}\n\n{schema_instruction}"
            )
        else:
            result.insert(
                0,
                {"role": "system", "content": schema_instruction},
            )

        return result

    @staticmethod
    def _decode_json_content(content: str) -> dict[str, Any]:
        normalized = content.strip()
        if normalized.startswith("```") and normalized.endswith("```"):
            first_newline = normalized.find("\n")
            if first_newline != -1:
                normalized = normalized[first_newline + 1 : -3].strip()

        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            payload = BailianStructuredLLMClient._extract_json_object(normalized)

        # Some compatible endpoints wrap structured output in a single result field.
        if isinstance(payload, dict) and len(payload) == 1:
            key = next(iter(payload))
            if key in {"data", "result", "output", "response"}:
                payload = payload[key]
        if not isinstance(payload, dict):
            raise ValueError("Structured response must be a JSON object.")
        return payload

    @staticmethod
    def _extract_json_object(content: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        for index, character in enumerate(content):
            if character != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(content[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        raise ValueError("No JSON object found in structured response.")

    def _provider_error(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> LLMClientError:
        return LLMClientError(
            code=code,
            message=message,
            provider=self.provider,
            retryable=retryable,
        )
