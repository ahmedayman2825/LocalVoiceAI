<<<<<<< HEAD
# Local Voice AI

Local Voice AI is a small MVP for using ElevenLabs as the voice interface while your own FastAPI backend acts as the AI brain.

ElevenLabs handles speech-to-text, turn-taking, text-to-speech, and playback. This project exposes an OpenAI-compatible Chat Completions endpoint that ElevenLabs can call. The current LLM provider is Ollama with `llama3.1:latest`, but the provider layer is separated so you can later add OpenAI, Anthropic, Gemini, or another local model without rewriting the ElevenLabs-facing API.

## Architecture

```text
User speaks
  -> ElevenLabs Agent
  -> FastAPI Custom LLM server
  -> LLM provider abstraction
  -> Ollama
  -> FastAPI streams OpenAI-compatible SSE chunks
  -> ElevenLabs turns text into speech
```

The Streamlit UI is only for testing and monitoring. It does not do speech recognition or text-to-speech.

```text
Streamlit UI
  -> FastAPI API
  -> LLM Provider
  -> Ollama
```

## Project Structure

```text
LocalVoiceAI/
|-- app/
|   |-- __init__.py
|   |-- main.py
|   |-- config.py
|   |-- schemas.py
|   `-- llm/
|       |-- __init__.py
|       |-- base.py
|       `-- ollama_provider.py
|-- ui/
|   `-- streamlit_app.py
|-- .env.example
|-- requirements.txt
|-- README.md
`-- .gitignore
```

## Setup on Windows PowerShell

Open PowerShell and go to the project:

```powershell
cd E:\work\LocalVoiceAI
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once for the current shell:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Copy the environment example:

```powershell
Copy-Item .env.example .env
```

The default `.env` values are:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:latest
HOST=0.0.0.0
PORT=8000
BACKEND_URL=http://localhost:8000
CUSTOM_LLM_API_KEY=
```

## Verify Ollama

Make sure Ollama is installed and running. Then check the available models:

```powershell
ollama list
```

Expected model:

```text
llama3.1:latest
```

If it is missing, pull it:

```powershell
ollama pull llama3.1:latest
```

## Start the FastAPI Backend

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Test health in a second PowerShell window:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected successful response:

```json
{
  "status": "ok",
  "provider": "ollama",
  "model": "llama3.1:latest"
}
```

The actual response also includes Ollama reachability and model availability details.

## Test Chat Completions

Non-streaming test:

```powershell
$body = @{
  model = "local-llama"
  messages = @(
    @{ role = "system"; content = "You are a helpful assistant." },
    @{ role = "user"; content = "Say hello in one short sentence." }
  )
  temperature = 0.7
  max_tokens = 100
  stream = $false
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri http://localhost:8000/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Streaming test:

```powershell
$body = @{
  model = "local-llama"
  messages = @(
    @{ role = "user"; content = "Count from one to three." }
  )
  stream = $true
} | ConvertTo-Json -Depth 10

curl.exe -N `
  -H "Content-Type: application/json" `
  -d $body `
  http://localhost:8000/v1/chat/completions
```

Streaming responses use `Content-Type: text/event-stream`, emit `data: {JSON}` chunks, and finish with:

```text
data: [DONE]
```

## Optional API Key

By default, authentication is disabled:

```env
CUSTOM_LLM_API_KEY=
```

To enable it, set a secret:

```env
CUSTOM_LLM_API_KEY=your-secret-here
```

Then requests to `POST /v1/chat/completions` must include:

```text
Authorization: Bearer your-secret-here
```

`GET /health` never requires authentication.

The Streamlit UI reads the same `CUSTOM_LLM_API_KEY` from `.env` and sends it to the backend automatically.

## Start the Streamlit UI

In a second PowerShell window, with the virtual environment activated:

```powershell
cd E:\work\LocalVoiceAI
.\.venv\Scripts\Activate.ps1
streamlit run ui/streamlit_app.py
```

Open the URL Streamlit prints, usually:

```text
http://localhost:8501
```

Use the chat interface to test the backend without ElevenLabs. The UI sends the full conversation history to FastAPI with `stream: false`.

## ElevenLabs Custom LLM Setup

This project does not require an ElevenLabs API key. ElevenLabs acts as the client.

After the backend works locally, expose it publicly with ngrok:

```powershell
ngrok http 8000
```

Use the public ngrok URL in ElevenLabs Custom LLM configuration.

Example base URL:

```text
https://YOUR-NGROK-URL.ngrok-free.app/v1
```

Configure ElevenLabs with:

```text
API type: Chat Completions
Model ID: local-llama
Endpoint called by ElevenLabs: /v1/chat/completions
```

If `CUSTOM_LLM_API_KEY` is enabled, configure the same bearer token secret in ElevenLabs.

## Endpoints

### GET /health

Returns backend, provider, Ollama reachability, and model availability status.

### POST /v1/chat/completions

OpenAI-compatible Chat Completions endpoint for ElevenLabs Custom LLM.

Supported request fields include:

```json
{
  "model": "local-llama",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello"}
  ],
  "temperature": 0.7,
  "max_tokens": 500,
  "stream": true
}
```

Unknown optional fields are accepted and ignored safely, including `tools`, `tool_choice`, `user_id`, and `elevenlabs_extra_body`.

## Notes

- Do not install or configure the OpenAI Python SDK.
- Do not set an OpenAI API key.
- Do not set an ElevenLabs API key for this backend.
- ElevenLabs handles voice.
- FastAPI handles the Custom LLM API.
- Ollama is the current model provider.
- Streamlit is only a testing and monitoring UI.
=======
# LocalVoiceAI
>>>>>>> 69191e6e84179471c3490e5c32b123f38f812d48
