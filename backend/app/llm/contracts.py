from collections.abc import Sequence
from typing import Annotated, Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
StructuredResponseT = TypeVar("StructuredResponseT", bound=BaseModel)


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["system", "user", "assistant"]
    content: NonEmptyStr


class LLMClientConfig(BaseModel):
    """Provider-neutral configuration passed to an LLM adapter."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: NonEmptyStr
    api_key: SecretStr
    base_url: NonEmptyStr
    model: NonEmptyStr
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    structured_output_mode: Literal["json_object", "prompt_only"]
    extra_body: dict[str, Any] = Field(default_factory=dict)


class LLMClientError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        provider: str,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.retryable = retryable


class LLMConfigurationError(LLMClientError):
    pass


class LLMResponseError(LLMClientError):
    pass


class StructuredLLMClient(Protocol):
    @property
    def provider(self) -> str:
        ...

    def generate_structured(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[StructuredResponseT],
    ) -> StructuredResponseT:
        ...
