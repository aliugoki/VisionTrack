"""Face identity overlay — person_identities

Revision ID: 0017_face_identities
Revises: 0016_global_tracks
Create Date: 2026-06-23

Background
----------
A separate face-recognition pipeline publishes recognized identities to the
Redis stream `vt:face:identities:<tenant_id>`. The face-identity consumer
(app.modules.persons.face_identity_consumer) correlates each event to an active
track by camera + bbox IoU + time, then labels the matched Person.

This adds `person_identities` — an OVERLAY linking an external employee id /
name to a Person. It is intentionally separate from the ReID tables: a face
label never feeds the cross-camera matcher, so a mislabel cannot corrupt
appearance clustering.

`person_id` is nullable because an event may correlate to a track the matcher
has not yet assigned to a Person; such rows are reconciled later.

Rollback path
-------------
downgrade() drops person_identities and its indexes. No other data is touched.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017_face_identities"
down_revision = "0016_global_tracks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "camera_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cameras.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("emp_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="face", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("votes", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "first_labeled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_labeled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "person_id", "emp_id", name="uq_person_identity"
        ),
    )
    op.create_index(
        "ix_person_identities_tenant", "person_identities", ["tenant_id"]
    )
    op.create_index(
        "ix_person_identities_person", "person_identities", ["person_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_person_identities_person", table_name="person_identities")
    op.drop_index("ix_person_identities_tenant", table_name="person_identities")
    op.drop_table("person_identities")
