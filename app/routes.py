"""HTTP routes for the memorial application."""

from __future__ import annotations

from time import monotonic
from types import SimpleNamespace
from typing import Any, Mapping

from datetime import UTC, datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from werkzeug.http import http_date, parse_date

from .extensions import db
from .forms import AdminAuthForm, TributeForm
from .models import Tribute, TributePhoto
from .services import notifications, s3, storage, tributes

main_bp = Blueprint("main", __name__)


_CAROUSEL_CACHE: dict[int, tuple[float, list[dict[str, Any]]]] = {}
_TRIBUTES_CACHE: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}
def _parse_positive_int(
    raw_value: str | None,
    *,
    default: int,
    maximum: int | None = None,
) -> int:
    """Parse a positive integer from user input with sane fallbacks."""

    if raw_value is None:
        return default

    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default

    if parsed <= 0:
        return default

    if maximum is not None and parsed > maximum:
        return maximum

    return parsed


def _resolve_cache_ttl(config_key: str, default: int) -> int:
    raw_value = current_app.config.get(config_key, default)
    try:
        ttl = int(raw_value)
    except (TypeError, ValueError):
        ttl = default

    if ttl <= 0:
        return 0

    presigned_raw = current_app.config.get("S3_PRESIGNED_TTL", 0)
    try:
        presigned_ttl = int(presigned_raw)
    except (TypeError, ValueError):
        presigned_ttl = 0

    if presigned_ttl > 0:
        safety_margin = 15 if presigned_ttl > 30 else 5
        max_allowed = max(presigned_ttl - safety_margin, 1)
        ttl = min(ttl, max_allowed)

    return ttl


@main_bp.route("/tributes", methods=["GET", "POST"])
def index() -> str:
    form = TributeForm()
    config = current_app.config
    default_per_page = int(config.get("TRIBUTES_PER_PAGE", config.get("TRIBUTES_PAGE_SIZE", 12)))
    max_per_page = int(config.get("TRIBUTES_MAX_PER_PAGE", default_per_page))
    requested_page = _parse_positive_int(request.args.get("page"), default=1)
    per_page = default_per_page

    if form.validate_on_submit():
        entries, had_rejection = storage.prepare_photo_entries(
            form.photos.data or [],
            logger=current_app.logger,
            max_bytes=current_app.config.get("MAX_PHOTO_UPLOAD_BYTES"),
        )
        if had_rejection:
            flash(
                "Some photos could not be processed or uploaded and were skipped.",
                "warning",
            )
        try:
            tribute = tributes.create_tribute(
                name=form.name.data,
                message=form.message.data,
                photo_entries=entries,
                phone=form.phone.data,
                email=form.email.data,
            )
        except Exception:  # pragma: no cover - defensive server guard
            db.session.rollback()
            current_app.logger.exception("Failed to create tribute")
            flash(
                "We were unable to save your tribute. Please try again.",
                "danger",
            )
        else:
            notifications.notify_new_tribute(
                tribute_id=tribute.id,
                tribute_name=tribute.name,
                tribute_message=tribute.message,
            )
            _invalidate_carousel_cache()
            _invalidate_tributes_cache()
            flash("Thank you for sharing your tribute.", "success")
            return redirect(url_for("main.index"))

    payload = _get_cached_tributes(
        page=requested_page,
        per_page=per_page,
        max_per_page=max_per_page,
    )
    tributes_payload = payload["items"]
    pagination_meta = payload["meta"]

    tributes_namespace = [_namespace_tribute(item) for item in tributes_payload]

    pagination = {
        **pagination_meta,
        "next_page_url": (
            url_for("main.index", page=pagination_meta["next_page"])
            if pagination_meta.get("next_page")
            else None
        ),
        "prev_page_url": (
            url_for("main.index", page=pagination_meta["prev_page"])
            if pagination_meta.get("prev_page")
            else None
        ),
    }

    carousel_images = _collect_carousel_images(limit=8)
    return render_template(
        "index.html",
        form=form,
        tributes=tributes_namespace,
        carousel_images=carousel_images,
        pagination=pagination,
        tributes_endpoint=url_for("main.tributes_data"),
    )


