"""Database models for the memorial application."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .extensions import db


class Tribute(db.Model):
    __tablename__ = "tributes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    extra_fields = db.Column(db.JSON, default=dict, nullable=False)

    photos = db.relationship(
        "TributePhoto",
        back_populates="tribute",
        cascade="all, delete-orphan",
        order_by="TributePhoto.display_order",
        lazy="selectin",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "extra_fields": self.extra_fields,
            "photos": [photo.to_dict() for photo in self.photos],
        }


class TributePhoto(db.Model):
    __tablename__ = "tribute_photos"

    id = db.Column(db.Integer, primary_key=True)
    tribute_id = db.Column(
        db.Integer,
        db.ForeignKey("tributes.id", ondelete="CASCADE"),
        nullable=False,
    )
    photo_b64 = db.Column(db.Text, nullable=True)
    photo_content_type = db.Column(db.String(64), nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    caption = db.Column(db.String(255))
    photo_s3_key = db.Column(db.String(512))
    photo_url = db.Column(db.Text)
    migrated_at = db.Column(db.DateTime(timezone=True))

    tribute = db.relationship("Tribute", back_populates="photos")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "photo_content_type": self.photo_content_type,
            "display_order": self.display_order,
            "caption": self.caption,
            "photo_url": self.photo_url,
            "photo_s3_key": self.photo_s3_key,
            "photo_b64": self.photo_b64,
        }
