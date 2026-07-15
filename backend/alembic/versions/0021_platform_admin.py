"""users.is_platform_admin — platform super-admin (multi-tenant Phase 2)

Revision ID: 0021_platform_admin
Revises: 0020_tenant_external_company
Create Date: 2026-07-15

A platform admin can list all tenants and "enter" any of them (mint an
impersonation token scoped to that tenant). Existing superusers are promoted to
platform admins so the current admin keeps working.

Rollback: downgrade() drops the column.
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_platform_admin"
down_revision = "0020_tenant_external_company"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_platform_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # Promote existing superusers (e.g. the seeded admin) to platform admins.
    op.execute("UPDATE users SET is_platform_admin = true WHERE is_superuser = true")


def downgrade() -> None:
    op.drop_column("users", "is_platform_admin")
