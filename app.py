import io
import json
import os
import re
import shutil
import subprocess
import time
import tkinter as tk
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from tkinter import filedialog

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1
from mutagen.mp3 import MP3
from PIL import Image
from yt_dlp import YoutubeDL

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_OUTPUT_DIR = str(Path.home() / "Music" / "AnimeMp3")
FFMPEG_LOCATION = shutil.which("ffmpeg")

# AI-based title parsing (optional). Uses the OpenAI-compatible "chat
# completions" shape so any provider that speaks it can be swapped in by
# only changing these three values - Anthropic, Kimi/Moonshot, DeepSeek,
# OpenRouter, etc.
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5")

# Hard safety cap: no matter what triggers calls to the AI endpoint (a bug,
# a runaway retry, whatever), it can never place more than this many
# requests in a rolling minute.
AI_GUESS_RATE_LIMIT = 20
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


CORNER_QUOTE_RE = re.compile(r"[『「]([^』」]+)[』」]")
BY_ARTIST_RE = re.compile(r"\bby\s+([^([|｜\-–—]+)", re.IGNORECASE)


def guess_fields_from_title(title):
    song = ""
    artist = ""

    bracket_match = CORNER_QUOTE_RE.search(title)
    if bracket_match:
        song = bracket_match.group(1).strip()

    by_match = BY_ARTIST_RE.search(title)
    if by_match:
        artist = by_match.group(1).strip()

    if song or artist:
        return {"artist": artist, "song": song}

    # Fallback for plain "Artist - Song" style titles.
    cleaned = re.sub(r"\[[^\]]*\]|\([^)]*\)|[『「][^』」]*[』」]", "", title).strip()
    if " - " in cleaned:
        left, right = cleaned.split(" - ", 1)
        return {"artist": left.strip(), "song": right.strip()}

    # No reliable pattern found - leave both empty rather than dumping the
    # raw title (with separators like "|" still in it) into "song". An
    # honest "unknown" lets AI/description/web-search fill it in properly,
    # instead of a bad guess blocking them because it isn't empty.
    return {"artist": "", "song": ""}


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


ROMANIZATION_RULE = (
    "Prefer the romanized/English name for song and artist (e.g. \"Tabibito no "
    "Uta\", not \"旅人の唄\"). Only use Japanese script if no romanized version "
    "exists anywhere."
)

JAPANESE_SCRIPT_RE = re.compile(r"[぀-ヿ一-鿿]")


def is_japanese(text):
    return bool(text) and bool(JAPANESE_SCRIPT_RE.search(text))


def strip_japanese(text):
    """Never surface raw kanji/kana here - treat it the same as "unknown" so
    later steps (which can actually search for a romanized version) get a
    chance to run, instead of a guessed transliteration that might be wrong."""
    return "" if is_japanese(text) else text


def ai_guess_titles(titles):
    prompt = (
        "You extract anime song metadata from YouTube video titles.\n"
        "For each numbered title below, identify:\n"
        "- anime: the anime's name only (no season/episode filler words unless "
        "they're part of the title itself, e.g. keep 'Season 2').\n"
        "- type: OP, ED, or OST.\n"
        "- number: ONLY a plain numeral if the title shows one (e.g. \"2\"). "
        "Words like Full, Short, TV, NCOP, NCED, ver are NOT numbers - use \"\" instead.\n"
        "- song: the clean song title, with quote marks, brackets (『』「」\"\"''), "
        "and filler words like Full/Short/Lyrics/HD/Creditless stripped out.\n"
        "- artist: the performing artist/band, if named anywhere in the title.\n"
        f"{ROMANIZATION_RULE}\n"
        'Use "" for any field you cannot determine.\n\n'
        "Example input:\n"
        '1. Attack on Titan S4 - Opening 1 Full『My War』by SiM [Lyrics]\n'
        '2. | Some Anime Title | ED FULL | [LYRICS] |\n'
        "Example output:\n"
        '[{"anime": "Attack on Titan S4", "type": "OP", "number": "1", '
        '"song": "My War", "artist": "SiM"}, '
        '{"anime": "Some Anime Title", "type": "ED", "number": "", '
        '"song": "", "artist": ""}]\n\n'
        "Reply with ONLY a JSON array of objects, in the same order as the "
        "titles below, one object per title, no prose, no markdown.\n\n"
        + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    )

    parsed = extract_json(call_llm(prompt), "[", "]")

    results = []
    for i in range(len(titles)):
        item = parsed[i] if i < len(parsed) and isinstance(parsed[i], dict) else {}
        results.append(
            {
                "anime": str(item.get("anime") or ""),
                "type": str(item.get("type") or "OP").upper(),
                "number": str(item.get("number") or ""),
                "song": strip_japanese(str(item.get("song") or "")),
                "artist": strip_japanese(str(item.get("artist") or "")),
            }
        )
    return results


