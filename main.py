import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from flask import Flask, render_template

from config import BASE_DIR, FLASK_DEBUG, FLASK_HOST, FLASK_PORT


def configurar_logging() -> None:
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    formato = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(formato))

    file_handler = TimedRotatingFileHandler(
        logs_dir / "consulta_ecd.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(formato))

    logging.basicConfig(
        level=logging.INFO,
        format=formato,
        handlers=[console_handler, file_handler],
        force=True,
    )


configurar_logging()

logging.getLogger("werkzeug").setLevel(logging.WARNING)

import database  # noqa: E402
from api import api_bp  # noqa: E402

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

    database.init_db()
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.route("/")
    def index():
        return render_template("index.html")

    return app


app = create_app()


if __name__ == "__main__":
    logger.info("Iniciando Consulta ECD | host=%s | port=%s | debug=%s", FLASK_HOST, FLASK_PORT, FLASK_DEBUG)
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, use_reloader=False, threaded=True)
