import io
import subprocess
from pathlib import Path

import urllib.request

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1
from mutagen.mp3 import MP3
from PIL import Image

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


def normalize_loudness(mp3_path):
    ffmpeg_bin = FFMPEG_LOCATION or "ffmpeg"
    normalized_path = mp3_path.with_name(mp3_path.stem + ".norm.mp3")
    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-i", str(mp3_path),
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-ar", "44100",
            "-codec:a", "libmp3lame",
            "-q:a", "2",
            str(normalized_path),
        ],
        check=True,
        capture_output=True,
    )
    mp3_path.unlink()
    normalized_path.rename(mp3_path)


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
            cover_req = urllib.request.Request(
                cover_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
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


def process_download(video_id, anime, kind, number, song, artist, output_dir, artwork_url=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    display_title = build_display_title(anime, kind, number, song)
    final_name = sanitize_filename(display_title) + ".mp3"
    final_path = output_dir / final_name

    mp3_path, thumbnail_url = download_audio(video_id, output_dir)
    normalize_loudness(mp3_path)
    cover_url = artwork_url or thumbnail_url
    tag_mp3(mp3_path, display_title, artist, anime, cover_url)

    if mp3_path != final_path:
        if final_path.exists():
            final_path.unlink()
        mp3_path.rename(final_path)

    return str(final_path)
