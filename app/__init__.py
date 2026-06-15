import os
from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required")
    app.secret_key = secret_key

    # 64 KB upload limit
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    from .routes import bp
    app.register_blueprint(bp)

    return app