@main_bp.route("/tributes/data", methods=["GET"])
def tributes_data():
    config = current_app.config
    default_per_page = int(config.get("TRIBUTES_PER_PAGE", config.get("TRIBUTES_PAGE_SIZE", 12)))
    max_per_page = int(config.get("TRIBUTES_MAX_PER_PAGE", default_per_page))

    page = _parse_positive_int(request.args.get("page"), default=1)
    per_page = _parse_positive_int(
        request.args.get("per_page"),
        default=default_per_page,
        maximum=max_per_page,
    )

    payload = _get_cached_tributes(
        page=page,
        per_page=per_page,
        max_per_page=max_per_page,
    )

    tributes_namespace = [_namespace_tribute(item) for item in payload["items"]]
    tributes_payload: list[dict[str, Any]] = []
    latest_created: datetime | None = None

    for tribute in tributes_namespace:
        tribute_dict, created_dt = _tribute_namespace_to_dict(tribute)
        tributes_payload.append(tribute_dict)
        if created_dt is None:
            continue
        if latest_created is None or created_dt > latest_created:
            latest_created = created_dt

    pagination_meta = dict(payload["meta"])
    pagination_meta["count"] = len(tributes_payload)
    pagination_meta["per_page"] = payload["meta"].get("per_page", per_page)
    pagination_meta["next_page_url"] = (
        url_for(
            "main.tributes_data",
            page=pagination_meta["next_page"],
            per_page=pagination_meta["per_page"],
        )
        if pagination_meta.get("next_page")
        else None
    )
    pagination_meta["prev_page_url"] = (
        url_for(
            "main.tributes_data",
            page=pagination_meta["prev_page"],
            per_page=pagination_meta["per_page"],
        )
        if pagination_meta.get("prev_page")
        else None
    )
    pagination_meta["fallback_next_url"] = (
        url_for("main.index", page=pagination_meta["next_page"])
        if pagination_meta.get("next_page")
        else None
    )
    pagination_meta["fallback_prev_url"] = (
        url_for("main.index", page=pagination_meta["prev_page"])
        if pagination_meta.get("prev_page")
        else None
    )

    etag: str | None = None
    last_modified_header: str | None = None

    if tributes_payload:
        identifier = "-".join(str(item["id"]) for item in tributes_payload)
        etag = f'W/"tribute-page-{pagination_meta["page"]}-{pagination_meta["per_page"]}-{identifier}"'

    if latest_created is not None:
        last_modified_header = http_date(latest_created)

    if etag:
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match:
            tags = {candidate.strip() for candidate in if_none_match.split(",")}
            if "*" in tags or etag in tags:
                response = make_response("", 304)
                response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
                response.headers["ETag"] = etag
                if last_modified_header:
                    response.headers["Last-Modified"] = last_modified_header
                return response

    if last_modified_header:
        if_modified_since_raw = request.headers.get("If-Modified-Since")
        if if_modified_since_raw:
            since_dt = parse_date(if_modified_since_raw)
            if since_dt is not None:
                if since_dt.tzinfo is None:
                    since_dt = since_dt.replace(tzinfo=UTC)
                if latest_created is not None:
                    latest_ts = latest_created.timestamp()
                    since_ts = since_dt.timestamp()
                    if since_ts >= latest_ts:
                        response = make_response("", 304)
                        response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
                        if etag:
                            response.headers["ETag"] = etag
                        response.headers["Last-Modified"] = last_modified_header
                        return response

    payload_body = {"tributes": tributes_payload, "meta": pagination_meta}

    response = make_response(jsonify(payload_body))
    response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
    if etag:
        response.headers["ETag"] = etag
    if last_modified_header:
        response.headers["Last-Modified"] = last_modified_header
    return response


