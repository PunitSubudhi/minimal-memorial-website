"""Configuration helpers for the memorial application."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Type

_BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_database_uri(env_name: str = "DATABASE_URL", *, default: str | None = None) -> str:
    url = os.getenv(env_name)
    if not url:
        if default is not None:
            return default
        return f"sqlite:///{_BASE_DIR / 'memorial.db'}"

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    scheme, sep, remainder = url.partition("://")
    if scheme == "postgresql" and sep:
        url = f"postgresql+psycopg://{remainder}"

    return url


class BaseConfig:
    """Default configuration shared by all environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = _resolve_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 20 * 1024 * 1024))
    MAX_PHOTO_UPLOAD_BYTES = int(os.getenv("MAX_PHOTO_UPLOAD_BYTES", 1 * 1024 * 1024))
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    TRIBUTES_PAGE_SIZE = int(os.getenv("TRIBUTES_PAGE_SIZE", 12))
    ALLOWED_EXTENSIONS = tuple(
        ext.strip().lower()
        for ext in os.getenv(
            "ALLOWED_EXTENSIONS",
            "jpg,jpeg,png,webp,heic,heif,gif",
        ).split(",")
        if ext.strip()
    )


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class TestingConfig(BaseConfig):
    TESTING = True
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = _resolve_database_uri(
        "DATABASE_URL_TEST", default="sqlite:///:memory:"
    )


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE = True


_CONFIG_MAP: dict[str | None, Type[BaseConfig]] = {
    None: BaseConfig,
    "default": BaseConfig,
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None) -> Type[BaseConfig]:
    """Pick a configuration object based on the provided name."""
    key = (name or os.getenv("FLASK_ENV") or "default").lower()
    return _CONFIG_MAP.get(key, BaseConfig)
