"""Talks to any OpenAI-compatible "chat completions" API - Anthropic, a
local Ollama, Kimi/Moonshot, DeepSeek, OpenRouter, etc. Swap providers by
only changing the three LLM_* values in .env, no code changes needed."""

import json
import os
import re
import time
import urllib.request
from collections import deque
from pathlib import Path

from dotenv import load_dotenv

# Loaded explicitly (rather than relying on load_dotenv()'s default search
# from the current working directory) so it works the same whether the app
# is started from inside backend/ or from the repo root.
load_dotenv(Path(__file__).resolve().parent / ".env")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5")

# Hard safety cap: no matter what triggers calls to the AI endpoint (a bug,
# a runaway retry, whatever), it can never place more than this many
# requests in a rolling minute. Bulk playlist processing legitimately needs
# one call per song, so this is generous rather than tight - it's here to
# catch a runaway loop, not to throttle normal use.
AI_GUESS_RATE_LIMIT = 60
AI_GUESS_RATE_WINDOW_SECONDS = 60
_ai_guess_call_times = deque()


def ai_guess_rate_limit_ok():
    now = time.time()
    while _ai_guess_call_times and now - _ai_guess_call_times[0] > AI_GUESS_RATE_WINDOW_SECONDS:
        _ai_guess_call_times.popleft()
    if len(_ai_guess_call_times) >= AI_GUESS_RATE_LIMIT:
        return False
    _ai_guess_call_times.append(now)
    return True


def call_llm(prompt):
    if not LLM_API_KEY:
        raise RuntimeError("AI parsing is not configured (set LLM_API_KEY in .env)")

    body = json.dumps(
        {
            "model": LLM_MODEL,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{LLM_BASE_URL}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def extract_json(content, opener, closer):
    content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
    start, end = content.find(opener), content.rfind(closer)
    if start == -1 or end == -1:
        raise ValueError("AI response did not contain the expected JSON")
    return json.loads(content[start : end + 1])
