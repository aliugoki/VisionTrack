"""recordings table for Step 6 — playback feature

Revision ID: 0011_recordings
Revises: 0010_tenant_timezone_alerts
Create Date: 2026-06-06 11:15:00

Schema notes:
  The recordings table indexes MediaMTX-written MP4 segments. MediaMTX
  is the source of truth for the *files*; this table is the source of
  truth for *metadata + access*.

  One row per recorded segment. MediaMTX segment duration defaults to
  1 hour, so for 2 cameras streaming 24/7 we get 48 rows/day = ~17k/year.
  Comfortably small. Indexes are conservative.

  storage_path is the in-container path (`/recordings/cam-XXX/2026-06-06_10-01-04.mp4`)
  since MediaMTX writes to the local volume. For a future MinIO migration
  this becomes a MinIO object key — the column is wide enough either way.

  source_event_id is nullable. Most segments are background recording
  (no associated event). When the alert evaluator fires, we can populate
  the nearest segment with the alert id, making clip lookup O(1) by
  alert_id — but that's a 6C optimization. For now, lookup is by
  (camera_id, fired_at BETWEEN started_at AND ended_at).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_recordings"
down_revision = "0010_tenant_timezone_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("codec", sa.String(20), nullable=True),
        sa.Column("width_px", sa.Integer, nullable=True),
        sa.Column("height_px", sa.Integer, nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("source_alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_alert_id"], ["alerts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("storage_path", name="uq_recordings_storage_path"),
    )

    # Indexes for the two main query patterns:
    # 1. List recent recordings for a camera: (tenant_id, camera_id, started_at DESC)
    # 2. Find segment covering a timestamp: (camera_id, started_at, ended_at)
    op.create_index(
        "ix_recordings_tenant_camera_started",
        "recordings",
        ["tenant_id", "camera_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_recordings_camera_time_range",
        "recordings",
        ["camera_id", "started_at", "ended_at"],
    )
    # 3. Tenant-wide newest-first feed
    op.create_index(
        "ix_recordings_tenant_started",
        "recordings",
        ["tenant_id", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_recordings_tenant_started", table_name="recordings")
    op.drop_index("ix_recordings_camera_time_range", table_name="recordings")
    op.drop_index("ix_recordings_tenant_camera_started", table_name="recordings")
    op.drop_table("recordings")
