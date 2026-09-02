import hmac
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.llm.base import LLMModelNotFoundError, LLMProvider, LLMProviderError
from app.llm.ollama_provider import OllamaProvider
from app.schemas import ChatCompletionRequest


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Local Voice AI", version="0.1.0")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.exception_handler(RequestValidationError)
async def log_request_validation_error(request: Request, exc: RequestValidationError):
    body = await request.body()
    logger.exception(
        "Request validation failed. path=%s headers=%s body=%s errors=%s",
        request.url.path,
        _safe_headers(request),
        _safe_decode(body),
        exc.errors(),
    )
    return await request_validation_exception_handler(request, exc)


def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    if settings.llm_provider == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Unsupported LLM_PROVIDER '{settings.llm_provider}'.",
    )


def require_api_key(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected_key = settings.custom_llm_api_key
    if not expected_key:
        return

    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    provided_key = authorization[len(prefix) :]
    if not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.")

@app.get("/", include_in_schema=False)
async def root_page() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/api/conversation/signed-url")
async def get_signed_url(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return a temporary signed WebSocket URL or agent ID for ElevenLabs Conversational AI.

    If an ELEVENLABS_API_KEY with convai_write permissions is provided, returns signed_url.
    Otherwise falls back to agent_id for direct public/allowlisted agent connection.
    """
    if not settings.elevenlabs_agent_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ELEVENLABS_AGENT_ID is not configured on the server.",
        )

    if settings.elevenlabs_api_key:
        try:
            url = f"https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?agent_id={settings.elevenlabs_agent_id}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers={"xi-api-key": settings.elevenlabs_api_key})

            if resp.status_code == 200:
                data = resp.json()
                return {"signed_url": data.get("signed_url"), "agent_id": settings.elevenlabs_agent_id}
            
            logger.warning(
                "Could not generate signed URL from ElevenLabs (HTTP %s: %s). Falling back to direct agent_id.",
                resp.status_code,
                resp.text,
            )
        except Exception as exc:
            logger.warning("Error fetching signed URL: %s. Falling back to direct agent_id.", exc)

    return {"agent_id": settings.elevenlabs_agent_id}


@app.get("/health")
async def health(
    settings: Settings = Depends(get_settings),
    provider: LLMProvider = Depends(get_llm_provider),
) -> dict[str, Any]:
    provider_health = await provider.health_check()
    status_value = "ok" if provider_health.reachable and provider_health.model_available is not False else "degraded"
    return {
        "status": status_value,
        "provider": settings.llm_provider,
        "model": settings.ollama_model,
        "ollama": {
            "base_url": settings.ollama_base_url,
            "reachable": provider_health.reachable,
            "model_available": provider_health.model_available,
            "message": provider_health.message,
        },
    }


@app.get("/v1")
async def v1_status() -> dict[str, str]:
    return {
        "status": "ok",
        "object": "api",
        "message": "OpenAI-compatible API is available",
    }


@app.get("/v1/models")
async def v1_models(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": "local-llama",
                "object": "model",
                "created": 1700000000,
                "owned_by": settings.llm_provider,
            },
            {
                "id": settings.ollama_model,
                "object": "model",
                "created": 1700000000,
                "owned_by": settings.llm_provider,
            },
        ],
    }


@app.post("/v1/chat/completions", dependencies=[Depends(require_api_key)], response_model=None)
async def chat_completions(
    raw_request: Request,
    request: ChatCompletionRequest,
    provider: LLMProvider = Depends(get_llm_provider),
) -> JSONResponse | StreamingResponse:
    raw_body = await raw_request.body()
    logger.info("Incoming /v1/chat/completions headers: %s", _safe_headers(raw_request))
    logger.info("Incoming /v1/chat/completions raw body: %s", _safe_decode(raw_body))
    logger.info("Parsed /v1/chat/completions body: %s", json.dumps(request.model_dump(mode="json"), ensure_ascii=False))
    logger.info("Incoming /v1/chat/completions stream=%s", request.stream)

    if not request.messages:
        logger.error("Invalid chat completion request: messages must not be empty.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="messages must not be empty.")

    if request.stream:
        return StreamingResponse(
            _openai_stream(request=request, provider=provider),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        content = await provider.chat(
            messages=request.provider_messages(),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except LLMModelNotFoundError as exc:
        logger.exception("Configured model was not found.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LLMProviderError as exc:
        logger.exception("LLM provider error: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error while handling non-streaming chat completion.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error.") from exc

    response_body = _completion_response(request=request, content=content)
    logger.info("Outgoing /v1/chat/completions non-streaming body: %s", json.dumps(response_body, ensure_ascii=False))
    return JSONResponse(response_body)


async def _openai_stream(request: ChatCompletionRequest, provider: LLMProvider) -> AsyncIterator[str]:
    chat_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    logger.info("Generating streaming response. id=%s model=%s stream=%s", chat_id, request.model, request.stream)

    first_chunk = _sse(
        {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "finish_reason": None,
                }
            ],
        }
    )
    logger.info("Outgoing stream chunk: %s", first_chunk.rstrip())
    yield first_chunk

    try:
        async for token in provider.stream_chat(
            messages=request.provider_messages(),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        ):
            token_chunk = _sse(
                {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": token},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            logger.info("Outgoing stream chunk: %s", token_chunk.rstrip())
            yield token_chunk

        final_chunk = _sse(
            {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
            }
        )
        logger.info("Outgoing stream chunk: %s", final_chunk.rstrip())
        yield final_chunk

        if _include_stream_usage(request):
            usage_chunk = _sse(
                {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    },
                }
            )
            logger.info("Outgoing stream chunk: %s", usage_chunk.rstrip())
            yield usage_chunk

        done_chunk = "data: [DONE]\n\n"
        logger.info("Outgoing stream chunk: %s", done_chunk.rstrip())
        yield done_chunk
    except LLMProviderError as exc:
        logger.exception("LLM streaming error: %s", exc)
        error_chunk = _sse({"error": {"message": str(exc), "type": "llm_provider_error"}})
        logger.info("Outgoing stream chunk: %s", error_chunk.rstrip())
        yield error_chunk

        done_chunk = "data: [DONE]\n\n"
        logger.info("Outgoing stream chunk: %s", done_chunk.rstrip())
        yield done_chunk
    except Exception:
        logger.exception("Unexpected error while handling streaming chat completion.")
        error_chunk = _sse({"error": {"message": "Internal server error.", "type": "server_error"}})
        logger.info("Outgoing stream chunk: %s", error_chunk.rstrip())
        yield error_chunk

        done_chunk = "data: [DONE]\n\n"
        logger.info("Outgoing stream chunk: %s", done_chunk.rstrip())
        yield done_chunk


def _completion_response(request: ChatCompletionRequest, content: str) -> dict[str, Any]:
    usage = _estimate_usage(request=request, content=content)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _include_stream_usage(request: ChatCompletionRequest) -> bool:
    stream_options = request.model_extra.get("stream_options") if request.model_extra else None
    if not isinstance(stream_options, dict):
        return False
    return stream_options.get("include_usage") is True


def _estimate_usage(request: ChatCompletionRequest, content: str) -> dict[str, int]:
    prompt_text = " ".join(message["content"] for message in request.provider_messages())
    prompt_tokens = _rough_token_count(prompt_text)
    completion_tokens = _rough_token_count(content)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _rough_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text.split()))


def _safe_headers(request: Request) -> dict[str, str]:
    sensitive_names = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"}
    safe: dict[str, str] = {}
    for name, value in request.headers.items():
        if name.lower() in sensitive_names:
            safe[name] = "[REDACTED]"
        else:
            safe[name] = value
    return safe


def _safe_decode(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")
