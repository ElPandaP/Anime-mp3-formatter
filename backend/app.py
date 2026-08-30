from flask import Flask

from routes import bp

app = Flask(__name__)
app.register_blueprint(bp)

if __name__ == "__main__":
    # threaded=True so the playlist tab can fire several tag-lookup /
    # download requests at once instead of them queuing behind each other.
    app.run(debug=True, port=5000, threaded=True)
