"""Tests for tribute service helpers."""

from __future__ import annotations

from app.models import Tribute, TributePhoto
from app.services import tributes


def test_create_tribute_persists_data(app, db_session) -> None:
    with app.app_context():
        tribute = tributes.create_tribute(
            name="Test Name",
            message="Heartfelt message",
            photo_entries=[
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


def test_create_tribute_with_contact_info(app, db_session) -> None:
    """Verify phone and email are stored in extra_fields."""
    with app.app_context():
        tribute = tributes.create_tribute(
            name="John Doe",
            message="Test message",
            photo_entries=[],
            phone="555-1234",
            email="john@example.com",
        )

        assert tribute.extra_fields["phone"] == "555-1234"
        assert tribute.extra_fields["email"] == "john@example.com"

        stored = db_session.get(Tribute, tribute.id)
        assert stored is not None
        assert stored.extra_fields["phone"] == "555-1234"
        assert stored.extra_fields["email"] == "john@example.com"


def test_create_tribute_without_contact_info(app, db_session) -> None:
    """Verify tribute works without phone/email."""
    with app.app_context():
        tribute = tributes.create_tribute(
            name="Jane Doe",
            message="Test message",
            photo_entries=[],
        )

        assert "phone" not in tribute.extra_fields
        assert "email" not in tribute.extra_fields
