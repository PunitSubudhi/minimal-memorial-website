"""Tests for WTForms validation helpers."""

from __future__ import annotations

from io import BytesIO

from werkzeug.datastructures import FileStorage

from app.forms import TributeForm


def _make_file(name: str) -> FileStorage:
    return FileStorage(stream=BytesIO(b"mock-data"), filename=name, content_type="image/png")


def test_validate_photos_allows_configured_extensions(app):
    with app.test_request_context("/tributes", method="POST"):
        app.config["ALLOWED_EXTENSIONS"] = ("png", "jpg")
        form = TributeForm(meta={"csrf": False})
        form.name.data = "Tester"
        form.message.data = "Hello"
        form.photos.data = [_make_file("photo.png")]

        assert form.validate() is True


def test_validate_photos_rejects_disallowed_extensions(app):
    with app.test_request_context("/tributes", method="POST"):
        app.config["ALLOWED_EXTENSIONS"] = ("jpg",)
        form = TributeForm(meta={"csrf": False})
        form.name.data = "Tester"
        form.message.data = "Hello"
        form.photos.data = [_make_file("photo.gif")]

        assert form.validate() is False
        assert "unsupported format" in form.photos.errors[0]


def test_validate_photos_ignores_entries_without_filename(app):
    with app.test_request_context("/tributes", method="POST"):
        app.config["ALLOWED_EXTENSIONS"] = ("png",)
        form = TributeForm(meta={"csrf": False})
        form.name.data = "Tester"
        form.message.data = "Hello"
        storage = _make_file("photo.png")
        storage.filename = ""
        form.photos.data = [storage]

        assert form.validate() is True
