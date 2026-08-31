import os

from flask import Flask

import media_cache
from routes import bp

app = Flask(__name__)
app.register_blueprint(bp)

# Wipe any audio left in the scratch cache by a previous session that was
# closed without downloading. Guarded so the debug reloader's parent process
# doesn't do it a second time mid-run.
if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    media_cache.clear_cache()

if __name__ == "__main__":
    # threaded=True so the playlist tab can fire several tag-lookup /
    # download requests at once instead of them queuing behind each other.
    app.run(debug=True, port=5000, threaded=True)
