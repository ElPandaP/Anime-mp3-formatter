import io
import shutil
import subprocess
import threading
from collections import defaultdict
from pathlib import Path

import urllib.request

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1
from mutagen.mp3 import MP3
from PIL import Image

import media_cache
from artwork import DESKTOP_USER_AGENT
from title_parsing import build_display_title, sanitize_filename
from youtube import FFMPEG_LOCATION, download_audio

COVER_SIZE = 640


def to_square_jpeg(image_data, size=COVER_SIZE):
    """Force any source image (portrait anime poster, square album art,
    16:9 YouTube thumbnail, whatever) into a consistent square cover:
    center-crop to a square, then resize."""
    with Image.open(io.BytesIO(image_data)) as img:
        img = img.convert("RGB")
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()


def loudnorm_to_mp3(src_path, dst_path):
    """Loudness-normalise any audio file into a 192k-ish mp3 at dst_path. This
    is the only transcode in the pipeline - the raw download is fed straight
    in, no separate 'extract to mp3' step first."""
    ffmpeg_bin = FFMPEG_LOCATION or "ffmpeg"
    tmp_path = dst_path.with_name(dst_path.stem + ".norm.mp3")
    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-i", str(src_path),
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-ar", "44100",
            "-codec:a", "libmp3lame",
            "-q:a", "2",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
    )
    if dst_path.exists():
        dst_path.unlink()
    tmp_path.rename(dst_path)


def normalize_loudness(mp3_path):
    loudnorm_to_mp3(mp3_path, mp3_path)


def tag_mp3(mp3_path, display_title, artist, anime, cover_url):
    audio = MP3(mp3_path, ID3=ID3)
    try:
        audio.add_tags()
    except Exception:
        pass

    # encoding=1 (UTF-16) rather than 3 (UTF-8): we save as ID3v2.3 below for
    # Spotify/local-files compatibility, and v2.3 doesn't support UTF-8 text
    # frames - only Latin-1 and UTF-16.
    audio.tags.setall("TIT2", [TIT2(encoding=1, text=display_title)])
    audio.tags.setall("TPE1", [TPE1(encoding=1, text=artist or "Unknown")])
    if anime:
        audio.tags.setall("TALB", [TALB(encoding=1, text=anime)])

    if cover_url:
        try:
            cover_req = urllib.request.Request(cover_url, headers={"User-Agent": DESKTOP_USER_AGENT})
            with urllib.request.urlopen(cover_req, timeout=10) as resp:
                image_data = resp.read()
            image_data = to_square_jpeg(image_data)
            audio.tags.setall(
                "APIC",
                [APIC(encoding=1, mime="image/jpeg", type=3, desc="Cover", data=image_data)],
            )
        except Exception:
            pass

    # Spotify's local-files feature reads embedded artwork much more
    # reliably from ID3v2.3 tags than v2.4 (mutagen's default).
    audio.save(v2_version=3)


def _finalize(mp3_path, output_dir, display_title, artist, anime, cover_url):
    """Tag an mp3 that's already downloaded + normalised, then move it to its
    final name in the user's output folder."""
    final_path = output_dir / (sanitize_filename(display_title) + ".mp3")
    tag_mp3(mp3_path, display_title, artist, anime, cover_url)
    if mp3_path != final_path:
        if final_path.exists():
            final_path.unlink()
        mp3_path.rename(final_path)
    return str(final_path)


def prefetch_audio(video_id):
    """Prep stage 1 (runs one-at-a-time with a gap between tracks - this is the
    only part that hits YouTube). Pulls the raw bestaudio file + the description
    into the cache. No transcode, no normalise - those are stage 2. Returns the
    description. Idempotent: does nothing if the audio is already here.
    Raises RateLimitedError / VideoUnavailableError like any other fetch."""
    if media_cache.is_cached(video_id):
        return media_cache.read_meta(video_id).get("description", "")
    if media_cache.pending_raw_path(video_id):
        return media_cache.read_pending(video_id).get("description", "")

    media_cache.ensure_dir()
    media_cache.clear_partial(video_id)

    raw_path, thumbnail_url, description = download_audio(
        video_id, media_cache.CACHE_DIR, to_mp3=False
    )
    media_cache.mark_pending(video_id, raw_path.name, description, thumbnail_url)
    return description


_normalize_locks = defaultdict(threading.Lock)


def normalize_cached(video_id):
    """No network: loudness-normalise the raw stage-1 download into <id>.mp3 and
    write the 'done' sidecar. Idempotent and safe to call from several places at
    once (the background prep queue and a download that got there first) - a
    per-id lock means the work happens exactly once."""
    with _normalize_locks[video_id]:
        if media_cache.is_cached(video_id):
            return
        raw_path = media_cache.pending_raw_path(video_id)
        if not raw_path:
            return  # stage 1 never ran / was cleared
        pending = media_cache.read_pending(video_id)
        loudnorm_to_mp3(raw_path, media_cache.cache_mp3_path(video_id))
        try:
            raw_path.unlink()
        except OSError:
            pass
        media_cache.store(video_id, pending.get("description", ""), pending.get("thumbnail_url", ""))
        media_cache.clear_pending(video_id)


def finalize_download(video_id, anime, kind, number, song, artist, output_dir, artwork_url=None):
    """Turn a prepared track into the final tagged mp3 with no network access.
    If the background prep queue hasn't normalised this one yet, do it inline
    now (a few seconds) rather than re-fetch. Only a track that was never
    prefetched at all - or whose cache was wiped - triggers a full download."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    display_title = build_display_title(anime, kind, number, song)

    if not media_cache.is_cached(video_id):
        if media_cache.pending_raw_path(video_id):
            normalize_cached(video_id)  # background queue hadn't reached it yet
    if not media_cache.is_cached(video_id):
        return process_download(
            video_id, anime, kind, number, song, artist, output_dir, artwork_url
        )

    meta = media_cache.read_meta(video_id)
    work_mp3 = output_dir / f".{video_id}.staging.mp3"
    shutil.copy2(media_cache.cache_mp3_path(video_id), work_mp3)
    cover_url = artwork_url or meta.get("thumbnail_url")
    return _finalize(work_mp3, output_dir, display_title, artist, anime, cover_url)


def process_download(video_id, anime, kind, number, song, artist, output_dir, artwork_url=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    display_title = build_display_title(anime, kind, number, song)

    mp3_path, thumbnail_url, _description = download_audio(video_id, output_dir)
    normalize_loudness(mp3_path)
    cover_url = artwork_url or thumbnail_url
    return _finalize(mp3_path, output_dir, display_title, artist, anime, cover_url)
