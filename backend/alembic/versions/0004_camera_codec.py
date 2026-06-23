"""Add cameras.codec column.

Stores the detected video codec (H264, H265) as observed by the
health-check task. NULL until first probe.

Revision ID: 0004_camera_codec
Revises: 0003_rename_sites_metadata
Create Date: 2026-06-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_camera_codec"
down_revision: Union[str, None] = "0003_rename_sites_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column("codec", sa.String(20), nullable=True),
    )
    op.create_index("ix_cameras_codec", "cameras", ["codec"])


def downgrade() -> None:
    op.drop_index("ix_cameras_codec", table_name="cameras")
    op.drop_column("cameras", "codec")
