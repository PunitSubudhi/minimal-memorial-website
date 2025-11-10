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
_DEFAULT_MAX_BYTES = 1 * 1024 * 1024


def prepare_photo_entries(
    files: Iterable[FileStorage],
    *,
    logger: Optional[logging.Logger] = None,
    quality: int = 85,
    max_bytes: int | None = None,
    min_quality: int = 30,
) -> tuple[List[dict[str, str | int]], bool]:
    """Convert uploads to base64-encoded WebP payloads with optional size caps.
    
    Returns:
        A tuple of (prepared_entries, had_size_error) where had_size_error indicates
        if any photos were rejected due to exceeding the size limit.
    """
    prepared: List[dict[str, str | int]] = []
    log = logger or LOGGER
    size_cap = _resolve_max_bytes(max_bytes)
    had_size_error = False

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
            payload_bytes, smallest = _encode_with_limit(
                image,
                quality=quality,
                min_quality=min_quality,
                max_bytes=size_cap,
            )

        if payload_bytes is None:
            if smallest is None:
                log.warning("Skipping file %s: image conversion failed", filename)
            else:
                smallest_mb = len(smallest) / (1024 * 1024)
                target_mb = (size_cap or 0) / (1024 * 1024)
                log.warning(
                    "Skipping file %s: minimum achievable size %.2f MB exceeds limit %.2f MB",
                    filename,
                    smallest_mb,
                    target_mb,
                )
                had_size_error = True
            continue

        prepared.append(
            {
                "photo_b64": base64.b64encode(payload_bytes).decode("ascii"),
                "photo_content_type": _WEBP_MIME,
                "display_order": index,
            }
        )

    return prepared, had_size_error


def _encode_with_limit(
    image: Image.Image,
    *,
    quality: int,
    min_quality: int,
    max_bytes: int | None,
) -> tuple[Optional[bytes], Optional[bytes]]:
    """Return WebP bytes within ``max_bytes`` along with the smallest attempted payload."""
    best_payload: Optional[bytes] = None
    for level in _quality_candidates(quality, min_quality):
        payload = _image_to_webp_bytes(image, quality=level)
        if not payload:
            continue
        if best_payload is None or len(payload) < len(best_payload):
            best_payload = payload
        if max_bytes is None or len(payload) <= max_bytes:
            return payload, best_payload

    return (None, best_payload)


def _quality_candidates(start: int, minimum: int) -> list[int]:
    if start <= minimum:
        return [max(start, minimum)]

    levels: list[int] = []
    current = start
    while current > minimum:
        levels.append(current)
        current = max(minimum, current - 10)
    if not levels or levels[-1] != minimum:
        levels.append(minimum)
    return levels


def _image_to_webp_bytes(image: Image.Image, *, quality: int) -> Optional[bytes]:
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

    return buffer.getvalue()


def _resolve_max_bytes(value: int | None) -> Optional[int]:
    if value is None:
        return _DEFAULT_MAX_BYTES
    if value <= 0:
        return None
    return value
