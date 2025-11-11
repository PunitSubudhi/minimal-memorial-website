"""Helpers for validating, normalizing, and storing tribute photo uploads."""

from __future__ import annotations

import io
import logging
from flask import current_app, has_app_context
from typing import Iterable, List, Optional

from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from . import s3

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
) -> tuple[List[dict[str, object]], bool]:
    """Normalize uploads and push them to S3 storage.

    Returns a tuple of (prepared_entries, had_rejection) where had_rejection
    flags that one or more photos were skipped because they could not be
    processed or uploaded."""
    prepared: List[dict[str, object]] = []
    log = logger or LOGGER
    size_cap = _resolve_max_bytes(max_bytes)
    had_rejection = False

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
                had_rejection = True
            continue

        entry = {
            "photo_content_type": _WEBP_MIME,
            "display_order": index,
        }

        upload_key, _ = _store_in_s3(
            payload_bytes,
            content_type=_WEBP_MIME,
            filename_hint=filename,
            logger=log,
        )

        if not upload_key:
            had_rejection = True
            log.warning(
                "Skipping file %s: failed to store photo in S3, entry discarded",
                filename,
            )
            continue

        entry["photo_s3_key"] = upload_key

        prepared.append(entry)

    return prepared, had_rejection


def _store_in_s3(
    payload: bytes,
    *,
    content_type: str,
    filename_hint: str,
    logger: logging.Logger,
) -> tuple[Optional[str], Optional[str]]:
    if not has_app_context():
        return None, None
    if not current_app.config.get("S3_BUCKET_NAME"):
        return None, None
    try:
        key, url = s3.upload_bytes(
            payload,
            content_type=content_type,
            filename_hint=filename_hint,
        )
        return key, url
    except s3.S3ConfigurationError:
        logger.error("S3 configuration missing; cannot store photo uploads")
    except s3.S3Error:
        logger.warning("Failed to upload photo to S3; photo will be skipped", exc_info=True)
    except Exception:  # pragma: no cover - unexpected failure during upload
        logger.exception("Unexpected error uploading photo to S3; photo will be skipped")
    return None, None


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
