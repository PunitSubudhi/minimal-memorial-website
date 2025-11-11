"""add s3 metadata columns to tribute photos"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f4f1e07911dc"
down_revision = "07075a1ea27e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tribute_photos",
        sa.Column("photo_s3_key", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "tribute_photos",
        sa.Column("photo_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "tribute_photos",
        sa.Column("migrated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column(
        "tribute_photos",
        "photo_b64",
        existing_type=sa.Text(),
        existing_nullable=False,
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tribute_photos",
        "photo_b64",
        existing_type=sa.Text(),
        existing_nullable=True,
        nullable=False,
    )
    op.drop_column("tribute_photos", "migrated_at")
    op.drop_column("tribute_photos", "photo_url")
    op.drop_column("tribute_photos", "photo_s3_key")
