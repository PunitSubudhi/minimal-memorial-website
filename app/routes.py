"""HTTP routes for the memorial application."""
from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from .extensions import db
from .forms import TributeForm
from .models import Tribute, TributePhoto
from .services import notifications, storage, tributes

main_bp = Blueprint("main", __name__)


@main_bp.route("/", methods=["GET", "POST"])
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


@main_bp.route("/tributes/<int:tribute_id>")
def tribute_detail(tribute_id: int) -> str:
    tribute = Tribute.query.options(selectinload(Tribute.photos)).get_or_404(tribute_id)
    return render_template("tribute_detail.html", tribute=tribute)


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