@main_bp.route("/home", methods=["GET"])
def home() -> str:
    """Render a static home page where site owners can add text and images.

    The tributes listing and submission are served from the `index` view at
    `/tributes` so the public home can be a simple static page.
    """
    return render_template("home.html")


@main_bp.route("/", methods=["GET"])
def invitation() -> str:
    contacts = current_app.config.get("INVITATION_CONTACTS") or [
        {
            "name": "Debadutta Subudhi",
            "phone_display": "+91 94377 22222",
            "phone_link": "919437722222",
        },
        {
            "name": "Sibadutta Subudhi",
            "phone_display": "+91 94371 01010",
            "phone_link": "919437101010",
        },
        {
            "name": "Bibhudutta Subudhi",
            "phone_display": "+91 9861080610",
            "phone_link": "919861080610",
        },
        {
            "name": "Pravudutta Subudhi",
            "phone_display": "+91 98611 66666",
            "phone_link": "919861166666",
        },
    ]
    return render_template("invitation.html", contacts=contacts)


@main_bp.route("/slideshow", methods=["GET"])
def slideshow() -> str:
    max_message_length_raw = current_app.config.get("SLIDESHOW_MAX_MESSAGE_LENGTH", 0)
    try:
        max_message_length = int(max_message_length_raw)
    except (TypeError, ValueError):
        max_message_length = 0
    if max_message_length < 0:
        max_message_length = 0

    return render_template(
        "slideshow.html",
        poll_seconds=current_app.config.get("SLIDESHOW_POLL_SECONDS", 60),
        dwell_ms=current_app.config.get("SLIDESHOW_DWELL_MILLISECONDS", 8000),
        transition_ms=current_app.config.get("SLIDESHOW_TRANSITION_MILLISECONDS", 800),
        submission_url=url_for("main.index", _external=True),
        max_message_length=max_message_length,
    )


@main_bp.route("/slideshow/data", methods=["GET"])
def slideshow_data():
    tributes_q = (
        Tribute.query.options(selectinload(Tribute.photos))
        .order_by(Tribute.created_at.desc())
        .all()
    )

    tributes_payload = [_serialize_slideshow_tribute(model) for model in tributes_q]
    latest = tributes_q[0].created_at if tributes_q else None
    etag: str | None = None
    last_modified_header: str | None = None

    if latest is not None:
        if latest.tzinfo is None:
            latest_utc = latest.replace(tzinfo=UTC)
        else:
            latest_utc = latest.astimezone(UTC)
        last_modified_header = http_date(latest_utc)
        etag = f'W/"tributes-{int(latest_utc.timestamp())}-{len(tributes_payload)}"'

        if_none_match = request.headers.get("If-None-Match")
        if if_none_match:
            tag_candidates = {
                candidate.strip() for candidate in if_none_match.split(",")
            }
            if "*" in tag_candidates or etag in tag_candidates:
                response = make_response("", 304)
                response.headers["ETag"] = etag
                response.headers["Last-Modified"] = last_modified_header
                response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
                return response

        if_modified_since_raw = request.headers.get("If-Modified-Since")
        if if_modified_since_raw:
            since_dt = parse_date(if_modified_since_raw)
            if since_dt is not None:
                if since_dt.tzinfo is None:
                    since_dt = since_dt.replace(tzinfo=UTC)
                latest_ts = latest_utc.timestamp()
                since_ts = since_dt.timestamp()
                if since_ts >= latest_ts:
                    response = make_response("", 304)
                    response.headers["ETag"] = etag
                    response.headers["Last-Modified"] = last_modified_header
                    response.headers["Cache-Control"] = (
                        "public, max-age=0, must-revalidate"
                    )
                    return response

    payload = {
        "tributes": tributes_payload,
        "meta": {
            "count": len(tributes_payload),
            "generated_at": http_date(),
            "poll_seconds": current_app.config.get("SLIDESHOW_POLL_SECONDS", 60),
        },
    }

    response = make_response(jsonify(payload))
    response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
    if etag:
        response.headers["ETag"] = etag
    if last_modified_header:
        response.headers["Last-Modified"] = last_modified_header
    return response


