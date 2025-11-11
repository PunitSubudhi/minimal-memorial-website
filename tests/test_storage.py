"""Tests for image storage helpers."""

from __future__ import annotations

import io

from PIL import Image
from werkzeug.datastructures import FileStorage

from app.services import storage


def _make_png(color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    image = Image.new("RGB", (10, 10), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _make_large_bmp(size: int = 600) -> bytes:
    image = Image.effect_noise((size, size), 100).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="BMP")
    return buffer.getvalue()


def _configure_s3_stub(app, monkeypatch):
    captured: list[dict[str, object]] = []

    def _fake_upload(payload, **kwargs):
        captured.append({"payload": payload, "kwargs": kwargs})
        return ("tributes/1/upload.webp", "https://cdn/u")

    with app.app_context():
        app.config["S3_BUCKET_NAME"] = "test-bucket"
        monkeypatch.setattr(storage.s3, "upload_bytes", _fake_upload)

    return captured


def test_prepare_photo_entries_converts_png_to_webp(app, monkeypatch) -> None:
    data = _make_png()
    file_storage = FileStorage(
        stream=io.BytesIO(data),
        filename="test.png",
        content_type="image/png",
    )

    captures = _configure_s3_stub(app, monkeypatch)

    with app.app_context():
        result, had_rejection = storage.prepare_photo_entries([file_storage])

    assert len(result) == 1
    assert not had_rejection
    entry = result[0]
    assert entry["photo_content_type"] == "image/webp"
    assert entry["photo_s3_key"].endswith("upload.webp")
    assert captures and captures[0]["payload"][:4] == b"RIFF"
    assert b"WEBP" in captures[0]["payload"][:16]


def test_prepare_photo_entries_skips_invalid_images(app, monkeypatch) -> None:
    file_storage = FileStorage(
        stream=io.BytesIO(b"not an image"),
        filename="broken.png",
        content_type="image/png",
    )

    captures = _configure_s3_stub(app, monkeypatch)

    with app.app_context():
        result, had_rejection = storage.prepare_photo_entries([file_storage])

    assert result == []
    assert not had_rejection
    assert captures == []


def test_prepare_photo_entries_compresses_large_images(app, monkeypatch) -> None:
    data = _make_large_bmp()
    assert len(data) > 1_048_576

    unrestricted = FileStorage(
        stream=io.BytesIO(data),
        filename="noise.bmp",
        content_type="image/bmp",
    )

    captures_unrestricted = _configure_s3_stub(app, monkeypatch)

    with app.app_context():
        unrestricted_result, had_rejection_unrestricted = storage.prepare_photo_entries(
            [unrestricted], max_bytes=0
        )

    assert unrestricted_result
    assert not had_rejection_unrestricted
    unrestricted_size = len(captures_unrestricted[0]["payload"])

    constrained = FileStorage(
        stream=io.BytesIO(data),
        filename="noise.bmp",
        content_type="image/bmp",
    )
    limit = 400_000

    captures_constrained = _configure_s3_stub(app, monkeypatch)

    with app.app_context():
        constrained_result, had_rejection_constrained = storage.prepare_photo_entries(
            [constrained], max_bytes=limit
        )

    assert len(constrained_result) == 1
    assert not had_rejection_constrained
    constrained_size = len(captures_constrained[0]["payload"])
    assert constrained_size <= limit
    assert constrained_size <= unrestricted_size


def test_prepare_photo_entries_flags_size_error(app, monkeypatch) -> None:
    """Verify rejection flag is set when image cannot fit within size limit."""
    # Create a large image that will fail to compress below a tiny limit
    data = _make_large_bmp(size=200)
    file_storage = FileStorage(
        stream=io.BytesIO(data),
        filename="large.bmp",
        content_type="image/bmp",
    )

    # Use a very restrictive size limit (100 bytes)
    _configure_s3_stub(app, monkeypatch)

    with app.app_context():
        result, had_rejection = storage.prepare_photo_entries(
            [file_storage], max_bytes=100
        )

    assert result == []
    assert had_rejection is True


def test_prepare_photo_entries_uses_s3_when_configured(app, monkeypatch) -> None:
    data = _make_png()
    file_storage = FileStorage(
        stream=io.BytesIO(data),
        filename="upload.png",
        content_type="image/png",
    )

    captures = _configure_s3_stub(app, monkeypatch)

    with app.app_context():
        result, had_rejection = storage.prepare_photo_entries([file_storage])

    assert had_rejection is False
    assert result[0]["photo_s3_key"] == "tributes/1/upload.webp"
    assert captures


def test_prepare_photo_entries_skips_on_s3_failure(app, monkeypatch) -> None:
    data = _make_png()
    file_storage = FileStorage(
        stream=io.BytesIO(data),
        filename="fallback.png",
        content_type="image/png",
    )

    def _raise(*_args, **_kwargs):
        raise storage.s3.S3Error("failed")

    with app.app_context():
        app.config["S3_BUCKET_NAME"] = "test-bucket"
        monkeypatch.setattr(storage.s3, "upload_bytes", _raise)

        result, had_rejection = storage.prepare_photo_entries([file_storage])

    assert had_rejection is True
    assert result == []
