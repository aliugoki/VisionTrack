"""MV3DT Phase A — global (cross-camera) tracks

Revision ID: 0016_global_tracks
Revises: 0015_matcher
Create Date: 2026-06-10

Background
----------
Adds the cross-camera *spatial* fusion layer (MV3DT Phase A — see
docs/MV3DT.md). The matcher (P2.5) already gives appearance identity
(`persons`); this adds a global trajectory layer that stitches per-camera
`tracks` into one site-wide journey using BEV world positions + time.

  - global_tracks        one contiguous cross-camera journey of a person
  - tracks.global_track_id  links each per-camera fragment to its journey
  - global_track_points  fused world-frame positions along the journey
                         (plain table; this deployment has no TimescaleDB)

`track_points.world_x/world_y` (populated at ingest from camera homographies)
are the spatial input. `global_tracks.person_id` links to the appearance
identity when known.

Rollback path
-------------
downgrade() drops global_track_points, tracks.global_track_id (+index), and
global_tracks. No data outside these is touched.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0016_global_tracks"
down_revision = "0015_matcher"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "global_tracks",
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
            sa.ForeignKey("persons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "floor_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("floor_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_global_tracks_tenant_time", "global_tracks", ["tenant_id", "started_at"]
    )

    op.add_column(
        "tracks",
        sa.Column(
            "global_track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("global_tracks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_tracks_global", "tracks", ["global_track_id"])

    op.create_table(
        "global_track_points",
        sa.Column("ts", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column(
            "global_track_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Floor-plan fractional coords (0..1), fused across contributing cameras.
        sa.Column("world_x", sa.Float(), nullable=False),
        sa.Column("world_y", sa.Float(), nullable=False),
        sa.Column("contributing_camera_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_global_track_points_track", "global_track_points", ["global_track_id"]
    )
    op.create_index(
        "ix_global_track_points_tenant_ts", "global_track_points", ["tenant_id", "ts"]
    )


def downgrade() -> None:
    op.drop_index("ix_global_track_points_tenant_ts", table_name="global_track_points")
    op.drop_index("ix_global_track_points_track", table_name="global_track_points")
    op.drop_table("global_track_points")
    op.drop_index("ix_tracks_global", table_name="tracks")
    op.drop_column("tracks", "global_track_id")
    op.drop_index("ix_global_tracks_tenant_time", table_name="global_tracks")
    op.drop_table("global_tracks")
