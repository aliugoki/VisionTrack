"""Employees roster (sourced from FaceTrack)

Revision ID: 0018_employees
Revises: 0017_face_identities
Create Date: 2026-07-15

Adds `employees` — the employee roster imported from the FaceTrack face-
recognition system (its `user_data` table) by
`scripts/sync_facetrack_employees.py`. `emp_id` is the shared key the face-
identity bridge stamps onto `person_identities`, linking an employee to their
tracked identity. Unique per (tenant, emp_id).

Rollback: downgrade() drops the table.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018_employees"
down_revision = "0017_face_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("emp_id", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("external_company_id", sa.String(length=255), nullable=True),
        sa.Column("image_path", sa.String(length=1024), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="facetrack", nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "emp_id", name="uq_employee_tenant_emp"),
    )
    op.create_index("ix_employees_tenant_id", "employees", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_employees_tenant_id", table_name="employees")
    op.drop_table("employees")
