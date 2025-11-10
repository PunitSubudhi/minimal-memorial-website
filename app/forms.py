"""WTForms definitions for the memorial application."""

from __future__ import annotations

from flask import current_app
from flask_wtf import FlaskForm
from werkzeug.datastructures import FileStorage
from wtforms import MultipleFileField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, ValidationError


class TributeForm(FlaskForm):
    name = StringField(
        "Your Name",
        validators=[DataRequired(), Length(max=120)],
        render_kw={"placeholder": "Enter your name"},
    )
    message = TextAreaField(
        "Tribute Message",
        validators=[DataRequired(), Length(max=2000)],
        render_kw={
            "rows": 5,
            "placeholder": "Share a favorite memory, message of support, or story.",
        },
    )
    photos = MultipleFileField("Upload Photos (optional)")
    submit = SubmitField("Share Tribute")

    def validate_photos(self, field: MultipleFileField) -> None:
        allowed = set(current_app.config.get("ALLOWED_EXTENSIONS", ()))
        for storage in field.data or []:
            if not isinstance(storage, FileStorage):
                continue
            filename = storage.filename or ""
            if not filename:
                continue
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if allowed and ext not in allowed:
                raise ValidationError("One or more files have an unsupported format.")
