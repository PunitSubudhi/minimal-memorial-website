"""Additional tests for models."""

from __future__ import annotations

from app.models import Tribute, TributePhoto


def test_tribute_extra_fields_default_isolated(app, db_session):
    with app.app_context():
        first = Tribute(name="First", message="One")
        second = Tribute(name="Second", message="Two")
        db_session.add_all([first, second])
        db_session.commit()

        first.extra_fields["note"] = "hello"
        assert "note" not in second.extra_fields


def test_tribute_photo_to_dict_includes_fields(app, db_session):
    with app.app_context():
        tribute = Tribute(name="Has Photo", message="Message")
        db_session.add(tribute)
        db_session.commit()

        photo = TributePhoto(
            tribute_id=tribute.id,
            photo_b64="Zm9v",
            photo_content_type="image/webp",
            display_order=1,
            caption="A caption",
            photo_s3_key="photos/key.webp",
            photo_url="https://example.com/photo.webp",
        )
        db_session.add(photo)
        db_session.commit()

        payload = photo.to_dict()
        assert payload["photo_content_type"] == "image/webp"
        assert payload["caption"] == "A caption"
        assert payload["photo_s3_key"] == "photos/key.webp"
        assert payload["photo_url"] == "https://example.com/photo.webp"
        assert payload["photo_b64"] == "Zm9v"
