"""Service helpers for managing tribute records."""

from __future__ import annotations

import logging
from typing import Iterable, Mapping, Optional

from ..extensions import db
from ..models import Tribute, TributePhoto

LOGGER = logging.getLogger(__name__)


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
        photo_b64 = str(entry.get("photo_b64", ""))
        content_type = str(entry.get("photo_content_type", ""))
        display_order = int(entry.get("display_order", 0))
        caption = entry.get("caption")
        if not photo_b64:
            continue
        tribute.photos.append(
            TributePhoto(
                photo_b64=photo_b64,
                photo_content_type=content_type or "image/webp",
                display_order=display_order,
                caption=str(caption) if caption is not None else None,
            )
        )

    db.session.commit()
    log.info("Created tribute %s with %s photos", tribute.id, len(tribute.photos))
    return tribute
