"""Add markers JSONB column to floor_plans.

Revision ID: 0008_floor_plan_markers
Revises: 0007_floor_plans
Create Date: 2026-06-03

Phase 1 stores camera placements as a JSONB array on the floor plan
itself. A separate `floor_plan_markers` table is reserved for Phase 3
when calibration matrices and per-marker permissions become relevant.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0008_floor_plan_markers"
down_revision: Union[str, None] = "0007_floor_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "floor_plans",
        sa.Column(
            "markers",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("floor_plans", "markers")
