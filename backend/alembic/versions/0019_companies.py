"""Companies (reflected from FaceTrack + VisionTrack-native)

Revision ID: 0019_companies
Revises: 0018_employees
Create Date: 2026-07-15

Adds `companies` — mirrors FaceTrack companies (source='facetrack', external_id =
FaceTrack company_id), and allows VisionTrack-native companies (source=
'visiontrack', external_id NULL). Employees link via external_company_id.

Rollback: downgrade() drops the table.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0019_companies"
down_revision = "0018_employees"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("admin_username", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="facetrack", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "external_id", name="uq_company_tenant_external"),
    )
    op.create_index("ix_companies_tenant_id", "companies", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_companies_tenant_id", table_name="companies")
    op.drop_table("companies")
