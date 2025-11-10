"""HTTP routes for the memorial application."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    url_for,
)
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from .extensions import db
from .forms import AdminAuthForm, TributeForm
from .models import Tribute, TributePhoto
from .services import notifications, storage, tributes

main_bp = Blueprint("main", __name__)


@main_bp.route("/tributes", methods=["GET", "POST"])
def index() -> str:
    form = TributeForm()
    page_size = current_app.config.get("TRIBUTES_PAGE_SIZE", 12)

    if form.validate_on_submit():
        entries = storage.prepare_photo_entries(
            form.photos.data or [],
            logger=current_app.logger,
            max_bytes=current_app.config.get("MAX_PHOTO_UPLOAD_BYTES"),
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
            flash("Thank you for sharing your tribute.", "success")
            return redirect(url_for("main.index"))

    tributes_q = (
        Tribute.query.options(selectinload(Tribute.photos))
        .order_by(Tribute.created_at.desc())
        .limit(page_size)
    )
    carousel_images = _collect_carousel_images(limit=8)
    return render_template(
        "index.html",
        form=form,
        tributes=list(tributes_q),
        carousel_images=carousel_images,
    )


@main_bp.route("/", methods=["GET"])
def home() -> str:
    """Render a static home page where site owners can add text and images.

    The tributes listing and submission are served from the `index` view at
    `/tributes` so the public home can be a simple static page.
    """
    return render_template("home.html")


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
                    db.session.delete(photo)
                db.session.delete(tribute)
                db.session.commit()
                current_app.logger.info(
                    "Admin deleted tribute %s (%s)", tribute_id, tribute_name
                )
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

    oversample = max(limit * 3, limit)
    photos = (
        TributePhoto.query.filter(TributePhoto.photo_b64.isnot(None))
        .order_by(func.random())
        .limit(oversample)
        .all()
    )

    carousel_items: list[dict[str, str]] = []
    seen_payloads: set[str] = set()

    for photo in photos:
        payload = photo.photo_b64 or ""
        if not payload or payload in seen_payloads:
            continue
        seen_payloads.add(payload)

        src = f"data:{photo.photo_content_type};base64,{payload}"
        alt = photo.caption or f"Tribute photo {photo.id}"
        carousel_items.append({"src": src, "alt": alt})

        if len(carousel_items) >= limit:
            break

    return carousel_items
