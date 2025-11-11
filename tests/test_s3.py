"""Tests for S3 helper utilities."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from app.services import s3


class FakePutClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_object(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


class RetryClient(FakePutClient):
    def __init__(self) -> None:
        super().__init__()
        self._first = True

    def put_object(self, **kwargs):  # type: ignore[no-untyped-def]
        if self._first:
            self._first = False
            self.calls.append(kwargs)
            raise ClientError({"Error": {"Code": "AccessControlListNotSupported"}}, "PutObject")
        return super().put_object(**kwargs)


class FakeDeleteClient:
    def __init__(self, *, missing_ok: bool = True) -> None:
        self.called = False
        self._missing_ok = missing_ok

    def delete_object(self, **kwargs):  # type: ignore[no-untyped-def]
        self.called = True
        if self._missing_ok:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "DeleteObject")
        raise ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")


class FakePresignClient:
    def __init__(self) -> None:
        self.captured: dict | None = None

    def generate_presigned_url(self, operation_name, **kwargs):  # type: ignore[no-untyped-def]
        self.captured = {
            "operation": operation_name,
            "params": kwargs.get("Params"),
            "expires": kwargs.get("ExpiresIn"),
            "method": kwargs.get("HttpMethod"),
        }
        return "https://signed.example.com/payload"


@pytest.fixture(autouse=True)
def _reset_s3_extensions(app):
    with app.app_context():
        extensions = app.extensions
        extensions.pop(s3._EXTENSION_KEY, None)
        extensions.pop(s3._ACL_DISABLED_FLAG, None)
        yield
        extensions.pop(s3._EXTENSION_KEY, None)
        extensions.pop(s3._ACL_DISABLED_FLAG, None)


def test_upload_bytes_generates_prefixed_key_and_public_url(app, monkeypatch):
    fake_client = FakePutClient()

    with app.app_context():
        app.config.update(
            {
                "S3_BUCKET_NAME": "test-bucket",
                "S3_BUCKET_PREFIX": "tributes/",
                "S3_PUBLIC_BASE_URL": "https://cdn.example.com/assets",
                "S3_PRESIGNED_TTL": 60,
            }
        )

        monkeypatch.setattr(s3, "_get_client", lambda: fake_client)
        monkeypatch.setattr(s3, "uuid4", lambda: SimpleNamespace(hex="deadbeef"))

        key, url = s3.upload_bytes(
            b"payload",
            content_type="image/webp",
            filename_hint="photo.png",
            metadata={"answer": 42},
        )

        assert key == "tributes/deadbeef.png"
        assert url == "https://cdn.example.com/assets/tributes/deadbeef.png"
        assert fake_client.calls[0]["Bucket"] == "test-bucket"
        assert fake_client.calls[0]["Metadata"] == {"answer": "42"}
        assert fake_client.calls[0]["CacheControl"].startswith("public")
        assert fake_client.calls[0]["ACL"] == "public-read"


def test_upload_bytes_retries_without_acl_on_rejection(app, monkeypatch):
    retry_client = RetryClient()

    with app.app_context():
        app.config.update(
            {
                "S3_BUCKET_NAME": "retry-bucket",
                "S3_BUCKET_PREFIX": "uploads/",
            }
        )

        monkeypatch.setattr(s3, "_get_client", lambda: retry_client)
        monkeypatch.setattr(s3, "uuid4", lambda: SimpleNamespace(hex="cafebabe"))

        key, _ = s3.upload_bytes(b"content", content_type="image/jpeg")

        assert key == "uploads/cafebabe.jpg"
        assert len(retry_client.calls) == 2
        assert "ACL" in retry_client.calls[0]
        assert "ACL" not in retry_client.calls[1]
        assert app.extensions[s3._ACL_DISABLED_FLAG] is True


def test_delete_object_ignores_missing_key_when_allowed(app, monkeypatch):
    client = FakeDeleteClient()

    with app.app_context():
        app.config["S3_BUCKET_NAME"] = "delete-bucket"
        monkeypatch.setattr(s3, "_get_client", lambda: client)

        s3.delete_object("missing/file.jpg", ignore_missing=True)
        assert client.called is True


def test_delete_object_raises_for_unexpected_error(app, monkeypatch):
    client = FakeDeleteClient(missing_ok=False)

    with app.app_context():
        app.config["S3_BUCKET_NAME"] = "delete-bucket"
        monkeypatch.setattr(s3, "_get_client", lambda: client)

        with pytest.raises(s3.S3DeleteError):
            s3.delete_object("denied/file.jpg", ignore_missing=True)


def test_build_public_url_uses_region_when_base_missing(app):
    with app.app_context():
        app.config.update(
            {
                "S3_BUCKET_NAME": "region-bucket",
                "AWS_REGION": "us-west-2",
                "S3_PUBLIC_BASE_URL": "",
                "S3_PUBLIC_DOMAIN": "",
            }
        )
        url = s3.build_public_url("photos/example.jpg")
        assert url == "https://region-bucket.s3.us-west-2.amazonaws.com/photos/example.jpg"


def test_build_public_url_validates_key(app):
    with app.app_context():
        with pytest.raises(ValueError):
            s3.build_public_url("")


def test_generate_presigned_get_url_respects_override(app, monkeypatch):
    presign_client = FakePresignClient()

    with app.app_context():
        app.config.update({"S3_BUCKET_NAME": "presign-bucket", "S3_PRESIGNED_TTL": 120})
        monkeypatch.setattr(s3, "_get_client", lambda: presign_client)

        url = s3.generate_presigned_get_url("photos/item.jpg", expires_in=45)

        assert url == "https://signed.example.com/payload"
        assert presign_client.captured == {
            "operation": "get_object",
            "params": {"Bucket": "presign-bucket", "Key": "photos/item.jpg"},
            "expires": 45,
            "method": "GET",
        }


def test_resolve_presigned_ttl_defaults_and_overrides(app):
    with app.app_context():
        app.config["S3_PRESIGNED_TTL"] = -1
        assert s3._resolve_presigned_ttl(None) == 300
        assert s3._resolve_presigned_ttl(0) == 300
        assert s3._resolve_presigned_ttl(60) == 60


@pytest.mark.parametrize(
    "value, expected",
    [
        (True, True),
        (False, False),
        ("true", True),
        ("FALSE", False),
        ("yes", True),
        ("0", False),
        (None, False),
    ],
)
def test_as_bool_handles_various_inputs(value, expected):
    assert s3._as_bool(value) is expected
