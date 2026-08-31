"""Turning a YouTube video into a finished, tagged mp3.

Playlist prep splits the work into stages so YouTube isn't the bottleneck:

    prefetch_audio   - download the raw audio (the only step that hits YouTube)
    normalize_cached - loudness pass -> <id>.mp3  (no network, runs in parallel)
    finalize_download - tag + move into the music folder  (no network)

A one-off download from the search tab runs the same three steps back to back.
"""

import io
import shutil
import subprocess
import threading
import urllib.request
from collections import defaultdict
from pathlib import Path

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1
from mutagen.mp3 import MP3
from PIL import Image

from config import CONFIG
from sources.catalog import DESKTOP_USER_AGENT
from sources.youtube import FFMPEG_LOCATION, download_audio
from text import build_display_title, sanitize_filename

from . import media_cache

COVER_SIZE = 640

# One lock per video id, so the background normalise queue and a download that
# reaches the same track first don't both run ffmpeg on it.
_normalize_locks = defaultdict(threading.Lock)


def to_square_jpeg(image_data):
    """Center-crop any source image (portrait poster, square album art, 16:9
    thumbnail) to a square and resize, so every cover comes out consistent."""
    with Image.open(io.BytesIO(image_data)) as img:
        img = img.convert("RGB")
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w - side) // 2, (h - side) // 2,
                        (w - side) // 2 + side, (h - side) // 2 + side))
        img = img.resize((COVER_SIZE, COVER_SIZE), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()


def loudnorm_to_mp3(src_path, dst_path):
    """The single transcode in the pipeline: normalise loudness and encode to
    mp3 in one ffmpeg pass, raw download straight in."""
    ffmpeg = FFMPEG_LOCATION or "ffmpeg"
    tmp = dst_path.with_name(dst_path.stem + ".norm.mp3")
    subprocess.run(
        [
            ffmpeg, "-y", "-i", str(src_path),
            "-af", f"loudnorm=I={CONFIG['loudnorm_i']}:TP={CONFIG['loudnorm_tp']}:LRA={CONFIG['loudnorm_lra']}",
            "-ar", "44100", "-codec:a", "libmp3lame", "-q:a", str(CONFIG["mp3_quality"]),
            str(tmp),
        ],
        check=True, capture_output=True,
    )
    tmp.replace(dst_path)


def tag_mp3(mp3_path, display_title, artist, anime, cover_url):
    audio = MP3(mp3_path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()

    # UTF-16, not UTF-8: we save as ID3v2.3 (below) for Spotify local-files
    # support, and v2.3 text frames only allow Latin-1 or UTF-16.
    audio.tags.setall("TIT2", [TIT2(encoding=1, text=display_title)])
    audio.tags.setall("TPE1", [TPE1(encoding=1, text=artist or "Unknown")])
    if anime:
        audio.tags.setall("TALB", [TALB(encoding=1, text=anime)])

    if cover_url:
        try:
            req = urllib.request.Request(cover_url, headers={"User-Agent": DESKTOP_USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                cover = to_square_jpeg(resp.read())
            audio.tags.setall("APIC", [APIC(encoding=1, mime="image/jpeg", type=3, desc="Cover", data=cover)])
        except Exception:
            pass  # a missing cover shouldn't fail the download

    audio.save(v2_version=3)


def prefetch_audio(video_id):
    """Stage 1. Download the raw audio + description into the cache. One at a
    time with a gap between tracks - this is the only YouTube request. Returns
    the description; a no-op if the track is already here."""
    if media_cache.is_cached(video_id) or media_cache.pending_raw(video_id):
        return media_cache.description(video_id)

    media_cache.clear_one(video_id)
    raw_path, thumbnail_url, description = download_audio(video_id, media_cache.CACHE_DIR)
    media_cache.write_raw(video_id, raw_path.name, description, thumbnail_url)
    return description


def normalize_cached(video_id):
    """Stage 2. Loudness-normalise the raw download into <id>.mp3. No network,
    runs several at once, idempotent."""
    with _normalize_locks[video_id]:
        raw = media_cache.pending_raw(video_id)
        if not raw:
            return  # already done, or stage 1 never ran
        loudnorm_to_mp3(raw, media_cache.mp3_path(video_id))
        raw.unlink(missing_ok=True)
        media_cache.mark_done(video_id)


def finalize_download(video_id, anime, kind, number, song, artist, output_dir, artwork_url=None):
    """Tag the cached mp3 and move it into the music folder. Fills in whichever
    earlier stage hasn't run yet - a search-tab download starts from nothing and
    does all three here."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not media_cache.is_cached(video_id):
        prefetch_audio(video_id)
        normalize_cached(video_id)

    meta = media_cache.read(video_id)
    staged = output_dir / f".{video_id}.staging.mp3"
    shutil.copy2(media_cache.mp3_path(video_id), staged)

    display_title = build_display_title(anime, kind, number, song)
    tag_mp3(staged, display_title, artist, anime, artwork_url or meta.get("thumbnail_url"))

    final_path = output_dir / (sanitize_filename(display_title) + ".mp3")
    final_path.unlink(missing_ok=True)
    staged.rename(final_path)
    return str(final_path)
