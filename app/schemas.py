from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Any = ""


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(default="local-llama")
    messages: list[ChatMessage]
    temperature: float | None = Field(default=None)
    max_tokens: int | None = Field(default=None)
    stream: bool = Field(default=True)
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any | None = None
    user_id: str | None = None
    elevenlabs_extra_body: dict[str, Any] | None = None

    def provider_messages(self) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for message in self.messages:
            content = message.content
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text" and isinstance(item.get("text"), str):
                            parts.append(item["text"])
                        elif isinstance(item.get("content"), str):
                            parts.append(item["content"])
                    elif item is not None:
                        parts.append(str(item))
                text = "\n".join(parts)
            elif content is None:
                text = ""
            else:
                text = str(content)

            role = message.role
            if role in {"tool", "function"}:
                role = "user"
            normalized.append({"role": role, "content": text})
        return normalized
