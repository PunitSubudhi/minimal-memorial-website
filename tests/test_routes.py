"""Route-level integration tests."""

from __future__ import annotations

from app.models import Tribute
from app.services import notifications


def test_index_get_renders(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b"Share a Tribute" in response.data


def test_index_post_creates_tribute(client, app, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_notify(**payload):  # type: ignore[no-untyped-def]
        captured.update(payload)

    monkeypatch.setattr(notifications, "notify_new_tribute", fake_notify)

    response = client.post(
        "/",
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
