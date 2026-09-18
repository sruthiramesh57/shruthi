"""
Application entry point. Run with:
    python app.py
"""

from flask import Flask, render_template, jsonify

from config import MAX_UPLOAD_BYTES
from utils.file_utils import ensure_directories
from routes.compression import bp as compression_bp


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    ensure_directories()
    app.register_blueprint(compression_bp)

    @app.route("/")
    def index():
        return render_template("index.html", max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024))

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({"success": False, "error": "File exceeds the maximum upload size."}), 413

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"success": False, "error": "Not found."}), 404

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify({"success": False, "error": "An unexpected server error occurred."}), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
