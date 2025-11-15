"""Service helpers for managing tribute records."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from ..extensions import db
from ..models import Tribute, TributePhoto
from sqlalchemy.orm import selectinload

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TributePage:
    """Simple pagination payload for tribute listings."""

    items: list[Tribute]
    page: int
    per_page: int
    has_next: bool
    has_prev: bool
    next_page: int | None
    prev_page: int | None


def create_tribute(
    *,
    name: str,
    message: str,
    photo_entries: Iterable[Mapping[str, object]],
    phone: Optional[str] = None,
    email: Optional[str] = None,
    extra_fields: Optional[dict] = None,
    logger: Optional[logging.Logger] = None,
) -> Tribute:
    """Persist a tribute and any associated photo records."""
    log = logger or LOGGER

    # Merge contact info into extra_fields
    fields = extra_fields or {}
    if phone:
        fields["phone"] = phone.strip()
    if email:
        fields["email"] = email.strip().lower()

    tribute = Tribute(
        name=name.strip(),
        message=message.strip(),
        extra_fields=fields,
    )
    db.session.add(tribute)

    for entry in photo_entries:
        photo_b64 = str(entry.get("photo_b64", "")) if entry.get("photo_b64") else None
        photo_s3_key = (
            str(entry.get("photo_s3_key")) if entry.get("photo_s3_key") else None
        )
        content_type = str(entry.get("photo_content_type", ""))
        display_order = int(entry.get("display_order", 0))
        caption = entry.get("caption")
        if not (photo_b64 or photo_s3_key):
            continue
        tribute.photos.append(
            TributePhoto(
                photo_b64=photo_b64,
                photo_s3_key=photo_s3_key,
                photo_content_type=content_type or "image/webp",
                display_order=display_order,
                caption=str(caption) if caption is not None else None,
            )
        )

    db.session.commit()
    log.info("Created tribute %s with %s photos", tribute.id, len(tribute.photos))
    return tribute


def paginate_tributes(
    *,
    page: int,
    per_page: int,
    max_per_page: int | None = None,
) -> TributePage:
    """Return a paginated batch of tributes ordered by newest first."""

    page_number = page if page > 0 else 1
    limit = per_page if per_page > 0 else 1

    if max_per_page is not None and max_per_page > 0:
        limit = min(limit, max_per_page)

    base_query = (
        Tribute.query.options(selectinload(Tribute.photos))
        .order_by(Tribute.created_at.desc())
    )

    offset = (page_number - 1) * limit
    models = base_query.offset(offset).limit(limit + 1).all()

    has_next = len(models) > limit
    if has_next:
        items = models[:-1]
    else:
        items = models

    has_prev = page_number > 1

    return TributePage(
        items=items,
        page=page_number,
        per_page=limit,
        has_next=has_next,
        has_prev=has_prev,
        next_page=page_number + 1 if has_next else None,
        prev_page=page_number - 1 if has_prev else None,
    )
