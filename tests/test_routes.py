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


def test_slideshow_page_renders(client) -> None:
    response = client.get("/slideshow")
    assert response.status_code == 200
    assert b'id="slideshow-root"' in response.data
    assert b"slideshow.js" in response.data
    assert b"data-max-message-length" in response.data


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


def test_collect_carousel_images_includes_presigned_and_inline(
    app, monkeypatch
) -> None:
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
        app.config["TRIBUTES_MAX_PER_PAGE"] = 2

        tributes.create_tribute(
            name="Cache One",
            message="First",
            photo_entries=[],
        )

        first = _get_cached_tributes(page=1, per_page=1, max_per_page=1)
        tributes.create_tribute(
            name="Cache Two",
            message="Second",
            photo_entries=[],
        )

        second = _get_cached_tributes(page=1, per_page=1, max_per_page=1)

    assert len(first["items"]) == len(second["items"]) == 1
    assert second["items"][0]["message"] == first["items"][0]["message"]


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


def test_index_paginates_tributes(client, app) -> None:
    app.config["TRIBUTES_PER_PAGE"] = 2
    app.config["TRIBUTES_MAX_PER_PAGE"] = 3

    with app.app_context():
        from app.services import tributes

        for idx in range(3):
            tributes.create_tribute(
                name=f"Person {idx}",
                message=f"Message {idx}",
                photo_entries=[],
            )

    response = client.get("/tributes")

    assert response.status_code == 200
    assert b"Person 2" in response.data
    assert b"Person 1" in response.data
    assert b"Person 0" not in response.data


def test_index_second_page_query_returns_older_batch(client, app) -> None:
    app.config["TRIBUTES_PER_PAGE"] = 1
    app.config["TRIBUTES_MAX_PER_PAGE"] = 2

    with app.app_context():
        from app.services import tributes

        tributes.create_tribute(name="Newest", message="Newest", photo_entries=[])
        tributes.create_tribute(name="Older", message="Older", photo_entries=[])

    response = client.get("/tributes?page=2")

    assert response.status_code == 200
    assert b"Older" in response.data
    assert b"Newest" not in response.data


def test_tributes_data_endpoint_returns_paginated_payload(client, app) -> None:
    app.config["TRIBUTES_PER_PAGE"] = 1
    app.config["TRIBUTES_MAX_PER_PAGE"] = 2

    with app.app_context():
        from app.services import tributes

        alpha = tributes.create_tribute(name="Alpha", message="First", photo_entries=[])
        tributes.create_tribute(name="Beta", message="Second", photo_entries=[])

    response = client.get("/tributes/data?page=2&per_page=1")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["meta"]["page"] == 2
    assert payload["meta"]["per_page"] == 1
    assert payload["meta"]["has_next"] is False
    assert len(payload["tributes"]) == 1
    assert payload["tributes"][0]["name"] == "Alpha"
    assert payload["tributes"][0]["detail_url"].endswith(f"/tributes/{alpha.id}") is True


def test_tributes_data_clamps_page_size(client, app) -> None:
    app.config["TRIBUTES_PER_PAGE"] = 2
    app.config["TRIBUTES_MAX_PER_PAGE"] = 3

    with app.app_context():
        from app.services import tributes

        tributes.create_tribute(name="Gamma", message="First", photo_entries=[])

    response = client.get("/tributes/data?per_page=99")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["meta"]["per_page"] == 3


def test_slideshow_data_endpoint_returns_ordered_payload(
    client, app, monkeypatch
) -> None:
    with app.app_context():
        from datetime import timedelta

        from app.extensions import db
        from app.services import tributes

        monkeypatch.setattr(
            s3,
            "generate_presigned_get_url",
            lambda key, **_: f"https://cdn.example/{key}",
        )

        first = tributes.create_tribute(
            name="Earlier",
            message="First message",
            photo_entries=[],
        )

        second = tributes.create_tribute(
            name="Recent",
            message="Newest message",
            photo_entries=[
                {
                    "photo_s3_key": "tributes/second.webp",
                    "photo_content_type": "image/webp",
                    "display_order": 0,
                    "caption": "Celebration",
                },
                {
                    "photo_s3_key": "tributes/second-alt.webp",
                    "photo_content_type": "image/webp",
                    "display_order": 1,
                    "caption": "Gathering",
                },
            ],
        )

        second_id = second.id

        earlier = db.session.get(Tribute, first.id)
        assert earlier is not None
        earlier.created_at = earlier.created_at - timedelta(days=1)
        db.session.commit()

    response = client.get("/slideshow/data")
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data["meta"]["count"] == 2
    assert data["tributes"][0]["id"] == second_id
    photos = data["tributes"][0]["photos"]
    assert len(photos) == 2
    assert photos[0]["url"].startswith("https://cdn.example/")
    assert photos[0]["caption"] == "Celebration"
    assert photos[1]["caption"] == "Gathering"
    assert data["tributes"][0]["text_only"] is False
    assert data["tributes"][1]["text_only"] is True
    assert "Last-Modified" in response.headers
    assert "ETag" in response.headers

    etag = response.headers["ETag"]
    cached = client.get("/slideshow/data", headers={"If-None-Match": etag})
    assert cached.status_code == 304
