"""Helpers for interacting with Amazon S3."""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app

LOGGER = logging.getLogger(__name__)
_DEFAULT_CACHE_CONTROL = "public, max-age=31536000, immutable"
_EXTENSION_KEY = "memorial_s3_client"
_ACL_DISABLED_FLAG = "memorial_s3_acl_disabled"


class S3Error(RuntimeError):
    """Base exception for S3 helper failures."""


class S3ConfigurationError(S3Error):
    """Raised when required S3 configuration is missing."""


class S3UploadError(S3Error):
    """Raised when uploading bytes to S3 fails."""


class S3DeleteError(S3Error):
    """Raised when deleting an S3 object fails."""


def upload_bytes(
    payload: bytes,
    *,
    content_type: str,
    filename_hint: str | None = None,
    cache_control: str | None = _DEFAULT_CACHE_CONTROL,
    metadata: dict[str, Any] | None = None,
    object_key: str | None = None,
) -> tuple[str, str]:
    """Upload bytes to S3 and return the stored key and public URL."""
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise ValueError("payload must be non-empty bytes")
    resolved_key = _normalise_key(object_key, filename_hint, content_type)
    bucket = _get_bucket_name()
    client = _get_client()
    app_extensions = current_app.extensions
    acl_disabled = app_extensions.get(_ACL_DISABLED_FLAG, False)
    put_params: dict[str, Any] = {
        "Bucket": bucket,
        "Key": resolved_key,
        "Body": payload,
        "ContentType": content_type,
    }

    acl = None if acl_disabled else _resolve_acl()
    if acl:
        put_params["ACL"] = acl
    if cache_control:
        put_params["CacheControl"] = cache_control
    if metadata:
        put_params["Metadata"] = {
            str(k): str(v) for k, v in metadata.items() if v is not None
        }

    try:
        client.put_object(**put_params)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if (
            error_code == "AccessControlListNotSupported"
            and "ACL" in put_params
        ):
            LOGGER.warning(
                "Bucket %s rejects ACLs; retrying upload without ACL", bucket
            )
            put_params.pop("ACL", None)
            app_extensions[_ACL_DISABLED_FLAG] = True
            try:
                client.put_object(**put_params)
            except (BotoCoreError, ClientError) as retry_exc:
                raise S3UploadError(
                    f"Failed to upload object {resolved_key!r}: {retry_exc}"
                ) from retry_exc
        else:
            raise S3UploadError(
                f"Failed to upload object {resolved_key!r}: {exc}"
            ) from exc
    except BotoCoreError as exc:
        raise S3UploadError(
            f"Failed to upload object {resolved_key!r}: {exc}"
        ) from exc

    LOGGER.debug("Uploaded object to S3 bucket %s at key %s", bucket, resolved_key)
    return resolved_key, build_public_url(resolved_key)


def delete_object(key: str, *, ignore_missing: bool = True) -> None:
    """Remove an object from S3, optionally ignoring missing keys."""
    if not key:
        return
    bucket = _get_bucket_name()
    client = _get_client()
    normalised = key.lstrip("/")

    try:
        client.delete_object(Bucket=bucket, Key=normalised)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if ignore_missing and error_code in {"NoSuchKey", "404"}:
            LOGGER.debug("S3 object %s already absent", normalised)
            return
        raise S3DeleteError(
            f"Failed to delete object {normalised!r}: {exc}"
        ) from exc
    except BotoCoreError as exc:
        raise S3DeleteError(
            f"Failed to delete object {normalised!r}: {exc}"
        ) from exc

    LOGGER.debug("Deleted object from S3 bucket %s at key %s", bucket, normalised)


def build_public_url(key: str) -> str:
    """Construct a public URL for an object key, defaulting to S3 endpoints."""
    if not key:
        raise ValueError("key must be provided")
    normalised = key.lstrip("/")
    base_url = (
        current_app.config.get("S3_PUBLIC_BASE_URL")
        or os.getenv("S3_PUBLIC_BASE_URL")
        or current_app.config.get("S3_PUBLIC_DOMAIN")
        or os.getenv("S3_PUBLIC_DOMAIN")
        or ""
    ).strip()
    if base_url:
        base = base_url.rstrip("/")
        if not base.lower().startswith(("https://", "http://")):
            base = f"https://{base}"
        return f"{base}/{normalised}"

    bucket = _get_bucket_name()
    region = _resolve_region()
    if region and region != "us-east-1":
        return f"https://{bucket}.s3.{region}.amazonaws.com/{normalised}"
    return f"https://{bucket}.s3.amazonaws.com/{normalised}"


def _normalise_key(
    provided: str | None, filename_hint: str | None, content_type: str
) -> str:
    if provided:
        return provided.lstrip("/")

    prefix = _get_bucket_prefix()
    extension = _resolve_extension(filename_hint, content_type)
    object_name = f"{uuid4().hex}{extension}"
    if prefix:
        return f"{prefix}{object_name}"
    return object_name


def _resolve_extension(filename_hint: str | None, content_type: str) -> str:
    if filename_hint:
        suffix = Path(filename_hint).suffix
        if suffix:
            return suffix.lower()

    guessed = mimetypes.guess_extension(content_type or "")
    if guessed == ".jpe":
        return ".jpg"
    if guessed:
        return guessed.lower()
    return ""


def _get_client() -> BaseClient:
    client = current_app.extensions.get(_EXTENSION_KEY)
    if client:
        return client

    client_kwargs: dict[str, Any] = {}
    region = _resolve_region()
    if region:
        client_kwargs["region_name"] = region

    endpoint_url = current_app.config.get("S3_ENDPOINT_URL") or os.getenv(
        "S3_ENDPOINT_URL"
    )
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url

    client = boto3.client("s3", **client_kwargs)
    current_app.extensions[_EXTENSION_KEY] = client
    return client


def _resolve_acl() -> str | None:
    acl = current_app.config.get("S3_OBJECT_ACL")
    if acl:
        return str(acl)
    if _as_bool(current_app.config.get("S3_USE_OAC") or os.getenv("S3_USE_OAC")):
        return None
    return "public-read"


def _get_bucket_prefix() -> str:
    prefix = (
        current_app.config.get("S3_BUCKET_PREFIX")
        or os.getenv("S3_BUCKET_PREFIX")
        or ""
    ).strip()
    if not prefix:
        return ""
    prefix = prefix.replace("\\", "/")
    prefix = prefix.lstrip("/")
    if not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix


def _get_bucket_name() -> str:
    bucket = current_app.config.get("S3_BUCKET_NAME") or os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise S3ConfigurationError("S3 bucket name is not configured")
    return str(bucket)


def _resolve_region() -> str | None:
    region = current_app.config.get("AWS_REGION") or os.getenv("AWS_REGION")
    if region:
        return str(region)
    session_region = boto3.session.Session().region_name
    return session_region


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