def itunes_song_snippets(query, max_results=200):
    """iTunes's catalog as a stand-in for a general web search: no API key,
    no bot-detection wall (unlike scraping a search engine), and it already
    stores properly romanized official artist/track names."""
    try:
        candidates = search_artwork(query, limit=max_results)
    except Exception:
        return []
    return [
        f"{c['artist']} - {c['track']} ({c.get('collection', '')})"
        for c in candidates
        if c.get("track")
    ]


def ai_fill_from_context(title, base_guess, context_label, context_text, allow_override=False):
    base_guess = dict(base_guess or {})
    if not allow_override and base_guess.get("song") and base_guess.get("artist"):
        return base_guess
    if not context_text:
        return base_guess

    prompt = (
        "You are extracting anime song metadata using extra context.\n"
        f"Original YouTube video title: {title}\n"
        f"Current guess (may be WRONG - e.g. a bracketed annotation like "
        f"\"[Creditless]\", \"[4K]\" or \"[UHD 60FPS]\" mistaken for the song title; "
        f"only trust it if the context below doesn't clearly say otherwise) - "
        f"anime: {base_guess.get('anime') or '?'}, type: {base_guess.get('type') or '?'}, "
        f"number: {base_guess.get('number') or '?'}, "
        f"song: {base_guess.get('song') or '(unknown)'}, "
        f"artist: {base_guess.get('artist') or '(unknown)'}\n\n"
        f"{context_label}:\n{context_text[:2000]}\n\n"
        "If the context above EXPLICITLY states a song title and/or artist (e.g. after "
        "\"Song:\", \"Artist:\", \"Song Title :\", \"by\", a track listing, or an obvious "
        "name in a URL like lnk.to/artistname), use that name - even if it means "
        "replacing the current guess. Copy or lightly clean up that exact name - never "
        "translate the meaning of a Japanese word/phrase into English (e.g. a title like "
        "\"春擬き\" must stay as its actual name if you find one, not be translated to "
        "something like \"Spring Proposal\"). If the context doesn't clearly state a "
        "song/artist, leave that field \"\" - do not guess or translate.\n"
        'Reply with ONLY JSON: {"song": "", "artist": ""} - use "" if still unknown.\n'
    )

    try:
        parsed = extract_json(call_llm(prompt), "{", "}")
    except Exception:
        return base_guess

    result = dict(base_guess)
    for key in ("song", "artist"):
        value = parsed.get(key)
        if value and (allow_override or not result.get(key)):
            result[key] = str(value)
    return result


