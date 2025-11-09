"""Helpers for validating and normalizing tribute photo uploads."""
from __future__ import annotations

import base64
import io
import logging
from typing import Iterable, List, Optional

from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

try:  # pragma: no cover - defensive guard for optional dependency
    import pillow_heif
except ImportError:  # pragma: no cover
    pillow_heif = None
else:  # pragma: no cover
    pillow_heif.register_heif_opener()

LOGGER = logging.getLogger(__name__)
_WEBP_MIME = "image/webp"


def prepare_photo_entries(
    files: Iterable[FileStorage],
    *,
    logger: Optional[logging.Logger] = None,
    quality: int = 85,
) -> List[dict[str, str | int]]:
    """Convert uploads to base64-encoded WebP payloads."""
    prepared: List[dict[str, str | int]] = []
    log = logger or LOGGER

    for index, storage in enumerate(files or []):
        if not isinstance(storage, FileStorage):
            continue
        filename = storage.filename or ""
        if not filename:
            continue
        storage.stream.seek(0)
        raw_bytes = storage.read()
        storage.stream.seek(0)

        try:
            image_handle = Image.open(io.BytesIO(raw_bytes))
        except UnidentifiedImageError:
            log.warning("Skipping file %s: unsupported image format", filename)
            continue

        with image_handle as image:
            payload = _image_to_webp(image, quality=quality)
            if not payload:
                log.warning("Skipping file %s: image conversion failed", filename)
                continue

        prepared.append(
            {
                "photo_b64": payload,
                "photo_content_type": _WEBP_MIME,
                "display_order": index,
            }
        )

    return prepared


def _image_to_webp(image: Image.Image, *, quality: int) -> Optional[str]:
    """Convert a Pillow image to WebP and return ASCII base64 data."""
    try:
        image.load()
        converted = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    except Exception:  # pragma: no cover - unexpected Pillow failure
        return None

    buffer = io.BytesIO()
    try:
        converted.save(buffer, format="WEBP", quality=quality, method=6)
    except OSError:
        return None

    return base64.b64encode(buffer.getvalue()).decode("ascii")
