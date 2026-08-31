"""The two ways a YouTube fetch can fail, and the JSON the API returns for them.
Registering the handlers on the app lets route code just let these propagate."""

from flask import current_app, jsonify

_RATE_LIMIT_MESSAGE = (
    "YouTube is rate-limiting requests (anti-bot check). Wait a few minutes and retry."
)


class RateLimitedError(Exception):
    """YouTube's anti-bot / HTTP 429 wall. Recoverable - back off and retry."""


class VideoUnavailableError(Exception):
    """Private, deleted, copyright-blocked, age-restricted or region-locked.
    Nothing to retry - skip it."""


def register_handlers(app):
    @app.errorhandler(RateLimitedError)
    def _rate_limited(_exc):
        return jsonify(status="rate_limited", error=_RATE_LIMIT_MESSAGE), 429

    @app.errorhandler(VideoUnavailableError)
    def _unavailable(exc):
        return jsonify(status="unavailable", error=str(exc)), 422

    @app.errorhandler(Exception)
    def _unexpected(exc):
        current_app.logger.exception("unhandled error")
        return jsonify(error=str(exc)), 500
