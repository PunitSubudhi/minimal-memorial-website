#!/usr/bin/env python3
"""Data migration helper to move tribute photo payloads into S3.

This script uploads any existing ``TributePhoto`` records that still rely on
inline base64 storage to Amazon S3 and records the resulting key/URL metadata.
It is designed to be resumable and safe to run multiple times.
"""

from __future__ import annotations

import argparse
import base64
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from dotenv import load_dotenv


def _ensure_project_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


_ensure_project_path()
load_dotenv()

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import TributePhoto  # noqa: E402
from app.services import s3  # noqa: E402

LOGGER = logging.getLogger("migrate_photos_to_s3")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of photos to process per database batch (default: 100)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on total photos to migrate in this run",
    )
    parser.add_argument(
        "--min-id",
        type=int,
        default=0,
        help="Resume processing starting after this photo ID",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between batches to throttle requests",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the migration without uploading or committing changes",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging output",
    )
    return parser.parse_args(argv)


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )


def generate_object_key(photo: TributePhoto) -> str:
    suffix = ".webp"
    if photo.photo_content_type:
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }.get(photo.photo_content_type.lower(), suffix)
    return f"tributes/{photo.tribute_id}/{uuid4().hex}{suffix}"


def migrate_batch(batch: list[TributePhoto], *, dry_run: bool) -> int:
    migrated = 0
    for photo in batch:
        if photo.photo_s3_key and photo.photo_url:
            continue
        if not photo.photo_b64:
            LOGGER.debug("Skipping photo %s: no base64 payload to migrate", photo.id)
            continue
        try:
            payload = base64.b64decode(photo.photo_b64)
        except Exception:  # pragma: no cover - defensive guard for corrupt data
            LOGGER.warning("Photo %s has invalid base64 payload; skipping", photo.id)
            continue

        content_type = photo.photo_content_type or "image/webp"
        object_key = generate_object_key(photo)

        if dry_run:
            LOGGER.info(
                "[dry-run] would upload tribute %s photo %s to key %s",
                photo.tribute_id,
                photo.id,
                object_key,
            )
            migrated += 1
            continue

        try:
            key, url = s3.upload_bytes(
                payload,
                content_type=content_type,
                object_key=object_key,
                metadata={"photo_id": str(photo.id), "tribute_id": str(photo.tribute_id)},
            )
        except s3.S3Error:
            LOGGER.exception("Failed to upload photo %s to S3", photo.id)
            db.session.rollback()
            continue

        photo.photo_s3_key = key
        photo.photo_url = url
        photo.migrated_at = datetime.now(timezone.utc)
        migrated += 1

    if dry_run:
        return migrated

    try:
        db.session.commit()
    except Exception:  # pragma: no cover - database failure should surface prominently
        db.session.rollback()
        LOGGER.exception("Database commit failed for current batch")
        return 0

    return migrated


def migrate_photos(*, batch_size: int, limit: int | None, min_id: int, sleep_seconds: float, dry_run: bool) -> None:
    total_migrated = 0
    last_id = max(min_id, 0)

    while True:
        query = (
            db.session.query(TributePhoto)
            .filter(TributePhoto.id > last_id)
            .filter(TributePhoto.photo_s3_key.is_(None))
            .filter(TributePhoto.photo_url.is_(None))
            .filter(TributePhoto.photo_b64.isnot(None))
            .order_by(TributePhoto.id.asc())
            .limit(batch_size)
        )
        batch = list(query)
        if not batch:
            break

        LOGGER.info(
            "Processing batch with photo IDs %s-%s", batch[0].id, batch[-1].id
        )

        migrated = migrate_batch(batch, dry_run=dry_run)
        total_migrated += migrated
        last_id = batch[-1].id

        if limit is not None and total_migrated >= limit:
            LOGGER.info("Reached migration limit of %s rows", limit)
            break

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    LOGGER.info("Migration complete; processed %s photos", total_migrated)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    app = create_app()
    if not app.config.get("S3_BUCKET_NAME"):
        LOGGER.error("S3 bucket configuration is missing. Aborting migration.")
        return 1

    with app.app_context():
        migrate_photos(
            batch_size=max(args.batch_size, 1),
            limit=args.limit,
            min_id=args.min_id,
            sleep_seconds=max(args.sleep, 0.0),
            dry_run=args.dry_run,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
