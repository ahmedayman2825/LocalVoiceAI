import { Conversation } from "@elevenlabs/client";

// ── DOM Elements ─────────────────────────────────────────────
const statusDot       = document.getElementById("status-dot");
const statusText      = document.getElementById("status-text");
const micButton       = document.getElementById("mic-button");
const modeText        = document.getElementById("mode-text");
const btnStart        = document.getElementById("btn-start");
const btnEnd          = document.getElementById("btn-end");
const transcript      = document.getElementById("transcript");
const placeholder     = document.getElementById("transcript-placeholder");

let conversation = null;

// ── UI Helpers ───────────────────────────────────────────────

function setConnectionStatus(state, text) {
    statusDot.className = "status-dot " + state;   // "", "connecting", "connected", "error"
    statusText.textContent = text;
}

function setMode(mode) {
    micButton.className = "mic-button " + mode;     // "", "listening", "speaking"
    modeText.className  = "mode-text "  + mode;

    const labels = {
        listening:  "Listening...",
        speaking:   "Speaking...",
        connecting: "Connecting...",
        "":         conversation ? "Connected" : "Click Start to begin",
    };
    modeText.textContent = labels[mode] ?? mode;
}

function addMessage(role, text) {
    if (!text || !text.trim()) return;

    // Hide the placeholder on first real message
    if (placeholder) placeholder.style.display = "none";

    const msg = document.createElement("div");
    msg.classList.add("message", role === "user" ? "user" : "ai");

    const label = document.createElement("div");
    label.classList.add("label");
    label.textContent = role === "user" ? "You" : "AI";

    const body = document.createElement("div");
    body.textContent = text;

    msg.appendChild(label);
    msg.appendChild(body);
    transcript.appendChild(msg);
    transcript.scrollTop = transcript.scrollHeight;
}

function resetUI() {
    conversation = null;
    setConnectionStatus("", "Disconnected");
    setMode("");
    btnStart.disabled  = false;
    btnEnd.disabled    = true;
    micButton.disabled = true;
}

// ── Connection Config ─────────────────────────────────────────

async function fetchConnectionConfig() {
    const res = await fetch("/api/conversation/signed-url");
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server returned ${res.status}`);
    }
    return await res.json();
}

// ── Start / End ──────────────────────────────────────────────

btnStart.addEventListener("click", async () => {
    btnStart.disabled = true;
    setConnectionStatus("connecting", "Connecting...");
    setMode("connecting");

    try {
        // Request microphone permission first
        await navigator.mediaDevices.getUserMedia({ audio: true });

        // Get connection config from our backend (signed URL or agent ID)
        const config = await fetchConnectionConfig();

        const sessionOptions = {
            onConnect: ({ conversationId }) => {
                console.log("Connected:", conversationId);
                setConnectionStatus("connected", "Connected");
                setMode("listening");
                micButton.disabled = false;
                btnEnd.disabled    = false;
            },

            onDisconnect: () => {
                console.log("Disconnected");
                resetUI();
            },

            onModeChange: (mode) => {
                const m = typeof mode === "object" ? mode.mode : mode;
                console.log("Mode:", m);
                setMode(m === "speaking" ? "speaking" : "listening");
            },

            onMessage: (message) => {
                console.log("Message:", message);

                if (message.source === "user" || message.type === "user_transcript") {
                    const text = message.message
                        || message.user_transcription_event?.user_transcript
                        || message.user_transcript
                        || "";
                    addMessage("user", text);
                } else if (message.source === "ai" || message.type === "agent_response") {
                    const text = message.message
                        || message.agent_response_event?.agent_response
                        || message.agent_response
                        || "";
                    addMessage("ai", text);
                }
            },

            onStatusChange: (status) => {
                console.log("Status:", status);
                if (typeof status === "object") status = status.status;

                if (status === "connected") {
                    setConnectionStatus("connected", "Connected");
                } else if (status === "connecting") {
                    setConnectionStatus("connecting", "Connecting...");
                } else if (status === "disconnected") {
                    resetUI();
                }
            },

            onError: (error) => {
                console.error("Conversation error:", error);
                const msg = typeof error === "string" ? error : error?.message || "Unknown error";
                setConnectionStatus("error", "Error: " + msg);
                setMode("");
            },
        };

        if (config.signed_url) {
            sessionOptions.signedUrl = config.signed_url;
        } else if (config.agent_id) {
            sessionOptions.agentId = config.agent_id;
        } else {
            throw new Error("No signed URL or Agent ID configured on the server.");
        }

        // Start the ElevenLabs conversation session
        conversation = await Conversation.startSession(sessionOptions);
    } catch (err) {
        console.error("Failed to start conversation:", err);
        setConnectionStatus("error", "Error: " + err.message);
        setMode("");
        btnStart.disabled = false;
    }
});

btnEnd.addEventListener("click", async () => {
    btnEnd.disabled = true;
    if (conversation) {
        try {
            await conversation.endSession();
        } catch (err) {
            console.error("Error ending session:", err);
        }
    }
    resetUI();
});
