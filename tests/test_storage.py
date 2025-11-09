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

	result = storage.prepare_photo_entries([file_storage])

	assert len(result) == 1
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

	result = storage.prepare_photo_entries([file_storage])

	assert result == []


def test_prepare_photo_entries_compresses_large_images() -> None:
	data = _make_large_bmp()
	assert len(data) > 1_048_576

	unrestricted = FileStorage(
		stream=io.BytesIO(data),
		filename="noise.bmp",
		content_type="image/bmp",
	)
	unrestricted_result = storage.prepare_photo_entries([unrestricted], max_bytes=0)
	assert unrestricted_result
	unrestricted_size = len(base64.b64decode(unrestricted_result[0]["photo_b64"]))

	constrained = FileStorage(
		stream=io.BytesIO(data),
		filename="noise.bmp",
		content_type="image/bmp",
	)
	limit = 400_000
	constrained_result = storage.prepare_photo_entries([constrained], max_bytes=limit)

	assert len(constrained_result) == 1
	constrained_size = len(base64.b64decode(constrained_result[0]["photo_b64"]))
	assert constrained_size <= limit
	assert constrained_size <= unrestricted_size
