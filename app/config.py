from functools import lru_cache
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


class Settings(BaseModel):
    llm_provider: str = Field(default="ollama")
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1:latest")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    backend_url: str = Field(default="http://localhost:8000")
    custom_llm_api_key: str = Field(default="")
    elevenlabs_api_key: str = Field(default="")
    elevenlabs_agent_id: str = Field(default="")


@lru_cache
def get_settings() -> Settings:
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "ollama").strip().lower(),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:latest"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        backend_url=os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/"),
        custom_llm_api_key=os.getenv("CUSTOM_LLM_API_KEY", ""),
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
        elevenlabs_agent_id=os.getenv("ELEVENLABS_AGENT_ID", ""),
    )
