"""Tests for image storage helpers."""

from __future__ import annotations

import base64
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


def test_prepare_photo_entries_converts_png_to_webp() -> None:
    data = _make_png()
    file_storage = FileStorage(
        stream=io.BytesIO(data),
        filename="test.png",
        content_type="image/png",
    )

    result, had_size_error = storage.prepare_photo_entries([file_storage])

    assert len(result) == 1
    assert not had_size_error
    entry = result[0]
    assert entry["photo_content_type"] == "image/webp"

    decoded = base64.b64decode(entry["photo_b64"])
    # Valid WebP files start with "RIFF" header and contain "WEBP"
    assert decoded[:4] == b"RIFF"
    assert b"WEBP" in decoded[:16]


def test_prepare_photo_entries_skips_invalid_images() -> None:
    file_storage = FileStorage(
        stream=io.BytesIO(b"not an image"),
        filename="broken.png",
        content_type="image/png",
    )

    result, had_size_error = storage.prepare_photo_entries([file_storage])

    assert result == []
    assert not had_size_error


def test_prepare_photo_entries_compresses_large_images() -> None:
    data = _make_large_bmp()
    assert len(data) > 1_048_576

    unrestricted = FileStorage(
        stream=io.BytesIO(data),
        filename="noise.bmp",
        content_type="image/bmp",
    )
    unrestricted_result, had_size_error_unrestricted = storage.prepare_photo_entries([unrestricted], max_bytes=0)
    assert unrestricted_result
    assert not had_size_error_unrestricted
    unrestricted_size = len(base64.b64decode(unrestricted_result[0]["photo_b64"]))

    constrained = FileStorage(
        stream=io.BytesIO(data),
        filename="noise.bmp",
        content_type="image/bmp",
    )
    limit = 400_000
    constrained_result, had_size_error_constrained = storage.prepare_photo_entries([constrained], max_bytes=limit)

    assert len(constrained_result) == 1
    assert not had_size_error_constrained
    constrained_size = len(base64.b64decode(constrained_result[0]["photo_b64"]))
    assert constrained_size <= limit
    assert constrained_size <= unrestricted_size


def test_prepare_photo_entries_flags_size_error() -> None:
    """Verify had_size_error flag is set when image cannot fit within size limit."""
    # Create a large image that will fail to compress below a tiny limit
    data = _make_large_bmp(size=200)
    file_storage = FileStorage(
        stream=io.BytesIO(data),
        filename="large.bmp",
        content_type="image/bmp",
    )

    # Use a very restrictive size limit (100 bytes)
    result, had_size_error = storage.prepare_photo_entries(
        [file_storage], max_bytes=100
    )

    assert result == []
    assert had_size_error is True


def test_prepare_photo_entries_uses_s3_when_configured(app, monkeypatch) -> None:
    data = _make_png()
    file_storage = FileStorage(
        stream=io.BytesIO(data),
        filename="upload.png",
        content_type="image/png",
    )

    with app.app_context():
        app.config["S3_BUCKET_NAME"] = "test-bucket"

        monkeypatch.setattr(
            storage.s3,
            "upload_bytes",
            lambda payload, **kwargs: ("tributes/1/upload.webp", "https://cdn/u"),
        )

        result, had_size_error = storage.prepare_photo_entries([file_storage])

    assert had_size_error is False
    assert result[0]["photo_s3_key"] == "tributes/1/upload.webp"
    assert "photo_b64" not in result[0]


def test_prepare_photo_entries_falls_back_to_inline_on_s3_failure(app, monkeypatch) -> None:
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

        result, had_size_error = storage.prepare_photo_entries([file_storage])

    assert had_size_error is False
    assert "photo_b64" in result[0]
