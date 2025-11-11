"""HTTP routes for the memorial application."""

from __future__ import annotations

from time import monotonic
from types import SimpleNamespace
from typing import Any

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    url_for,
)
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from .extensions import db
from .forms import AdminAuthForm, TributeForm
from .models import Tribute, TributePhoto
from .services import notifications, s3, storage, tributes

main_bp = Blueprint("main", __name__)


_CAROUSEL_CACHE: dict[int, tuple[float, list[dict[str, str]]]] = {}
_TRIBUTES_CACHE: dict[int, tuple[float, list[dict[str, Any]]]] = {}


@main_bp.route("/tributes", methods=["GET", "POST"])
def index() -> str:
    form = TributeForm()
    page_size = current_app.config.get("TRIBUTES_PAGE_SIZE", 12)

    if form.validate_on_submit():
        entries, had_size_error = storage.prepare_photo_entries(
            form.photos.data or [],
            logger=current_app.logger,
            max_bytes=current_app.config.get("MAX_PHOTO_UPLOAD_BYTES"),
        )
        if had_size_error:
            flash(
                "Some photos were too large and were skipped. Smaller files work best.",
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

    carousel_images = _collect_carousel_images(limit=8)
    return render_template(
        "index.html",
        form=form,
        tributes=_get_cached_tributes(limit=page_size),
        carousel_images=carousel_images,
    )


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
    return render_template("tribute_detail.html", tribute=tribute)


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

    cache_ttl = current_app.config.get("CAROUSEL_CACHE_SECONDS", 300)
    cache_key = limit
    now = monotonic()

    if cache_ttl and cache_ttl > 0:
        cached = _CAROUSEL_CACHE.get(cache_key)
        if cached:
            cached_at, cached_items = cached
            if now - cached_at < cache_ttl:
                return list(cached_items)

    oversample = max(limit * 3, limit)
    photos = (
        TributePhoto.query.filter(
            or_(
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

    for photo in photos:
        identifier = (
            (photo.photo_s3_key or "")
            or (photo.photo_url or "")
            or (photo.photo_b64 or "")
        )
        if not identifier or identifier in seen_payloads:
            continue
        seen_payloads.add(identifier)

        if photo.photo_url:
            src = photo.photo_url
        else:
            payload = photo.photo_b64 or ""
            if not payload:
                continue
            src = f"data:{photo.photo_content_type};base64,{payload}"
        alt = photo.caption or f"Tribute photo {photo.id}"
        carousel_items.append({"src": src, "alt": alt})

        if len(carousel_items) >= limit:
            break

    if cache_ttl and cache_ttl > 0:
        _CAROUSEL_CACHE[cache_key] = (now, list(carousel_items))

    return carousel_items


def _invalidate_carousel_cache() -> None:
    _CAROUSEL_CACHE.clear()


def _get_cached_tributes(*, limit: int) -> list[SimpleNamespace]:
    if limit <= 0:
        return []

    cache_ttl = current_app.config.get("TRIBUTES_CACHE_SECONDS", 300)
    now = monotonic()
    cache_key = limit

    if cache_ttl and cache_ttl > 0:
        cached = _TRIBUTES_CACHE.get(cache_key)
        if cached:
            cached_at, cached_items = cached
            if now - cached_at < cache_ttl:
                return [_namespace_tribute(item) for item in cached_items]

    tributes_q = (
        Tribute.query.options(selectinload(Tribute.photos))
        .order_by(Tribute.created_at.desc())
        .limit(limit)
    )
    tributes_serialized = [_serialize_tribute(model) for model in tributes_q]

    if cache_ttl and cache_ttl > 0:
        # store serialized payload only so SQLAlchemy objects are not cached directly
        _TRIBUTES_CACHE[cache_key] = (now, tributes_serialized)

    return [_namespace_tribute(item) for item in tributes_serialized]


def _invalidate_tributes_cache() -> None:
    _TRIBUTES_CACHE.clear()


def _serialize_tribute(model: Tribute) -> dict[str, Any]:
    return {
        "id": model.id,
        "name": model.name,
        "message": model.message,
        "created_at": model.created_at,
        "photos": [
            {
                "id": photo.id,
                "photo_b64": photo.photo_b64,
                "photo_content_type": photo.photo_content_type,
                "caption": photo.caption,
                "photo_url": photo.photo_url,
            }
            for photo in model.photos or []
        ],
    }


def _namespace_tribute(payload: dict[str, Any]) -> SimpleNamespace:
    photos = [SimpleNamespace(**photo) for photo in payload.get("photos", [])]
    return SimpleNamespace(
        id=payload["id"],
        name=payload["name"],
        message=payload["message"],
        created_at=payload["created_at"],
        photos=photos,
    )
