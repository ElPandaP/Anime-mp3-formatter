from flask import Blueprint, jsonify, request, send_file

import media_cache
from ai_guess import ai_guess_with_search
from artwork import search_anime_cover, search_artwork
from audio import finalize_download, normalize_cached, prefetch_audio
from folder_dialog import pick_folder_dialog
from llm_client import LLM_API_KEY, ai_guess_rate_limit_ok
from settings_store import DEFAULT_OUTPUT_DIR, load_config, save_config
from youtube import (
    RateLimitedError,
    VideoUnavailableError,
    get_audio_stream_url,
    playlist_entries,
    search_entries,
)

bp = Blueprint("api", __name__)

RATE_LIMIT_MESSAGE = (
    "YouTube is rate-limiting requests (anti-bot check). Wait a few minutes and retry."
)


def _rate_limited_response():
    return jsonify({"status": "rate_limited", "error": RATE_LIMIT_MESSAGE}), 429


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
    return finalize_download(
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

    try:
        entries = search_entries(query, limit=8)
    except RateLimitedError:
        return _rate_limited_response()

    results = [_build_video_entry(entry, include_channel=True) for entry in entries]
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
    except RateLimitedError:
        return _rate_limited_response()
    except VideoUnavailableError as exc:
        return jsonify({"status": "unavailable", "error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/prefetch-audio", methods=["POST"])
def prefetch_audio_route():
    """Playlist prep, stage 1 (serialised, spaced - the only YouTube hit per
    track): pull the raw audio + description into the scratch cache."""
    data = request.get_json(force=True)
    video_id = (data.get("id") or "").strip()
    if not video_id:
        return jsonify({"error": "Missing id"}), 400
    try:
        prefetch_audio(video_id)
    except RateLimitedError:
        return _rate_limited_response()
    except VideoUnavailableError as exc:
        return jsonify({"status": "unavailable", "error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@bp.route("/api/guess-tags", methods=["POST"])
def guess_tags_route():
    """Playlist prep, priority 2 (no network): guess the tags off the
    description stage 1 already fetched. This is all a row needs before the
    user can see and edit it - normalisation happens separately, lower
    priority. Safe to run several at once."""
    data = request.get_json(force=True)
    video_id = (data.get("id") or "").strip()
    title = (data.get("title") or "").strip()
    if not video_id or not title:
        return jsonify({"error": "Missing id or title"}), 400

    result = None
    if data.get("ai") and ai_guess_rate_limit_ok():
        try:
            result = ai_guess_with_search(
                video_id, title, data.get("guess"),
                description=media_cache.get_description(video_id),
            )
        except RateLimitedError:
            return _rate_limited_response()
        except Exception:
            result = None
    return jsonify({"result": result})


@bp.route("/api/normalize-cached", methods=["POST"])
def normalize_cached_route():
    """Playlist prep, priority 3 (no network): loudness-normalise a stage-1
    audio file in the cache. Runs in the background - only has to be done by
    the time that track is downloaded."""
    data = request.get_json(force=True)
    video_id = (data.get("id") or "").strip()
    if not video_id:
        return jsonify({"error": "Missing id"}), 400
    try:
        normalize_cached(video_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@bp.route("/api/cached-audio/<video_id>", methods=["GET"])
def cached_audio(video_id):
    path = media_cache.any_audio_path(video_id)
    if not path:
        return jsonify({"error": "Not cached"}), 404
    mimetype = {
        ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
        ".webm": "audio/webm", ".opus": "audio/ogg", ".ogg": "audio/ogg",
    }.get(path.suffix, "application/octet-stream")
    return send_file(path, mimetype=mimetype)


@bp.route("/api/stream", methods=["POST"])
def stream():
    data = request.get_json(force=True)
    video_id = (data.get("id") or "").strip()
    if not video_id:
        return jsonify({"error": "Missing video id"}), 400
    # Already pulled down during the playlist run - play the local file.
    if media_cache.has_audio(video_id):
        return jsonify({"url": f"/api/cached-audio/{video_id}"})
    try:
        stream_url = get_audio_stream_url(video_id)
        if not stream_url:
            return jsonify({"error": "No audio stream found"}), 404
        return jsonify({"url": stream_url})
    except RateLimitedError:
        return _rate_limited_response()
    except VideoUnavailableError as exc:
        return jsonify({"status": "unavailable", "error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/playlist", methods=["POST"])
def playlist():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Playlist URL is empty"}), 400

    # A new playlist means the previous run's prepared-but-not-downloaded audio
    # is dead weight - ditch it now rather than let it pile up.
    media_cache.clear_cache()

    try:
        title, entries, skipped = playlist_entries(url)
    except RateLimitedError:
        return _rate_limited_response()

    items = [_build_video_entry(entry) for entry in entries]
    return jsonify({
        "playlist_title": title,
        "items": items,
        "skipped_unavailable": skipped,
    })


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
    except RateLimitedError:
        return _rate_limited_response()
    except VideoUnavailableError as exc:
        return jsonify({"success": False, "status": "unavailable", "error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"success": False, "status": "error", "error": str(exc)}), 500
