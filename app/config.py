"""Configuration helpers for the memorial application."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Type

_BASE_DIR = Path(__file__).resolve().parent.parent


def _coerce_positive_int(
    raw_value: str | None,
    *,
    fallback: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    """Best-effort conversion of an environment value into a bounded integer."""

    if raw_value is None:
        return fallback

    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return fallback

    if parsed < minimum:
        return minimum

    if maximum is not None and parsed > maximum:
        return maximum

    return parsed


def _resolve_database_uri(
    env_name: str = "DATABASE_URL", *, default: str | None = None
) -> str:
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


def _build_engine_options(uri: str) -> dict[str, Any]:
    options: dict[str, Any] = {"pool_pre_ping": True}
    if not uri.startswith("sqlite"):
        options["pool_recycle"] = int(os.getenv("SQLALCHEMY_POOL_RECYCLE", 300))
        options["pool_timeout"] = int(os.getenv("SQLALCHEMY_POOL_TIMEOUT", 30))
    return options


class BaseConfig:
    """Default configuration shared by all environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = _resolve_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _build_engine_options(SQLALCHEMY_DATABASE_URI)
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 20 * 1024 * 1024))  # 20MB
    MAX_PHOTO_UPLOAD_BYTES = int(
        os.getenv("MAX_PHOTO_UPLOAD_BYTES", 1 * 1024 * 1024)
    )  # 1MB
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    _default_page_size = _coerce_positive_int(
        os.getenv("TRIBUTES_PER_PAGE") or os.getenv("TRIBUTES_PAGE_SIZE"),
        fallback=12,
    )
    TRIBUTES_PER_PAGE = _default_page_size
    TRIBUTES_PAGE_SIZE = _default_page_size  # Backwards compatibility for older code
    TRIBUTES_MAX_PER_PAGE = _coerce_positive_int(
        os.getenv("TRIBUTES_MAX_PER_PAGE"),
        fallback=max(_default_page_size * 3, _default_page_size),
        minimum=_default_page_size,
    )
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    AWS_REGION = os.getenv("AWS_REGION")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    S3_BUCKET_PREFIX = os.getenv("S3_BUCKET_PREFIX", "")
    S3_PUBLIC_BASE_URL = os.getenv("S3_PUBLIC_BASE_URL") or os.getenv(
        "S3_PUBLIC_DOMAIN"
    )
    S3_USE_OAC = os.getenv("S3_USE_OAC")
    S3_OBJECT_ACL = os.getenv("S3_OBJECT_ACL")
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
    S3_PRESIGNED_TTL = int(os.getenv("S3_PRESIGNED_TTL", 300))
    ALLOWED_EXTENSIONS = tuple(
        ext.strip().lower()
        for ext in os.getenv(
            "ALLOWED_EXTENSIONS",
            "jpg,jpeg,png,webp,heic,heif,gif",
        ).split(",")
        if ext.strip()
    )
    SLIDESHOW_POLL_SECONDS = int(os.getenv("SLIDESHOW_POLL_SECONDS", 60))
    SLIDESHOW_DWELL_MILLISECONDS = int(os.getenv("SLIDESHOW_DWELL_MILLISECONDS", 8000))
    SLIDESHOW_TRANSITION_MILLISECONDS = int(
        os.getenv("SLIDESHOW_TRANSITION_MILLISECONDS", 800)
    )
    SLIDESHOW_MAX_MESSAGE_LENGTH = int(
        os.getenv("SLIDESHOW_MAX_MESSAGE_LENGTH", 600)
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
    SQLALCHEMY_ENGINE_OPTIONS = _build_engine_options(SQLALCHEMY_DATABASE_URI)


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
