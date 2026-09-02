from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


class LLMProviderError(Exception):
    """Base error for provider failures that should be safe to show to clients."""


class LLMConnectionError(LLMProviderError):
    """Raised when the configured LLM service cannot be reached."""


class LLMModelNotFoundError(LLMProviderError):
    """Raised when the configured model is unavailable."""


@dataclass
class ProviderHealth:
    reachable: bool
    model_available: bool | None
    message: str


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        raise NotImplementedError

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError
