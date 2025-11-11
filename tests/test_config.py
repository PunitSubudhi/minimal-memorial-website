"""Tests for configuration helpers."""

from __future__ import annotations

import pytest

from app.config import _resolve_database_uri, get_config


def test_resolve_database_uri_normalises_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/db")
    try:
        result = _resolve_database_uri()
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    assert result == "postgresql+psycopg://user:pass@host:5432/db"


def test_resolve_database_uri_default_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    uri = _resolve_database_uri()
    assert uri.endswith("memorial.db")
    assert uri.startswith("sqlite")


@pytest.mark.parametrize(
    "name, expected_cls",
    [
        (None, "BaseConfig"),
        ("development", "DevelopmentConfig"),
        ("testing", "TestingConfig"),
        ("production", "ProductionConfig"),
        ("unknown", "BaseConfig"),
    ],
)
def test_get_config_returns_expected_class(monkeypatch, name, expected_cls):
    monkeypatch.delenv("FLASK_ENV", raising=False)
    config_cls = get_config(name)
    assert config_cls.__name__ == expected_cls
