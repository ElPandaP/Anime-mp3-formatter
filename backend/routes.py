from flask import Blueprint, jsonify, request
from yt_dlp import YoutubeDL

from ai_guess import ai_guess_with_search
from artwork import search_anime_cover, search_artwork
from audio import process_download
from folder_dialog import pick_folder_dialog
from llm_client import LLM_API_KEY, ai_guess_rate_limit_ok
from settings_store import DEFAULT_OUTPUT_DIR, load_config, save_config
from youtube import get_audio_stream_url

bp = Blueprint("api", __name__)


def _build_video_entry(entry, include_channel=False):
    video_id = entry.get("id")
    title = entry.get("title") or ""
    result = {
        "id": video_id,
        "title": title,
        "duration": entry.get("duration"),
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
    }
    if include_channel:
        result["channel"] = entry.get("channel") or entry.get("uploader") or ""
    return result


def _download_from_payload(item, output_dir):
    return process_download(
        video_id=item.get("id"),
        anime=item.get("anime", ""),
        kind=item.get("type", ""),
        number=item.get("number", ""),
        song=item.get("song", ""),
        artist=item.get("artist", ""),
        output_dir=output_dir,
        artwork_url=item.get("artwork_url"),
    )


@bp.route("/api/settings", methods=["GET", "POST"])
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


@bp.route("/api/browse-folder", methods=["POST"])
def browse_folder():
    data = request.get_json(silent=True) or {}
    initial = data.get("initial") or None
    try:
        path = pick_folder_dialog(initial)
        return jsonify({"path": path})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/search", methods=["POST"])
def search():
    data = request.get_json(force=True)
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Search query is empty"}), 400

    ydl_opts = {"quiet": True, "noplaylist": True, "extract_flat": "in_playlist"}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch8:{query}", download=False)

    results = [_build_video_entry(entry, include_channel=True) for entry in info.get("entries", []) or [] if entry]
    return jsonify({"results": results})


@bp.route("/api/ai-guess-online", methods=["POST"])
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


@bp.route("/api/stream", methods=["POST"])
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


@bp.route("/api/playlist", methods=["POST"])
def playlist():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Playlist URL is empty"}), 400

    ydl_opts = {"quiet": True, "extract_flat": "in_playlist"}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    items = [_build_video_entry(entry) for entry in info.get("entries", []) or [] if entry]
    return jsonify({"playlist_title": info.get("title", ""), "items": items})


@bp.route("/api/artwork", methods=["POST"])
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


@bp.route("/api/download", methods=["POST"])
def download_single():
    data = request.get_json(force=True)
    config = load_config()
    output_dir = (data.get("output_dir") or config.get("output_dir") or DEFAULT_OUTPUT_DIR).strip()

    try:
        final_path = _download_from_payload(data, output_dir)
        return jsonify({"success": True, "path": final_path})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
