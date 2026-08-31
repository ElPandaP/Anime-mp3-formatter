"""A tiny client for any OpenAI-compatible /chat/completions endpoint - a local
Ollama, Anthropic, DeepSeek, OpenRouter, whatever. Point the three LLM_* vars in
.env at your provider and nothing else changes."""

import json
import os
import re
import threading
import time
import urllib.request
from collections import deque

from dotenv import load_dotenv

from config import APP_DIR, CONFIG

# Explicit path so it doesn't matter whether the app was started from backend/
# or the repo root.
load_dotenv(APP_DIR / ".env")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5")

# A backstop, not a throttle: one call per song is expected, but a runaway loop
# or retry storm should never get past this many in a rolling minute.
_MAX_CALLS_PER_MINUTE = int(CONFIG["ai_rate_limit_per_min"])
_call_times = deque()
_lock = threading.Lock()


def ai_guess_rate_limit_ok():
    now = time.time()
    with _lock:
        while _call_times and now - _call_times[0] > 60:
            _call_times.popleft()
        if len(_call_times) >= _MAX_CALLS_PER_MINUTE:
            return False
        _call_times.append(now)
        return True


def call_llm(prompt):
    if not LLM_API_KEY:
        raise RuntimeError("AI parsing is not configured (set LLM_API_KEY in .env)")

    body = json.dumps({
        "model": LLM_MODEL,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{LLM_BASE_URL}/chat/completions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {LLM_API_KEY}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def extract_json(reply):
    """Pull the JSON object out of a model reply, tolerating ```json fences and
    any stray prose around it."""
    reply = re.sub(r"^```(?:json)?|```$", "", reply, flags=re.MULTILINE).strip()
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in the model reply")
    return json.loads(reply[start : end + 1])
