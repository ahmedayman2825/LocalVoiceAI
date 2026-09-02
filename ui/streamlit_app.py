import os
from pathlib import Path
from typing import Any

import httpx
import streamlit as st
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
CUSTOM_LLM_API_KEY = os.getenv("CUSTOM_LLM_API_KEY", "")
CHAT_MODEL = os.getenv("CUSTOM_LLM_MODEL_ID", "local-llama")


def auth_headers() -> dict[str, str]:
    if not CUSTOM_LLM_API_KEY:
        return {}
    return {"Authorization": f"Bearer {CUSTOM_LLM_API_KEY}"}


def get_health() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{BACKEND_URL}/health")
            response.raise_for_status()
            return response.json(), None
    except httpx.RequestError:
        return None, "Backend is offline or BACKEND_URL is incorrect."
    except httpx.HTTPStatusError as exc:
        return None, f"Backend health check failed with HTTP {exc.response.status_code}."
    except ValueError:
        return None, "Backend returned an invalid health response."


def send_chat(messages: list[dict[str, str]]) -> tuple[str | None, str | None]:
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 500,
        "stream": False,
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{BACKEND_URL}/v1/chat/completions",
                json=payload,
                headers=auth_headers(),
            )
            response.raise_for_status()
            data = response.json()
    except httpx.RequestError:
        return None, "Could not reach the FastAPI backend."
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text
        return None, f"Backend returned HTTP {exc.response.status_code}: {detail}"
    except ValueError:
        return None, "Backend returned invalid JSON."

    try:
        return data["choices"][0]["message"]["content"], None
    except (KeyError, IndexError, TypeError):
        return None, "Backend response did not match the expected Chat Completions format."


st.set_page_config(page_title="Local Voice AI", layout="centered")

st.title("Local Voice AI")

if "messages" not in st.session_state:
    st.session_state.messages = []

health, health_error = get_health()

with st.sidebar:
    st.header("Status")
    st.caption(f"Backend: {BACKEND_URL}")

    if health_error:
        st.error("Backend offline")
        st.write(health_error)
        provider = os.getenv("LLM_PROVIDER", "unknown")
        model = os.getenv("OLLAMA_MODEL", "unknown")
    else:
        provider = health.get("provider", "unknown")
        model = health.get("model", "unknown")
        ollama = health.get("ollama", {})
        if health.get("status") == "ok":
            st.success("Backend online")
        elif ollama.get("reachable") and ollama.get("model_available") is False:
            st.warning("Ollama model issue")
            st.write(ollama.get("message"))
        else:
            st.warning("Ollama issue")
            st.write(ollama.get("message", "Provider health is degraded."))

    st.write(f"Provider: {provider}")
    st.write(f"Model: {model}")

    if st.button("Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

with st.form("chat_form", clear_on_submit=True):
    user_text = st.text_input("Message", placeholder="Type a message for the local LLM...")
    send = st.form_submit_button("Send", use_container_width=True)

if send and user_text.strip():
    st.session_state.messages.append({"role": "user", "content": user_text.strip()})
    with st.chat_message("user"):
        st.markdown(user_text.strip())

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            assistant_text, error = send_chat(st.session_state.messages)
        if error:
            st.error(error)
        else:
            st.markdown(assistant_text)
            st.session_state.messages.append({"role": "assistant", "content": assistant_text})
