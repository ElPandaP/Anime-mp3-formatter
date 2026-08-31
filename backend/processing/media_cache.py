"""Scratch space for audio that's been pulled from YouTube during playlist prep
but isn't a finished track yet.

Each track has an mp3/raw file plus a `<id>.json` sidecar recording its stage:

    status "raw"   - bestaudio downloaded, still needs the loudness pass
    status "done"  - <id>.mp3 is normalised and ready to tag

The directory lives under LOCALAPPDATA (temp dir as a fallback), never the
user's music folder, and is wiped on startup, on loading a new playlist, and on
exit. A prepped-but-never-downloaded track leaves nothing behind that the user
would ever see.
"""

import atexit
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

from config import CONFIG

_local = os.environ.get("LOCALAPPDATA")
CACHE_DIR = (
    Path(_local) / "AnimeMp3Formatter" / "cache" if _local
    else Path(tempfile.gettempdir()) / "anime-mp3-formatter-cache"
)
_MAX_BYTES = int(CONFIG["cache_max_mb"]) * 1024 * 1024
_lock = threading.Lock()


def mp3_path(video_id):
    return CACHE_DIR / f"{video_id}.mp3"


def _sidecar(video_id):
    return CACHE_DIR / f"{video_id}.json"


def read(video_id):
    try:
        return json.loads(_sidecar(video_id).read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def is_cached(video_id):
    return read(video_id).get("status") == "done" and mp3_path(video_id).exists()


def pending_raw(video_id):
    """The downloaded-but-not-normalised file, or None."""
    meta = read(video_id)
    if meta.get("status") != "raw":
        return None
    raw = CACHE_DIR / meta["raw_name"]
    return raw if raw.exists() else None


def any_audio(video_id):
    """Anything playable for a preview - the finished mp3, or the raw stage-1
    download (browsers handle webm/m4a/opus fine)."""
    return mp3_path(video_id) if mp3_path(video_id).exists() else pending_raw(video_id)


def has_audio(video_id):
    return any_audio(video_id) is not None


def description(video_id):
    return read(video_id).get("description", "")


def write_raw(video_id, raw_name, description, thumbnail_url):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _write(video_id, {
        "status": "raw",
        "raw_name": raw_name,
        "description": description or "",
        "thumbnail_url": thumbnail_url or "",
    })


def mark_done(video_id):
    meta = read(video_id)
    meta["status"] = "done"
    meta.pop("raw_name", None)
    with _lock:
        _write(video_id, meta)
        _enforce_cap()


def _write(video_id, meta):
    _sidecar(video_id).write_text(json.dumps(meta), "utf-8")


def clear_one(video_id):
    """Remove every file for a track (used before re-downloading a partial)."""
    for path in CACHE_DIR.glob(f"{video_id}.*"):
        path.unlink(missing_ok=True)


def clear_all():
    with _lock:
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _enforce_cap():
    audio = [f for f in CACHE_DIR.iterdir() if f.suffix != ".json"]
    total = sum(f.stat().st_size for f in audio)
    for f in sorted(audio, key=lambda p: p.stat().st_mtime):
        if total <= _MAX_BYTES:
            return
        total -= f.stat().st_size
        for sibling in CACHE_DIR.glob(f"{f.stem}.*"):
            sibling.unlink(missing_ok=True)


@atexit.register
def _wipe_on_exit():
    # Skip in the Werkzeug reloader's worker - it respawns on every code change.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
