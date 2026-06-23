"""Add zones JSONB column to floor_plans

Revision ID: 0009_floor_plan_zones
Revises: 0008_floor_plan_markers
Create Date: 2026-06-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009_floor_plan_zones"
down_revision: Union[str, None] = "0008_floor_plan_markers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # zones is a JSONB array — each element is a dict containing name,
    # color, polygon points, and rules. Default empty list so existing
    # floor plans pick up the column without manual seeding.
    op.add_column(
        "floor_plans",
        sa.Column(
            "zones",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("floor_plans", "zones")
