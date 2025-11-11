"""Route-level integration tests."""

from __future__ import annotations

from app.models import Tribute
from app.services import notifications, s3
from app.routes import (
    _collect_carousel_images,
    _get_cached_tributes,
    _resolve_cache_ttl,
    _resolve_photo_src,
)


def test_index_get_renders(client) -> None:
    response = client.get("/tributes")
    assert response.status_code == 200
    assert b"Share a Tribute" in response.data


def test_index_post_creates_tribute(client, app, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_notify(**payload):  # type: ignore[no-untyped-def]
        captured.update(payload)

    monkeypatch.setattr(notifications, "notify_new_tribute", fake_notify)

    response = client.post(
        "/tributes",
        data={"name": "Tester", "message": "A memory"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Thank you for sharing your tribute." in response.data

    with app.app_context():
        tribute_count = Tribute.query.count()
        assert tribute_count == 1
        tribute = Tribute.query.first()
        assert tribute is not None
        assert tribute.name == "Tester"
        assert captured["tribute_id"] == tribute.id


def test_index_uses_presigned_urls(client, app, monkeypatch) -> None:
    with app.app_context():
        from app.services import tributes

        tribute_id = tributes.create_tribute(
            name="Signed",
            message="Uses presign",
            photo_entries=[
                {
                    "photo_s3_key": "tributes/99/sample.webp",
                    "photo_content_type": "image/webp",
                    "display_order": 0,
                }
            ],
        ).id

    monkeypatch.setattr(
        s3,
        "generate_presigned_get_url",
        lambda key, **_: f"https://signed.example.com/{key}",
    )

    response = client.get("/tributes")

    assert response.status_code == 200
    assert b"https://signed.example.com/tributes/99/sample.webp" in response.data
    assert tribute_id is not None


def test_detail_uses_presigned_urls(client, app, monkeypatch) -> None:
    with app.app_context():
        from app.services import tributes

        tribute = tributes.create_tribute(
            name="Detail",
            message="Detail presign",
            photo_entries=[
                {
                    "photo_s3_key": "tributes/100/detail.webp",
                    "photo_content_type": "image/webp",
                    "display_order": 0,
                }
            ],
        )

        tribute_id = tribute.id

    monkeypatch.setattr(
        s3,
        "generate_presigned_get_url",
        lambda key, **_: f"https://signed.example.com/{key}",
    )

    response = client.get(f"/tributes/{tribute_id}")

    assert response.status_code == 200
    assert b"https://signed.example.com/tributes/100/detail.webp" in response.data


def test_tribute_submission_with_contact(client, app) -> None:
    """Verify form accepts phone/email."""
    response = client.post(
        "/tributes",
        data={
            "name": "Test User",
            "message": "Test message",
            "phone": "(555) 123-4567",
            "email": "test@example.com",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Thank you for sharing" in response.data

    with app.app_context():
        tribute = Tribute.query.first()
        assert tribute is not None
        assert tribute.extra_fields.get("phone") == "(555) 123-4567"
        assert tribute.extra_fields.get("email") == "test@example.com"


def test_tribute_submission_invalid_phone(client) -> None:
    """Verify invalid phone format is rejected."""
    response = client.post(
        "/tributes",
        data={
            "name": "Test User",
            "message": "Test message",
            "phone": "invalid phone!!!",
        },
    )

    assert b"Invalid phone number format" in response.data


def test_tribute_submission_invalid_email(client) -> None:
    """Verify invalid email format is rejected."""
    response = client.post(
        "/tributes",
        data={
            "name": "Test User",
            "message": "Test message",
            "email": "not-an-email",
        },
    )

    assert b"Invalid email address" in response.data


def test_tribute_detail_hides_contact_info(client, app) -> None:
    """Ensure phone/email never appear in rendered HTML."""
    with app.app_context():
        from app.services import tributes

        tribute_id = tributes.create_tribute(
            name="Test User",
            message="Test message",
            photo_entries=[],
            phone="555-1234",
            email="test@example.com",
        ).id

        response = client.get(f"/tributes/{tribute_id}")
        assert b"555-1234" not in response.data
        assert b"test@example.com" not in response.data


def test_tribute_listing_hides_contact_info(client, app) -> None:
    """Ensure phone/email never appear in tribute listing."""
    with app.app_context():
        from app.services import tributes

        _ = tributes.create_tribute(
            name="Test User",
            message="Test message",
            photo_entries=[],
            phone="555-9999",
            email="hidden@example.com",
        )

        response = client.get("/tributes")
        assert b"555-9999" not in response.data
        assert b"hidden@example.com" not in response.data


def test_admin_delete_get_shows_form(client, app) -> None:
    """Verify GET request to admin delete shows authentication form."""
    with app.app_context():
        from app.services import tributes

        tribute_id = tributes.create_tribute(
            name="Test User",
            message="Test message",
            photo_entries=[],
        ).id

        response = client.get(f"/admin/delete/tribute/{tribute_id}")
        assert response.status_code == 200
        assert b"Admin Username" in response.data
        assert b"Admin Password" in response.data
        assert b"Delete Tribute" in response.data


def test_admin_delete_with_valid_credentials(client, app, monkeypatch) -> None:
    """Verify tribute is deleted with valid admin credentials."""
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret123")
    app.config["ADMIN_USERNAME"] = "admin"
    app.config["ADMIN_PASSWORD"] = "secret123"

    with app.app_context():
        from app.services import tributes

        tribute_id = tributes.create_tribute(
            name="Test User",
            message="Test message",
            photo_entries=[],
        ).id

        response = client.post(
            f"/admin/delete/tribute/{tribute_id}",
            data={"username": "admin", "password": "secret123"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"has been deleted" in response.data

        # Verify tribute is actually deleted
        from app.extensions import db

        deleted = db.session.get(Tribute, tribute_id)
        assert deleted is None


def test_admin_delete_with_invalid_credentials(client, app, monkeypatch) -> None:
    """Verify tribute is NOT deleted with invalid credentials."""
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret123")
    app.config["ADMIN_USERNAME"] = "admin"
    app.config["ADMIN_PASSWORD"] = "secret123"

    with app.app_context():
        from app.services import tributes

        tribute_id = tributes.create_tribute(
            name="Test User",
            message="Test message",
            photo_entries=[],
        ).id

        response = client.post(
            f"/admin/delete/tribute/{tribute_id}",
            data={"username": "wrong", "password": "wrong"},
        )

        assert response.status_code == 200
        assert b"Invalid username or password" in response.data

        # Verify tribute still exists
        from app.extensions import db

        still_exists = db.session.get(Tribute, tribute_id)
        assert still_exists is not None


def test_tribute_submission_with_oversized_photo_saved_without_photo(
    client, app, monkeypatch
) -> None:
    """Verify tribute is saved without photo when it exceeds size limit."""
    from app.services import notifications

    captured: dict[str, object] = {}

    def fake_notify(**payload):  # type: ignore[no-untyped-def]
        captured.update(payload)

    monkeypatch.setattr(notifications, "notify_new_tribute", fake_notify)

    # Create a very small size limit to trigger size error
    app.config["MAX_PHOTO_UPLOAD_BYTES"] = 100

    response = client.post(
        "/tributes",
        data={
            "name": "Test User",
            "message": "Test message",
            "photos": [],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        tribute_count = Tribute.query.count()
        assert tribute_count == 1
        tribute = Tribute.query.first()
        assert tribute is not None
        assert tribute.name == "Test User"
        assert len(tribute.photos) == 0  # No photos should be saved
        assert captured["tribute_id"] == tribute.id


def test_resolve_cache_ttl_respects_presigned_margin(app) -> None:
    with app.app_context():
        app.config["CAROUSEL_CACHE_SECONDS"] = 200
        app.config["S3_PRESIGNED_TTL"] = 90
        ttl = _resolve_cache_ttl("CAROUSEL_CACHE_SECONDS", 300)
        assert ttl == 75


def test_collect_carousel_images_includes_presigned_and_inline(app, monkeypatch) -> None:
    with app.app_context():
        from app.services import tributes

        app.config["CAROUSEL_CACHE_SECONDS"] = 120
        app.config["S3_PRESIGNED_TTL"] = 90

        tributes.create_tribute(
            name="Carousel",
            message="Includes images",
            photo_entries=[
                {
                    "photo_s3_key": "photos/primary.webp",
                    "photo_content_type": "image/webp",
                    "display_order": 0,
                    "caption": "Primary",
                },
                {
                    "photo_b64": "Zm9v",
                    "photo_content_type": "image/webp",
                    "display_order": 1,
                    "caption": "Inline",
                },
            ],
        )

        monkeypatch.setattr(
            s3,
            "generate_presigned_get_url",
            lambda key, **_: f"https://signed.example/{key}",
        )

        items = _collect_carousel_images(limit=2)

    assert len(items) == 2
    sources = {entry["src"]: entry for entry in items}
    assert "https://signed.example/photos/primary.webp" in sources
    assert sources["https://signed.example/photos/primary.webp"]["alt"] == "Primary"
    assert any(src.startswith("data:image/webp;base64,") for src in sources)


def test_get_cached_tributes_returns_cached_results(app) -> None:
    with app.app_context():
        from app.services import tributes

        app.config["TRIBUTES_CACHE_SECONDS"] = 120

        tributes.create_tribute(
            name="Cache One",
            message="First",
            photo_entries=[],
        )

        first = _get_cached_tributes(limit=1)
        tributes.create_tribute(
            name="Cache Two",
            message="Second",
            photo_entries=[],
        )

        second = _get_cached_tributes(limit=1)

    assert len(first) == len(second) == 1
    assert second[0].message == first[0].message


def test_resolve_photo_src_handles_presign_failures(app, monkeypatch) -> None:
    with app.app_context():
        monkeypatch.setattr(
            s3,
            "generate_presigned_get_url",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(s3.S3PresignError("boom")),
        )

        payload = {
            "photo_s3_key": "photos/key.webp",
            "photo_url": "https://existing/photo.webp",
            "photo_b64": "Zm9v",
            "photo_content_type": "image/webp",
        }

        resolved = _resolve_photo_src(payload)

    assert resolved == "https://existing/photo.webp"


def test_resolve_photo_src_uses_base64_payload() -> None:
    payload = {
        "photo_b64": "Zm9v",
        "photo_content_type": "image/webp",
    }
    resolved = _resolve_photo_src(payload)
    assert resolved == "data:image/webp;base64,Zm9v"