def get_video_description(video_id):
    ydl_opts = {"quiet": True, "skip_download": True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    return info.get("description") or ""


def _stash_and_clear_japanese(guess, stash):
    """A kanji/kana-only answer isn't good enough yet - park it in `stash`
    (the first one found is kept) and blank the field so the next, more
    capable step still gets a chance to find a romanized version."""
    for key in ("song", "artist"):
        if is_japanese(guess.get(key)):
            stash.setdefault(key, guess[key])
            guess[key] = ""
    return guess


def ai_guess_with_search(video_id, title, base_guess):
    stash = {}
    working = _stash_and_clear_japanese(dict(base_guess or {}), stash)

    # 1. The video's own description often has explicit "Song: X / Artist: Y"
    # credits - always worth checking, even if song/artist already look
    # filled in, since that guess might just be a misread bracketed
    # annotation (e.g. "[Creditless]") rather than the real title. The
    # description is authoritative enough to correct that.
    try:
        description = get_video_description(video_id)
    except Exception:
        description = ""
    working = _stash_and_clear_japanese(
        ai_fill_from_context(title, working, "Video description", description, allow_override=True),
        stash,
    )
    if working.get("song") and working.get("artist"):
        return working

    # 2. Still missing something - search iTunes's catalog, which stores
    # official romanized artist/track names. Use whatever we already have
    # (a resolved artist name is the strongest hint) to narrow it down.
    # This stage only fills gaps - it's less authoritative than an explicit
    # description credit, so it never overrides an existing guess.
    query = " ".join(filter(None, [working.get("artist") or stash.get("artist"), working.get("anime")])).strip()
    if not query:
        query = re.sub(r"[|｜\[\]()]", " ", title).strip()
    try:
        snippets = itunes_song_snippets(query)
    except Exception:
        snippets = []
    if snippets:
        working = _stash_and_clear_japanese(
            ai_fill_from_context(
                title, working, "iTunes catalog matches", "\n".join(f"- {s}" for s in snippets)
            ),
            stash,
        )

    # Nothing romanized was found anywhere - a kanji/kana answer beats no
    # answer, so fall back to whatever we stashed along the way.
    if not working.get("song") and stash.get("song"):
        working["song"] = stash["song"]
    if not working.get("artist") and stash.get("artist"):
        working["artist"] = stash["artist"]
    return working


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


def search_artwork(query, limit=8):
    params = urllib.parse.urlencode({"term": query, "media": "music", "limit": limit})
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


ANILIST_QUERY = """
query ($search: String) {
  Page(page: 1, perPage: 5) {
    media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
      title { romaji english }
      coverImage { extraLarge }
    }
  }
}
"""


def search_anime_cover(anime_name):
    """AniList's anime database - actual show poster/key art, unlike iTunes
    which only ever has music single/album covers."""
    if not anime_name.strip():
        return []
    body = json.dumps({"query": ANILIST_QUERY, "variables": {"search": anime_name}}).encode("utf-8")
    req = urllib.request.Request(
        "https://graphql.anilist.co",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    candidates = []
    for media in (data.get("data", {}).get("Page", {}).get("media") or []):
        art = (media.get("coverImage") or {}).get("extraLarge")
        if not art:
            continue
        title = media.get("title") or {}
        candidates.append(
            {
                "artwork_url": art,
                "track": title.get("english") or title.get("romaji") or anime_name,
                "artist": "",
                "collection": "Anime poster",
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
    config = dict(load_config())
    config["ai_available"] = bool(LLM_API_KEY)
    return jsonify(config)


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


@app.route("/api/ai-guess", methods=["POST"])
def ai_guess():
    data = request.get_json(force=True)
    titles = data.get("titles") or []
    if not titles:
        return jsonify({"error": "No titles provided"}), 400
    if not ai_guess_rate_limit_ok():
        return jsonify({"error": "AI request rate limit reached, try again in a minute"}), 429
    try:
        results = ai_guess_titles(titles)
        return jsonify({"results": results})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/ai-guess-online", methods=["POST"])
def ai_guess_online():
    data = request.get_json(force=True)
    video_id = (data.get("id") or "").strip()
    title = (data.get("title") or "").strip()
    if not video_id or not title:
        return jsonify({"error": "Missing id or title"}), 400
    if not ai_guess_rate_limit_ok():
        return jsonify({"error": "AI request rate limit reached, try again in a minute"}), 429
    try:
        result = ai_guess_with_search(video_id, title, data.get("guess"))
        return jsonify({"result": result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


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
        anime_candidates = search_anime_cover(query)
    except Exception:
        anime_candidates = []
    try:
        song_candidates = search_artwork(query)
    except Exception:
        song_candidates = []

    if not anime_candidates and not song_candidates:
        return jsonify({"error": "No cover art found"}), 500

    # Anime poster art first - it's what "cover art for the anime" actually
    # means; iTunes song/album covers are offered as alternates.
    return jsonify({"results": anime_candidates + song_candidates})


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
