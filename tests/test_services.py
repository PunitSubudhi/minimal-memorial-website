"""Tests for tribute service helpers."""

from __future__ import annotations

from app.models import Tribute, TributePhoto
from app.services import tributes


def test_create_tribute_persists_data(app, db_session) -> None:
    with app.app_context():
        tribute = tributes.create_tribute(
            name="Test Name",
            message="Heartfelt message",
            photo_entries=
            [
                {
                    "photo_b64": "Zm9vYmFy",
                    "photo_content_type": "image/webp",
                    "display_order": 0,
                    "caption": "Caption",
                }
            ],
        )

        assert tribute.id is not None
        stored = db_session.get(Tribute, tribute.id)
        assert stored is not None
        assert stored.name == "Test Name"
        assert stored.message == "Heartfelt message"
        assert len(stored.photos) == 1
        photo: TributePhoto = stored.photos[0]
        assert photo.photo_content_type == "image/webp"
        assert photo.caption == "Caption"
