"""A scratch area for audio pulled from YouTube during the playlist "prepare"
phase but not yet tagged and saved to the user's music folder.

Two stages leave two kinds of file here:
  <id>.<ext>       raw audio, downloaded but not yet normalised  (stage 1)
  <id>.pending.json  its description + thumbnail, waiting for stage 2
  <id>.mp3 + <id>.json   normalised + done; is_cached() is now true  (stage 2)

Nothing here is ever the user's output directory - it lives under LOCALAPPDATA
(or the system temp dir as a fallback) and is wiped on startup, whenever a new
playlist is loaded, and on exit. So a prepared-but-never-downloaded track never
leaves a half-finished file anywhere the user would see it; the music folder
only ever receives a fully finalised mp3.
"""

import atexit
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

_LOCAL = os.environ.get("LOCALAPPDATA")
CACHE_DIR = (
    Path(_LOCAL) / "AnimeMp3Formatter" / "cache"
    if _LOCAL
    else Path(tempfile.gettempdir()) / "anime-mp3-formatter-cache"
)

# Keep the scratch area from growing without bound if a user prepares several
# large segments across a session without ever downloading. Oldest entries are
# evicted first.
MAX_CACHE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB

_lock = threading.Lock()


def _mp3_path(video_id):
    return CACHE_DIR / f"{video_id}.mp3"


def _meta_path(video_id):
    return CACHE_DIR / f"{video_id}.json"


def _pending_path(video_id):
    return CACHE_DIR / f"{video_id}.pending.json"


def cache_mp3_path(video_id):
    return _mp3_path(video_id)


def is_cached(video_id):
    """A track counts as cached only when both the normalised mp3 and its
    metadata sidecar exist - the sidecar is written last, so it doubles as a
    "finished" marker that a crash mid-download/normalise can't fake."""
    return _mp3_path(video_id).exists() and _meta_path(video_id).exists()


def read_meta(video_id):
    try:
        return json.loads(_meta_path(video_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# --- stage 1: raw audio waiting to be normalised ----------------------------

def pending_raw_path(video_id):
    """Path to the downloaded-but-not-normalised audio, or None."""
    pending = read_pending(video_id)
    if not pending:
        return None
    raw = CACHE_DIR / pending["raw_name"]
    return raw if raw.exists() else None


def get_description(video_id):
    """The video's description from wherever we last stashed it - the pending
    sidecar (stage 1) or the final meta (stage 2)."""
    return read_meta(video_id).get("description") or read_pending(video_id).get("description") or ""


def read_pending(video_id):
    try:
        return json.loads(_pending_path(video_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def mark_pending(video_id, raw_name, description, thumbnail_url):
    with _lock:
        _pending_path(video_id).write_text(
            json.dumps({
                "raw_name": raw_name,
                "description": description or "",
                "thumbnail_url": thumbnail_url or "",
            }),
            encoding="utf-8",
        )


def clear_pending(video_id):
    try:
        _pending_path(video_id).unlink()
    except OSError:
        pass


def any_audio_path(video_id):
    """Something playable for this track - the finished mp3 if we have it,
    otherwise the raw stage-1 download (browsers play webm/m4a/opus fine)."""
    if _mp3_path(video_id).exists():
        return _mp3_path(video_id)
    return pending_raw_path(video_id)


def has_audio(video_id):
    return any_audio_path(video_id) is not None


# --- stage 2: normalised + done --------------------------------------------

def clear_partial(video_id):
    """Drop every leftover file for a track that isn't fully cached, so a
    fresh download starts clean."""
    if is_cached(video_id):
        return
    for path in CACHE_DIR.glob(f"{video_id}.*"):
        try:
            path.unlink()
        except OSError:
            pass


def store(video_id, description, thumbnail_url):
    """Record that <video_id>.mp3 is present and normalised. Call this after the
    mp3 is in place; it writes the sidecar that makes is_cached() true."""
    with _lock:
        _meta_path(video_id).write_text(
            json.dumps({"description": description or "", "thumbnail_url": thumbnail_url or ""}),
            encoding="utf-8",
        )
        _enforce_size_cap_locked()


def _enforce_size_cap_locked():
    entries = []
    total = 0
    for f in CACHE_DIR.iterdir():
        if f.suffix == ".json":
            continue
        try:
            stat = f.stat()
        except OSError:
            continue
        total += stat.st_size
        entries.append((stat.st_mtime, stat.st_size, f))
    if total <= MAX_CACHE_BYTES:
        return
    for _mtime, size, f in sorted(entries):
        stem = f.name.split(".")[0]
        for path in CACHE_DIR.glob(f"{stem}.*"):
            try:
                path.unlink()
            except OSError:
                pass
        total -= size
        if total <= MAX_CACHE_BYTES:
            return


def ensure_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def clear_cache():
    """Wipe everything. Safe to call when the dir doesn't exist yet."""
    with _lock:
        try:
            shutil.rmtree(CACHE_DIR, ignore_errors=True)
        finally:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _wipe_on_exit():
    # Only the top-level process should wipe on exit - not the Werkzeug debug
    # reloader's worker, which exits and respawns on every code change.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        shutil.rmtree(CACHE_DIR, ignore_errors=True)


atexit.register(_wipe_on_exit)
