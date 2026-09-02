import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.llm.base import (
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMProvider,
    LLMProviderError,
    ProviderHealth,
)


logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = httpx.Timeout(timeout_seconds, connect=5.0)

    async def health_check(self) -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except httpx.RequestError:
            return ProviderHealth(
                reachable=False,
                model_available=None,
                message="Ollama is not reachable. Confirm it is running and OLLAMA_BASE_URL is correct.",
            )
        except httpx.HTTPStatusError as exc:
            return ProviderHealth(
                reachable=False,
                model_available=None,
                message=f"Ollama health request failed with HTTP {exc.response.status_code}.",
            )
        except ValueError:
            return ProviderHealth(
                reachable=False,
                model_available=None,
                message="Ollama returned an invalid health response.",
            )

        models = payload.get("models", [])
        names = {item.get("name") for item in models if isinstance(item, dict)}
        model_available = self.model in names
        if model_available:
            return ProviderHealth(reachable=True, model_available=True, message="Ollama is reachable.")
        return ProviderHealth(
            reachable=True,
            model_available=False,
            message=f"Ollama is reachable, but model '{self.model}' was not found.",
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload = self._build_payload(messages, stream=False, temperature=temperature, max_tokens=max_tokens)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                await self._raise_for_status(response)
                data = response.json()
        except httpx.RequestError as exc:
            logger.warning("Ollama request failed: %s", exc.__class__.__name__)
            raise LLMConnectionError("Could not connect to Ollama. Is Ollama running?") from exc
        except ValueError as exc:
            raise LLMProviderError("Ollama returned an invalid JSON response.") from exc

        message = data.get("message", {})
        content = message.get("content", "")
        if not isinstance(content, str):
            raise LLMProviderError("Ollama response did not contain assistant text.")
        return content

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(messages, stream=True, temperature=temperature, max_tokens=max_tokens)
        logger.info(
            "Starting Ollama stream. url=%s model=%s message_count=%s",
            f"{self.base_url}/api/chat",
            self.model,
            len(messages),
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    logger.info("Ollama stream response status=%s", response.status_code)
                    await self._raise_for_status(response)
                    async for line in response.aiter_lines():
                        logger.info("Ollama raw stream line: %s", line)
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            logger.exception("Skipping invalid Ollama stream line.")
                            continue

                        logger.info("Ollama parsed stream JSON: %s", json.dumps(data, ensure_ascii=False))
                        if data.get("done"):
                            logger.info("Ollama stream received done=true.")
                            break

                        message = data.get("message", {})
                        content = message.get("content", "")
                        logger.info("Ollama extracted content chunk: %r", content)
                        if content:
                            yield content
        except httpx.RequestError as exc:
            logger.exception("Ollama stream request failed: %s", exc.__class__.__name__)
            raise LLMConnectionError("Could not connect to Ollama. Is Ollama running?") from exc
        except Exception:
            logger.exception("Unexpected Ollama stream failure.")
            raise

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        stream: bool,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": "24h",
        }

        options: dict = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options

        return payload

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        detail = ""
        body = await response.aread()
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
            detail = str(payload.get("error", ""))
        except (UnicodeDecodeError, ValueError):
            detail = body.decode("utf-8", errors="replace")

        if response.status_code == 404 or "not found" in detail.lower():
            raise LLMModelNotFoundError(
                f"Ollama model '{self.model}' was not found. Run: ollama pull {self.model}"
            )

        raise LLMProviderError(f"Ollama returned HTTP {response.status_code}: {detail or 'unknown error'}")
