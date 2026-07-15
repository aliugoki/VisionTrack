"""tenants.external_company_id — company↔tenant link (multi-tenant Phase 1)

Revision ID: 0020_tenant_external_company
Revises: 0019_companies
Create Date: 2026-07-15

Adds `tenants.external_company_id` (FaceTrack company_id), the canonical 1:1 link
between a FaceTrack company and its dedicated VisionTrack tenant. Nullable (the
demo/native tenants have none); unique so a company maps to at most one tenant.

Rollback: downgrade() drops the constraint + column.
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_tenant_external_company"
down_revision = "0019_companies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("external_company_id", sa.String(length=255), nullable=True))
    op.create_unique_constraint(
        "uq_tenant_external_company", "tenants", ["external_company_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_tenant_external_company", "tenants", type_="unique")
    op.drop_column("tenants", "external_company_id")
