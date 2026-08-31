"""HTTP layer. Anything that can raise RateLimitedError / VideoUnavailableError
just lets it propagate - errors.py turns those into the right JSON response."""

from flask import Blueprint, jsonify, request, send_file

from config import CONFIG, frontend_config, save_output_dir
from folder_dialog import pick_folder_dialog
from processing import media_cache
from processing.ai_guess import ai_guess_with_search
from processing.audio import finalize_download, normalize_cached, prefetch_audio
from sources.catalog import search_anime_cover, search_artwork
from sources.llm_client import LLM_API_KEY, ai_guess_rate_limit_ok
from sources.youtube import get_audio_stream_url, playlist_entries, search_entries

bp = Blueprint("api", __name__)

_AUDIO_MIMETYPES = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
    ".webm": "audio/webm", ".opus": "audio/ogg", ".ogg": "audio/ogg",
}


def _video_entry(entry, with_channel=False):
    video_id = entry.get("id")
    row = {
        "id": video_id,
        "title": entry.get("title") or "",
        "duration": entry.get("duration"),
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
    }
    if with_channel:
        row["channel"] = entry.get("channel") or entry.get("uploader") or ""
    return row


# --- settings + folder picker ---------------------------------------------

@bp.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        output_dir = (request.get_json(force=True).get("output_dir") or "").strip()
        if not output_dir:
            return jsonify(error="Output folder cannot be empty"), 400
        save_output_dir(output_dir)
        return jsonify(output_dir=output_dir)
    return jsonify(
        output_dir=CONFIG["output_dir"],
        ai_available=bool(LLM_API_KEY),
        **frontend_config(),
    )


@bp.route("/api/browse-folder", methods=["POST"])
def browse_folder():
    initial = (request.get_json(silent=True) or {}).get("initial") or None
    return jsonify(path=pick_folder_dialog(initial))


# --- search tab ---------------------------------------------------------

@bp.route("/api/search", methods=["POST"])
def search():
    query = (request.get_json(force=True).get("query") or "").strip()
    if not query:
        return jsonify(error="Search query is empty"), 400
    entries = search_entries(query, limit=8)
    return jsonify(results=[_video_entry(e, with_channel=True) for e in entries])


@bp.route("/api/ai-guess-online", methods=["POST"])
def ai_guess_online():
    data = request.get_json(force=True)
    video_id, title = (data.get("id") or "").strip(), (data.get("title") or "").strip()
    if not video_id or not title:
        return jsonify(error="Missing id or title"), 400
    if not ai_guess_rate_limit_ok():
        return jsonify(error="AI request rate limit reached, try again in a minute"), 429
    return jsonify(result=ai_guess_with_search(video_id, title, data.get("guess")))


# --- playlist prep: three lanes, see processing/audio.py ------------------

@bp.route("/api/prefetch-audio", methods=["POST"])
def prefetch_audio_route():
    video_id = (request.get_json(force=True).get("id") or "").strip()
    if not video_id:
        return jsonify(error="Missing id"), 400
    prefetch_audio(video_id)
    return jsonify(ok=True)


@bp.route("/api/guess-tags", methods=["POST"])
def guess_tags_route():
    data = request.get_json(force=True)
    video_id, title = (data.get("id") or "").strip(), (data.get("title") or "").strip()
    if not video_id or not title:
        return jsonify(error="Missing id or title"), 400

    result = None
    if data.get("ai") and ai_guess_rate_limit_ok():
        try:
            result = ai_guess_with_search(
                video_id, title, data.get("guess"),
                description=media_cache.description(video_id),
            )
        except Exception:
            pass  # tags stay blank; the user fills them in
    return jsonify(result=result)


@bp.route("/api/normalize-cached", methods=["POST"])
def normalize_cached_route():
    video_id = (request.get_json(force=True).get("id") or "").strip()
    if not video_id:
        return jsonify(error="Missing id"), 400
    normalize_cached(video_id)
    return jsonify(ok=True)


# --- audio for the preview player --------------------------------------

@bp.route("/api/stream", methods=["POST"])
def stream():
    video_id = (request.get_json(force=True).get("id") or "").strip()
    if not video_id:
        return jsonify(error="Missing video id"), 400
    if media_cache.has_audio(video_id):  # already prepped - play the local file
        return jsonify(url=f"/api/cached-audio/{video_id}")
    stream_url = get_audio_stream_url(video_id)
    if not stream_url:
        return jsonify(error="No audio stream found"), 404
    return jsonify(url=stream_url)


@bp.route("/api/cached-audio/<video_id>", methods=["GET"])
def cached_audio(video_id):
    path = media_cache.any_audio(video_id)
    if not path:
        return jsonify(error="Not cached"), 404
    return send_file(path, mimetype=_AUDIO_MIMETYPES.get(path.suffix, "application/octet-stream"))


# --- playlist + artwork + download ------------------------------------

@bp.route("/api/playlist", methods=["POST"])
def playlist():
    url = (request.get_json(force=True).get("url") or "").strip()
    if not url:
        return jsonify(error="Playlist URL is empty"), 400
    media_cache.clear_all()  # last run's prepped audio is dead weight now
    title, entries, skipped = playlist_entries(url)
    return jsonify(
        playlist_title=title,
        items=[_video_entry(e) for e in entries],
        skipped_unavailable=skipped,
    )


@bp.route("/api/artwork", methods=["POST"])
def artwork():
    query = (request.get_json(force=True).get("query") or "").strip()
    if not query:
        return jsonify(error="Search query is empty"), 400
    # Two independent sources; one failing shouldn't sink the other.
    anime = _safe(search_anime_cover, query)
    songs = _safe(search_artwork, query)
    if not anime and not songs:
        return jsonify(error="No cover art found"), 500
    return jsonify(results=anime + songs)  # anime poster first, song covers after


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return []


@bp.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(force=True)
    output_dir = (data.get("output_dir") or CONFIG["output_dir"]).strip()
    final_path = finalize_download(
        video_id=data.get("id"),
        anime=data.get("anime", ""),
        kind=data.get("type", ""),
        number=data.get("number", ""),
        song=data.get("song", ""),
        artist=data.get("artist", ""),
        output_dir=output_dir,
        artwork_url=data.get("artwork_url"),
    )
    return jsonify(path=final_path)