@main_bp.route("/tributes/<int:tribute_id>")
def tribute_detail(tribute_id: int) -> str:
    tribute = db.session.get(Tribute, tribute_id)
    if not tribute:
        from werkzeug.exceptions import NotFound

        raise NotFound()
    tribute = (
        Tribute.query.options(selectinload(Tribute.photos))
        .filter_by(id=tribute_id)
        .first_or_404()
    )
    tribute_payload = _serialize_tribute(tribute)
    tribute_namespace = _namespace_tribute(tribute_payload)
    return render_template("tribute_detail.html", tribute=tribute_namespace)


@main_bp.route("/admin/delete/tribute/<int:tribute_id>", methods=["GET", "POST"])
def admin_delete_tribute(tribute_id: int) -> str:
    """Admin-only endpoint to delete a tribute with authentication."""
    tribute = db.session.get(Tribute, tribute_id)
    if not tribute:
        from werkzeug.exceptions import NotFound

        raise NotFound()
    form = AdminAuthForm()

    if form.validate_on_submit():
        admin_username = current_app.config.get("ADMIN_USERNAME")
        admin_password = current_app.config.get("ADMIN_PASSWORD")

        if not admin_username or not admin_password:
            current_app.logger.error("Admin credentials not configured in environment")
            flash("Admin authentication is not configured.", "danger")
            return render_template("admin_delete.html", tribute=tribute, form=form)

        if (
            form.username.data == admin_username
            and form.password.data == admin_password
        ):
            tribute_name = tribute.name

            try:
                # Delete associated photos first (cascade should handle this, but being explicit)
                for photo in tribute.photos:
                    if photo.photo_s3_key:
                        try:
                            s3.delete_object(photo.photo_s3_key)
                        except s3.S3Error:  # pragma: no cover - defensive logging
                            current_app.logger.warning(
                                "Failed to delete S3 object for photo %s",
                                photo.id,
                                exc_info=True,
                            )
                    db.session.delete(photo)
                db.session.delete(tribute)
                db.session.commit()
                current_app.logger.info(
                    "Admin deleted tribute %s (%s)", tribute_id, tribute_name
                )
                _invalidate_carousel_cache()
                _invalidate_tributes_cache()
                flash(f"Tribute from {tribute_name} has been deleted.", "success")
                return redirect(url_for("main.index"))
            except Exception:  # pragma: no cover
                db.session.rollback()
                current_app.logger.exception("Failed to delete tribute %s", tribute_id)
                flash("Failed to delete tribute. Please try again.", "danger")
                return render_template("admin_delete.html", tribute=tribute, form=form)
        else:
            flash("Invalid username or password.", "danger")
            return render_template("admin_delete.html", tribute=tribute, form=form)

    # GET request or validation failed - show authentication form
    return render_template("admin_delete.html", tribute=tribute, form=form)


