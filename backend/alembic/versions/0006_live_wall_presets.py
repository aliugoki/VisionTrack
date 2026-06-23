"""Create wall_presets table.

Revision ID: 0006_live_wall_presets
Revises: 0005_tracks
Create Date: 2026-06-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "0006_live_wall_presets"
down_revision: Union[str, None] = "0005_tracks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wall_presets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("rows", sa.Integer, nullable=False),
        sa.Column("cols", sa.Integer, nullable=False),
        sa.Column("tiles", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "is_default", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "tenant_id", "name", name="uq_wall_presets_tenant_name"
        ),
    )
    op.create_index("ix_wall_presets_tenant_id", "wall_presets", ["tenant_id"])
    op.create_index(
        "ix_wall_presets_tenant_default",
        "wall_presets",
        ["tenant_id", "is_default"],
    )


def downgrade() -> None:
    op.drop_index("ix_wall_presets_tenant_default", table_name="wall_presets")
    op.drop_index("ix_wall_presets_tenant_id", table_name="wall_presets")
    op.drop_table("wall_presets")
