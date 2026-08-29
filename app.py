import json
import re
import shutil
import subprocess
import tkinter as tk
import urllib.parse
import urllib.request
from pathlib import Path
from tkinter import filedialog

from flask import Flask, jsonify, request
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1
from mutagen.mp3 import MP3
from yt_dlp import YoutubeDL

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_OUTPUT_DIR = str(Path.home() / "Music" / "AnimeMp3")
FFMPEG_LOCATION = shutil.which("ffmpeg")

app = Flask(__name__)


def load_config():
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if data.get("output_dir"):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"output_dir": DEFAULT_OUTPUT_DIR}


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "untitled"


def guess_fields_from_title(title):
    cleaned = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", title).strip()
    artist, song = "", cleaned
    if " - " in cleaned:
        left, right = cleaned.split(" - ", 1)
        artist, song = left.strip(), right.strip()
    return {"artist": artist, "song": song}


def build_display_title(anime, kind, number, song):
    anime = (anime or "").strip()
    kind = (kind or "").strip()
    number = (number or "").strip()
    song = (song or "").strip()

    if kind.upper() == "OST":
        label = f"{anime} OST".strip()
    elif number:
        label = f"{anime} {kind} {number}".strip()
    else:
        label = f"{anime} {kind}".strip()

    label = re.sub(r"\s+", " ", label).strip()
    if song:
        return f"{label} - {song}" if label else song
    return label


def search_artwork(query):
    params = urllib.parse.urlencode({"term": query, "media": "music", "limit": 8})
    request_url = f"https://itunes.apple.com/search?{params}"
    with urllib.request.urlopen(request_url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    candidates = []
    for result in data.get("results", []) or []:
        art = result.get("artworkUrl100")
        if not art:
            continue
        art_hd = re.sub(r"/\d+x\d+bb\.(jpg|png)$", r"/600x600bb.\1", art)
        candidates.append(
            {
                "artwork_url": art_hd,
                "track": result.get("trackName", ""),
                "artist": result.get("artistName", ""),
                "collection": result.get("collectionName", ""),
            }
        )
    return candidates


def get_audio_stream_url(video_id):
    ydl_opts = {"quiet": True, "format": "bestaudio/best", "noplaylist": True}
    if FFMPEG_LOCATION:
        ydl_opts["ffmpeg_location"] = FFMPEG_LOCATION

    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    stream_url = info.get("url")
    if not stream_url and info.get("requested_formats"):
        stream_url = info["requested_formats"][0].get("url")
    return stream_url


def pick_folder_dialog(initial_dir=None):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(initialdir=initial_dir or str(Path.home()))
    root.destroy()
    return selected or None


def download_audio(video_id, work_dir):
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ],
        "quiet": True,
        "noplaylist": True,
        "noprogress": True,
    }
    if FFMPEG_LOCATION:
        ydl_opts["ffmpeg_location"] = FFMPEG_LOCATION

    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    mp3_path = work_dir / f"{info['id']}.mp3"
    thumbnail_url = info.get("thumbnail")
    return mp3_path, thumbnail_url


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

    audio.tags.setall("TIT2", [TIT2(encoding=3, text=display_title)])
    audio.tags.setall("TPE1", [TPE1(encoding=3, text=artist or "Unknown")])
    if anime:
        audio.tags.setall("TALB", [TALB(encoding=3, text=anime)])

    if cover_url:
        try:
            with urllib.request.urlopen(cover_url, timeout=10) as resp:
                image_data = resp.read()
            mime = "image/png" if cover_url.lower().endswith(".png") else "image/jpeg"
            audio.tags.setall(
                "APIC",
                [APIC(encoding=3, mime=mime, type=3, desc="Cover", data=image_data)],
            )
        except Exception:
            pass

    audio.save()


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


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        data = request.get_json(force=True)
        output_dir = (data.get("output_dir") or "").strip()
        if not output_dir:
            return jsonify({"error": "Output folder cannot be empty"}), 400
        config = {"output_dir": output_dir}
        save_config(config)
        return jsonify(config)
    return jsonify(load_config())


@app.route("/api/browse-folder", methods=["POST"])
def browse_folder():
    data = request.get_json(silent=True) or {}
    initial = data.get("initial") or None
    try:
        path = pick_folder_dialog(initial)
        return jsonify({"path": path})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/search", methods=["POST"])
def search():
    data = request.get_json(force=True)
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Search query is empty"}), 400

    ydl_opts = {"quiet": True, "noplaylist": True, "extract_flat": "in_playlist"}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch8:{query}", download=False)

    results = []
    for entry in info.get("entries", []) or []:
        if not entry:
            continue
        video_id = entry.get("id")
        title = entry.get("title") or ""
        results.append(
            {
                "id": video_id,
                "title": title,
                "channel": entry.get("channel") or entry.get("uploader") or "",
                "duration": entry.get("duration"),
                "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
                "guess": guess_fields_from_title(title),
            }
        )
    return jsonify({"results": results})


@app.route("/api/stream", methods=["POST"])
def stream():
    data = request.get_json(force=True)
    video_id = (data.get("id") or "").strip()
    if not video_id:
        return jsonify({"error": "Missing video id"}), 400
    try:
        stream_url = get_audio_stream_url(video_id)
        if not stream_url:
            return jsonify({"error": "No audio stream found"}), 404
        return jsonify({"url": stream_url})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/playlist", methods=["POST"])
def playlist():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Playlist URL is empty"}), 400

    ydl_opts = {"quiet": True, "extract_flat": "in_playlist"}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    items = []
    for entry in info.get("entries", []) or []:
        if not entry:
            continue
        video_id = entry.get("id")
        title = entry.get("title") or ""
        items.append(
            {
                "id": video_id,
                "title": title,
                "duration": entry.get("duration"),
                "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
                "guess": guess_fields_from_title(title),
            }
        )
    return jsonify({"playlist_title": info.get("title", ""), "items": items})


@app.route("/api/artwork", methods=["POST"])
def artwork():
    data = request.get_json(force=True)
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Search query is empty"}), 400
    try:
        candidates = search_artwork(query)
        return jsonify({"results": candidates})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/download", methods=["POST"])
def download_single():
    data = request.get_json(force=True)
    config = load_config()
    output_dir = (data.get("output_dir") or config.get("output_dir") or DEFAULT_OUTPUT_DIR).strip()

    try:
        final_path = process_download(
            video_id=data.get("id"),
            anime=data.get("anime", ""),
            kind=data.get("type", ""),
            number=data.get("number", ""),
            song=data.get("song", ""),
            artist=data.get("artist", ""),
            output_dir=output_dir,
            artwork_url=data.get("artwork_url"),
        )
        return jsonify({"success": True, "path": final_path})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/playlist/download", methods=["POST"])
def download_playlist():
    data = request.get_json(force=True)
    config = load_config()
    output_dir = (data.get("output_dir") or config.get("output_dir") or DEFAULT_OUTPUT_DIR).strip()
    items = data.get("items", [])

    results = []
    for item in items:
        try:
            final_path = process_download(
                video_id=item.get("id"),
                anime=item.get("anime", ""),
                kind=item.get("type", ""),
                number=item.get("number", ""),
                song=item.get("song", ""),
                artist=item.get("artist", ""),
                output_dir=output_dir,
                artwork_url=item.get("artwork_url"),
            )
            results.append({"id": item.get("id"), "success": True, "path": final_path})
        except Exception as exc:
            results.append({"id": item.get("id"), "success": False, "error": str(exc)})

    return jsonify({"results": results})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