def _collect_carousel_images(*, limit: int = 8) -> list[dict[str, str]]:
    """Return up to ``limit`` unique tribute photo payloads for the carousel."""
    if limit <= 0:
        return []

    cache_ttl = _resolve_cache_ttl("CAROUSEL_CACHE_SECONDS", 300)
    cache_key = limit
    now = monotonic()

    if cache_ttl and cache_ttl > 0:
        cached = _CAROUSEL_CACHE.get(cache_key)
        if cached:
            cached_at, cached_items = cached
            if now - cached_at < cache_ttl:
                hydrated = [_hydrate_carousel_item(item) for item in cached_items]
                return [item for item in hydrated if item]

    oversample = max(limit * 3, limit)
    photos = (
        TributePhoto.query.filter(
            or_(
                TributePhoto.photo_s3_key.isnot(None),
                TributePhoto.photo_url.isnot(None),
                TributePhoto.photo_b64.isnot(None),
            )
        )
        .order_by(func.random())
        .limit(oversample)
        .all()
    )

    carousel_items: list[dict[str, str]] = []
    seen_payloads: set[str] = set()
    cached_descriptors: list[dict[str, Any]] = []

    for photo in photos:
        identifier = (
            (photo.photo_s3_key or "")
            or (photo.photo_url or "")
            or (photo.photo_b64 or "")
        )
        if not identifier or identifier in seen_payloads:
            continue
        seen_payloads.add(identifier)

        descriptor = {
            "id": photo.id,
            "photo_s3_key": photo.photo_s3_key,
            "photo_b64": photo.photo_b64,
            "photo_content_type": photo.photo_content_type,
            "caption": photo.caption,
            "photo_url": photo.photo_url,
        }

        hydrated = _hydrate_carousel_item(descriptor)
        if not hydrated:
            continue

        carousel_items.append(hydrated)
        cached_descriptors.append(descriptor)

        if len(carousel_items) >= limit:
            break

    if cache_ttl and cache_ttl > 0:
        _CAROUSEL_CACHE[cache_key] = (now, cached_descriptors)

    return carousel_items


def _invalidate_carousel_cache() -> None:
    _CAROUSEL_CACHE.clear()


def _get_cached_tributes(
    *, page: int, per_page: int, max_per_page: int | None = None
) -> dict[str, Any]:
    cache_ttl = _resolve_cache_ttl("TRIBUTES_CACHE_SECONDS", 300)
    now = monotonic()

    sanitized_page = page if page > 0 else 1
    sanitized_per_page = per_page if per_page > 0 else 1

    if max_per_page is not None and max_per_page > 0:
        sanitized_per_page = min(sanitized_per_page, max_per_page)

    cache_key = (sanitized_page, sanitized_per_page)

    if cache_ttl and cache_ttl > 0 and sanitized_page == 1:
        cached = _TRIBUTES_CACHE.get(cache_key)
        if cached:
            cached_at, cached_payload = cached
            if now - cached_at < cache_ttl:
                return cached_payload

    result = tributes.paginate_tributes(
        page=sanitized_page,
        per_page=sanitized_per_page,
        max_per_page=max_per_page,
    )
    tributes_serialized = [_serialize_tribute(model) for model in result.items]

    payload = {
        "items": tributes_serialized,
        "meta": {
            "page": result.page,
            "per_page": result.per_page,
            "has_next": result.has_next,
            "has_prev": result.has_prev,
            "next_page": result.next_page,
            "prev_page": result.prev_page,
        },
    }

    if cache_ttl and cache_ttl > 0 and result.page == 1:
        _TRIBUTES_CACHE[(result.page, result.per_page)] = (now, payload)

    return payload


def _invalidate_tributes_cache() -> None:
    _TRIBUTES_CACHE.clear()


def _serialize_tribute(model: Tribute) -> dict[str, Any]:
    return {
        "id": model.id,
        "name": model.name,
        "message": model.message,
        "created_at": model.created_at,
        "extra_fields": model.extra_fields or {},
        "photos": [
            {
                "id": photo.id,
                "photo_b64": photo.photo_b64,
                "photo_content_type": photo.photo_content_type,
                "caption": photo.caption,
                "photo_url": photo.photo_url,
                "photo_s3_key": photo.photo_s3_key,
            }
            for photo in model.photos or []
        ],
    }


