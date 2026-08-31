import os

from flask import Flask

from api import bp
from errors import register_handlers
from processing import media_cache

DEBUG = os.environ.get("FLASK_DEBUG", "1") != "0"

app = Flask(__name__)
app.debug = DEBUG
app.register_blueprint(bp)
register_handlers(app)

# Clear out audio left in the scratch cache by a session that quit without
# downloading. Skipped in the reloader's parent so it only runs once.
if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    media_cache.clear_all()

if __name__ == "__main__":
    # threaded so the playlist tab's parallel prep/download calls don't queue up.
    app.run(port=5000, threaded=True)
