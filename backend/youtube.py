import re
import shutil
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

FFMPEG_LOCATION = shutil.which("ffmpeg")

# yt-dlp error fragments that mean "YouTube is throttling this IP / demanding a
# login" rather than anything being wrong with the video itself. Recoverable:
# wait a few minutes (or add cookies) and retry.
_RATE_LIMIT_MARKERS = (
    "confirm you're not a bot",
    "confirm you’re not a bot",  # curly apostrophe variant
    "sign in to confirm you're not a bot",
    "sign in to confirm you’re not a bot",
    "http error 429",
    "too many requests",
    "429: too many requests",
)

# Fragments that mean the video is gone / unplayable for everyone - skip it,
# don't retry, don't count it as a real failure.
_UNAVAILABLE_MARKERS = (
    "private video",
    "video unavailable",
    "video is unavailable",
    "this video is not available",
    "video has been removed",
    "no longer available",
    "account associated with this video has been terminated",
    "has blocked it on copyright grounds",
    "who has blocked it",
    "content is not available on this app",
    "members-only content",
    "join this channel to get access",
    "sign in to confirm your age",  # age-restricted - unplayable without cookies
    "confirm your age",
    "inappropriate for some users",
    "removed for violating youtube's",
    "is not available in your country",
    "made this video available in your country",  # "uploader has not made this video available in your country"
    "this live event will begin",
    "premieres in",
)


class RateLimitedError(Exception):
    """YouTube served an anti-bot / HTTP 429 wall. Back off and retry later."""


class VideoUnavailableError(Exception):
    """The video is private, deleted, copyright-blocked or otherwise unplayable."""


def _video_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def _base_opts(**extra):
    """Shared yt-dlp options. Every call in this module goes through here so
    throttling / ffmpeg location are configured in exactly one place."""
    opts = {
        "quiet": True,
        "noprogress": True,
        # Light in-extract pacing. The real spacing for a big playlist comes
        # from the frontend running these one at a time with a gap between
        # tracks (see PlaylistTab), so no need to also stall inside each call.
        "sleep_interval_requests": 1,
        "retries": 5,
        "extractor_retries": 3,
    }
    if FFMPEG_LOCATION:
        opts["ffmpeg_location"] = FFMPEG_LOCATION
    opts.update(extra)
    return opts


def _raise_classified(exc):
    """Re-raise a yt-dlp error as RateLimitedError / VideoUnavailableError when
    the message matches a known pattern; otherwise let the original propagate."""
    message = str(exc)
    low = message.lower()
    if any(marker in low for marker in _RATE_LIMIT_MARKERS):
        raise RateLimitedError(message) from exc
    if any(marker in low for marker in _UNAVAILABLE_MARKERS):
        raise VideoUnavailableError(message) from exc


def _extract(opts, target, download=False):
    try:
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(target, download=download)
    except (DownloadError, ExtractorError) as exc:
        _raise_classified(exc)
        raise


# --- Playlist / search listing -------------------------------------------------

_UNAVAILABLE_ENTRY_TITLES = {
    "[private video]",
    "[deleted video]",
    "[unavailable video]",
    "[removed video]",
}


def entry_is_available(entry):
    """Filter for flat playlist/search entries: drop the placeholder rows
    YouTube leaves behind for private/deleted videos so they never reach the
    tag/download pipeline."""
    if not entry or not entry.get("id"):
        return False
    title = (entry.get("title") or "").strip().lower()
    # A flat playlist entry with no title at all is a fully-removed video -
    # YouTube returns just the id and nulls the rest. (Copyright-blocked videos
    # whose watch page still exists keep their cached title and can't be caught
    # here; they surface later when a real request hits the video.)
    if not title:
        return False
    if title in _UNAVAILABLE_ENTRY_TITLES:
        return False
    if entry.get("availability") in ("private", "needs_auth", "premium_only", "subscriber_only"):
        return False
    return True


def search_entries(query, limit=8):
    opts = _base_opts(noplaylist=True, extract_flat="in_playlist")
    info = _extract(opts, f"ytsearch{limit}:{query}", download=False)
    return [e for e in (info.get("entries") or []) if entry_is_available(e)]


def playlist_entries(url):
    """Returns (playlist_title, available_entries, skipped_count)."""
    opts = _base_opts(extract_flat="in_playlist")
    info = _extract(opts, url, download=False)
    entries = info.get("entries") or []
    available = [e for e in entries if entry_is_available(e)]
    return info.get("title", ""), available, len(entries) - len(available)


# --- Single video ------------------------------------------------------------

def get_audio_stream_url(video_id):
    opts = _base_opts(format="bestaudio/best", noplaylist=True)
    info = _extract(opts, _video_url(video_id), download=False)

    stream_url = info.get("url")
    if not stream_url and info.get("requested_formats"):
        stream_url = info["requested_formats"][0].get("url")
    return stream_url


def download_audio(video_id, work_dir, to_mp3=True):
    """Download the best audio track. With to_mp3 (default) yt-dlp transcodes it
    to a 192k mp3; without, the raw bestaudio file is kept as-is (the caller
    transcodes later, e.g. folded into a loudness pass). Returns
    (downloaded_path, thumbnail_url, description) - the description comes free
    from the same extract, so a caller here needs no separate request."""
    opts = _base_opts(
        format="bestaudio/best",
        outtmpl=str(work_dir / "%(id)s.%(ext)s"),
        noplaylist=True,
    )
    if to_mp3:
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ]
    info = _extract(opts, _video_url(video_id), download=True)

    downloads = info.get("requested_downloads") or []
    if downloads and downloads[0].get("filepath"):
        out_path = Path(downloads[0]["filepath"])
    else:
        ext = "mp3" if to_mp3 else info.get("ext", "webm")
        out_path = work_dir / f"{info['id']}.{ext}"
    thumbnail_url = info.get("thumbnail")
    description = info.get("description") or ""
    return out_path, thumbnail_url, description


def get_video_description(video_id):
    opts = _base_opts(skip_download=True, noplaylist=True)
    info = _extract(opts, _video_url(video_id), download=False)
    return info.get("description") or ""
