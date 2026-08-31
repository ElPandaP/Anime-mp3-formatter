"""Settings live in one place: backend/config.json. It's committed with every
knob at its default and a comment on each; edit and restart. The only value the
app itself writes back is output_dir (from the folder picker)."""

import json
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_OUTPUT_DIR = str(Path.home() / "Music" / "AnimeMp3")

DEFAULTS = {
    "output_dir": "",  # blank -> ~/Music/AnimeMp3

    # Playlist prep. Lane 1 (fetch) is the only part that talks to YouTube; a
    # burst of parallel yt-dlp calls is what trips its anti-bot wall.
    "fetch_concurrency": 2,
    "prep_gap_ms": 800,
    "tags_concurrency": 3,
    "normalize_concurrency": 2,
    "download_concurrency": 2,
    "segment_size": 50,

    # yt-dlp
    "yt_sleep_interval_requests": 1,
    "yt_retries": 5,
    "yt_extractor_retries": 3,

    # Misc
    "cache_max_mb": 2048,
    "ai_rate_limit_per_min": 60,

    # Audio output
    "loudnorm_i": -14.0,
    "loudnorm_tp": -1.5,
    "loudnorm_lra": 11.0,
    "mp3_quality": 2,
}

# What GET /api/settings hands to the browser - it only drives the playlist UI.
_FRONTEND_KEYS = (
    "fetch_concurrency", "prep_gap_ms", "tags_concurrency",
    "normalize_concurrency", "download_concurrency", "segment_size",
)


def _strip_comments(text):
    """config.json is JSONC: `//` comments, no trailing commas. Drop the
    comments (but not a `//` that's inside a string) before parsing."""
    out, i, in_string = [], 0, False
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            in_string = not in_string
        if not in_string and ch == "/" and text[i : i + 2] == "//":
            i = text.find("\n", i)
            if i == -1:
                break
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def load():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(_strip_comments(CONFIG_PATH.read_text("utf-8"))))
    except (OSError, json.JSONDecodeError):
        pass
    cfg["output_dir"] = cfg.get("output_dir") or DEFAULT_OUTPUT_DIR
    return cfg


# Read once at import; modules keep a reference and re-read via save().
CONFIG = load()


def frontend_config():
    return {key: CONFIG[key] for key in _FRONTEND_KEYS}


def save_output_dir(path):
    """Rewrite just the output_dir line so the comments in config.json survive."""
    text = CONFIG_PATH.read_text("utf-8")
    text = re.sub(r'("output_dir"\s*:\s*)"[^"]*"', lambda m: m.group(1) + json.dumps(path), text, count=1)
    CONFIG_PATH.write_text(text, "utf-8")
    CONFIG.clear()
    CONFIG.update(load())
