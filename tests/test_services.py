"""Tests for tribute service helpers."""

from __future__ import annotations

from app.models import Tribute, TributePhoto
from app.services import s3, tributes


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


def test_create_tribute_with_s3_photo(app, db_session) -> None:
    """Ensure S3 metadata persists even without base64 payloads."""
    with app.app_context():
        tribute = tributes.create_tribute(
            name="S3 User",
            message="Uses S3",
            photo_entries=[
                {
                    "photo_s3_key": "tributes/1/example.webp",
                    "photo_content_type": "image/webp",
                    "display_order": 0,
                }
            ],
        )

        stored = db_session.get(TributePhoto, tribute.photos[0].id)
        assert stored is not None
        assert stored.photo_s3_key == "tributes/1/example.webp"
        assert stored.photo_url is None
        assert stored.photo_b64 is None


def test_generate_presigned_get_url_uses_configured_ttl(app, monkeypatch) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def generate_presigned_url(self, operation_name, **kwargs):  # type: ignore[no-untyped-def]
            self.calls.append(
                {
                    "operation_name": operation_name,
                    "params": kwargs.get("Params"),
                    "expires": kwargs.get("ExpiresIn"),
                    "method": kwargs.get("HttpMethod"),
                }
            )
            return "https://signed.example.com"

    with app.app_context():
        app.config["S3_BUCKET_NAME"] = "test-bucket"
        app.config["S3_PRESIGNED_TTL"] = 180
        fake_client = FakeClient()
        monkeypatch.setattr(s3, "_get_client", lambda: fake_client)

        url = s3.generate_presigned_get_url("path/to/object")

        assert url == "https://signed.example.com"
        assert fake_client.calls == [
            {
                "operation_name": "get_object",
                "params": {"Bucket": "test-bucket", "Key": "path/to/object"},
                "expires": 180,
                "method": "GET",
            }
        ]


def test_generate_presigned_get_url_respects_override(app, monkeypatch) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.expires = None

        def generate_presigned_url(self, operation_name, **kwargs):  # type: ignore[no-untyped-def]
            self.expires = kwargs.get("ExpiresIn")
            return "https://signed.example.com/override"

    with app.app_context():
        app.config["S3_BUCKET_NAME"] = "test-bucket"
        app.config["S3_PRESIGNED_TTL"] = 180
        fake_client = FakeClient()
        monkeypatch.setattr(s3, "_get_client", lambda: fake_client)

        url = s3.generate_presigned_get_url("asset", expires_in=45)

        assert url == "https://signed.example.com/override"
        assert fake_client.expires == 45