def _namespace_tribute(payload: dict[str, Any]) -> SimpleNamespace:
    photos_payload = payload.get("photos", [])
    photos: list[SimpleNamespace] = []
    for photo in photos_payload:
        resolved_url = _resolve_photo_src(photo)
        photos.append(
            SimpleNamespace(
                id=photo.get("id"),
                photo_b64=photo.get("photo_b64"),
                photo_content_type=photo.get("photo_content_type"),
                caption=photo.get("caption"),
                photo_s3_key=photo.get("photo_s3_key"),
                photo_url=resolved_url,
            )
        )
    return SimpleNamespace(
        id=payload["id"],
        name=payload["name"],
        message=payload["message"],
        created_at=payload["created_at"],
        photos=photos,
        extra_fields=payload.get("extra_fields") or {},
    )


def _tribute_namespace_to_dict(
    tribute: SimpleNamespace,
) -> tuple[dict[str, Any], datetime | None]:
    created_at_value = getattr(tribute, "created_at", None)
    created_dt: datetime | None = None
    created_serialized: str | None = None

    if isinstance(created_at_value, datetime):
        if created_at_value.tzinfo is None:
            created_dt = created_at_value.replace(tzinfo=UTC)
        else:
            created_dt = created_at_value.astimezone(UTC)
        created_serialized = created_dt.isoformat()
    elif created_at_value is not None:
        created_serialized = str(created_at_value)

    photos_payload: list[dict[str, Any]] = []
    for photo in getattr(tribute, "photos", []):
        photos_payload.append(
            {
                "id": getattr(photo, "id", None),
                "caption": getattr(photo, "caption", None),
                "photo_url": getattr(photo, "photo_url", None),
                "photo_b64": getattr(photo, "photo_b64", None),
                "photo_content_type": getattr(photo, "photo_content_type", None),
                "photo_s3_key": getattr(photo, "photo_s3_key", None),
            }
        )

    tribute_id = getattr(tribute, "id", None)
    payload = {
        "id": tribute_id,
        "name": getattr(tribute, "name", None),
        "message": getattr(tribute, "message", None),
        "created_at": created_serialized,
        "detail_url": (
            url_for("main.tribute_detail", tribute_id=tribute_id)
            if tribute_id is not None
            else None
        ),
        "photos": photos_payload,
    }

    return payload, created_dt


def _serialize_slideshow_tribute(model: Tribute) -> dict[str, Any]:
    photos: list[dict[str, Any]] = []
    for photo in model.photos or []:
        src = _resolve_photo_src(photo)
        if not src:
            continue
        photos.append(
            {
                "id": photo.id,
                "url": src,
                "caption": photo.caption,
                "content_type": photo.photo_content_type,
            }
        )

    created_at = model.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    else:
        created_at = created_at.astimezone(UTC)
    return {
        "id": model.id,
        "name": model.name,
        "message": model.message,
        "created_at": created_at.isoformat(),
        "photos": photos,
        "text_only": len(photos) == 0,
    }


def _hydrate_carousel_item(payload: Mapping[str, Any]) -> dict[str, str] | None:
    src = _resolve_photo_src(payload)
    if not src:
        return None
    identifier = payload.get("id")
    alt_fallback = f"Tribute photo {identifier}" if identifier else "Tribute photo"
    alt = payload.get("caption") or alt_fallback
    return {"src": src, "alt": alt}


def _resolve_photo_src(photo: Mapping[str, Any] | Any) -> str | None:
    def _peek(attr: str) -> Any:
        if isinstance(photo, Mapping):
            return photo.get(attr)
        return getattr(photo, attr, None)

    key = _peek("photo_s3_key")
    if key:
        try:
            return s3.generate_presigned_get_url(key)
        except (s3.S3Error, ValueError):
            current_app.logger.warning(
                "Failed to generate presigned URL for key %s", key, exc_info=True
            )

    stored_url = _peek("photo_url")
    if stored_url:
        return stored_url

    payload = _peek("photo_b64")
    if payload:
        content_type = _peek("photo_content_type") or "image/webp"
        return f"data:{content_type};base64,{payload}"

    return None
