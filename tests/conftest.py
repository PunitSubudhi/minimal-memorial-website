"""Pytest fixtures for the memorial application."""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Generator, Iterator

import pytest
from flask import Flask

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from app.routes import _invalidate_carousel_cache, _invalidate_tributes_cache  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _configure_test_database_uri() -> Generator[None, None, None]:
    """Ensure tests use a dedicated SQLite database file."""
    fd, path = tempfile.mkstemp(prefix="memorial-test-", suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL_TEST"] = f"sqlite:///{path}"

    try:
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture()
def app() -> Iterator[Flask]:
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
    try:
        yield application
    finally:
        with application.app_context():
            _db.session.remove()
            _db.drop_all()


@pytest.fixture()
def db_session(app):
    """Provide a database session bound to the test app."""
    return _db.session


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_route_caches():
    """Ensure per-request caches do not leak between tests."""
    _invalidate_carousel_cache()
    _invalidate_tributes_cache()
    yield
    _invalidate_carousel_cache()
    _invalidate_tributes_cache()
