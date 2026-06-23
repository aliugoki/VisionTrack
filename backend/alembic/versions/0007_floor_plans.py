"""Create floor_plans table.

Revision ID: 0007_floor_plans
Revises: 0006_live_wall_presets
Create Date: 2026-06-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "0007_floor_plans"
down_revision: Union[str, None] = "0006_live_wall_presets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "floor_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("original_content_type", sa.String(100), nullable=False),
        sa.Column("original_size_bytes", sa.Integer, nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("width_px", sa.Integer, nullable=False),
        sa.Column("height_px", sa.Integer, nullable=False),
        sa.Column("storage_key_original", sa.String(500), nullable=False),
        sa.Column("storage_key_rendered", sa.String(500), nullable=True),
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
    )
    op.create_index("ix_floor_plans_tenant_id", "floor_plans", ["tenant_id"])
    op.create_index(
        "ix_floor_plans_tenant_site",
        "floor_plans",
        ["tenant_id", "site_id"],
    )
    op.create_index(
        "ix_floor_plans_tenant_name",
        "floor_plans",
        ["tenant_id", "name"],
    )


def downgrade() -> None:
    op.drop_index("ix_floor_plans_tenant_name", table_name="floor_plans")
    op.drop_index("ix_floor_plans_tenant_site", table_name="floor_plans")
    op.drop_index("ix_floor_plans_tenant_id", table_name="floor_plans")
    op.drop_table("floor_plans")
