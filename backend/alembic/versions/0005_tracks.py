"""Create tracks + track_points (TimescaleDB hypertable) with retention.

Revision ID: 0005_tracks
Revises: 0004_camera_codec
Create Date: 2026-06-02

The track_points table is converted to a TimescaleDB hypertable with
1-day chunks, and a 30-day retention policy is installed.

Note: this migration requires the timescaledb extension which was
installed by 0001_initial.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "0005_tracks"
down_revision: Union[str, None] = "0004_camera_codec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----- tracks ------------------------------------------------------------
    op.create_table(
        "tracks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "camera_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cameras.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tracker_id", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_bbox", JSONB, nullable=False, server_default="{}"),
        sa.Column("last_bbox", JSONB, nullable=False, server_default="{}"),
        sa.Column("point_count", sa.Integer, nullable=False, server_default="0"),
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
    op.create_index("ix_tracks_tenant_id", "tracks", ["tenant_id"])
    op.create_index("ix_tracks_camera_started", "tracks", ["camera_id", "started_at"])
    op.create_index("ix_tracks_tenant_active", "tracks", ["tenant_id", "ended_at"])

    # ----- track_points (hypertable) -----------------------------------------
    # No surrogate id — composite PK is (ts, track_id) so chunk pruning works.
    # No FK to tracks because TimescaleDB hypertables can't have inbound or
    # outbound FKs and stay performant.
    op.execute(
        """
        CREATE TABLE track_points (
            ts          timestamptz   NOT NULL,
            track_id    uuid          NOT NULL,
            tenant_id   uuid          NOT NULL,
            camera_id   uuid          NOT NULL,
            tracker_id  integer       NOT NULL,
            bbox_x1     double precision NOT NULL,
            bbox_y1     double precision NOT NULL,
            bbox_x2     double precision NOT NULL,
            bbox_y2     double precision NOT NULL,
            confidence  double precision NOT NULL,
            world_x     double precision,
            world_y     double precision,
            PRIMARY KEY (ts, track_id)
        );
        """
    )

    # Convert into a hypertable with 1-day chunks
    op.execute(
        """
        SELECT create_hypertable(
            'track_points',
            'ts',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
        """
    )

    # Indexes — hypertable indexes are auto-created per chunk by TimescaleDB
    op.execute("CREATE INDEX ix_track_points_camera_ts ON track_points (camera_id, ts DESC);")
    op.execute("CREATE INDEX ix_track_points_track_ts ON track_points (track_id, ts DESC);")
    op.execute("CREATE INDEX ix_track_points_tenant_ts ON track_points (tenant_id, ts DESC);")

    # Retention policy — drop chunks older than 30 days. Runs in the
    # database, no Python or Celery involvement. The job runs once a day
    # by default; can be changed with add_job_schedule_interval.
    op.execute(
        """
        SELECT add_retention_policy(
            'track_points',
            INTERVAL '30 days',
            if_not_exists => TRUE
        );
        """
    )


def downgrade() -> None:
    # Remove retention policy first (it has a FK-ish dependency on the table)
    op.execute("SELECT remove_retention_policy('track_points', if_exists => TRUE);")
    op.execute("DROP TABLE IF EXISTS track_points CASCADE;")
    op.drop_table("tracks")
