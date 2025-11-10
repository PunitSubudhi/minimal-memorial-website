"""Route-level integration tests."""

from __future__ import annotations

from app.models import Tribute
from app.services import notifications


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

        tribute = tributes.create_tribute(
            name="Test User",
            message="Test message",
            photo_entries=[],
            phone="555-1234",
            email="test@example.com",
        )

        response = client.get(f"/tributes/{tribute.id}")
        assert b"555-1234" not in response.data
        assert b"test@example.com" not in response.data


def test_tribute_listing_hides_contact_info(client, app) -> None:
    """Ensure phone/email never appear in tribute listing."""
    with app.app_context():
        from app.services import tributes

        tribute = tributes.create_tribute(
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

        tribute = tributes.create_tribute(
            name="Test User",
            message="Test message",
            photo_entries=[],
        )

        response = client.get(f"/admin/delete/tribute/{tribute.id}")
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

        tribute = tributes.create_tribute(
            name="Test User",
            message="Test message",
            photo_entries=[],
        )
        tribute_id = tribute.id

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

        tribute = tributes.create_tribute(
            name="Test User",
            message="Test message",
            photo_entries=[],
        )
        tribute_id = tribute.id

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
