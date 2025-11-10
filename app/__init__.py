"""Application factory for the memorial site."""

from datetime import UTC, datetime
from pathlib import Path

from flask import Flask
from .config import get_config
from .extensions import csrf, db, migrate
from .routes import main_bp

_BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(config_name: str | None = None) -> Flask:
    """Build and configure the Flask application instance."""
    app = Flask(
        __name__,
        static_folder=str(_BASE_DIR / "static"),
        static_url_path="/static",
    )
    config_obj = get_config(config_name)
    app.config.from_object(config_obj)

    register_extensions(app)
    register_blueprints(app)
    register_context_processors(app)

    return app


def register_extensions(app: Flask) -> None:
    """Initialize application extensions."""
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)


def register_blueprints(app: Flask) -> None:
    """Register application blueprints."""
    app.register_blueprint(main_bp)


def register_context_processors(app: Flask) -> None:
    """Attach template helpers."""

    @app.context_processor
    def inject_current_year() -> dict[str, int]:
        return {"current_year": datetime.now(UTC).year}
