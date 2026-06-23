"""P2.5 matcher — person_embeddings.tracker_id + persons.embedding_weight_sum

Revision ID: 0015_matcher
Revises: 0014_embedding_person_nullable
Create Date: 2026-06-09

Background
----------
The cross-camera matcher (P2.5) needs two things the schema doesn't yet
provide:

  1. A way to link an embedding back to the per-camera Track it came from.
     The DeepStream worker only knows the ByteTrack/NvDCF integer
     `tracker_id`, not the `tracks.id` UUID, so `person_embeddings.track_id`
     (the UUID FK) is written NULL. We add a nullable `tracker_id INT` so the
     matcher can resolve the Track by (tenant_id, camera_id, tracker_id) whose
     lifetime window contains the embedding's `captured_at`, then set
     `tracks.person_id`.

  2. A running weight for the canonical centroid. `persons.canonical_embedding`
     is a quality-weighted mean of unit vectors; to update it incrementally
     and exactly we persist the accumulated weight in `embedding_weight_sum`.
     `appearance_count` counts tracks, not weights, so it can't serve here.

Existing rows
-------------
`tracker_id` is nullable with no backfill — embeddings written before this
migration simply won't get a Track link (they predate any matcher run).
`embedding_weight_sum` defaults to 0; the matcher seeds the real value when it
first sets a person's centroid.

Rollback path
-------------
downgrade() drops the new index, the `tracker_id` column, and the
`embedding_weight_sum` column. No data dependencies outside these.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0015_matcher"
down_revision = "0014_embedding_person_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) person_embeddings.tracker_id — the per-camera integer tracker id,
    # used to resolve the originating Track. Nullable; no FK (it's not a
    # surrogate key, it collides across camera reboots — see Track docstring).
    op.add_column(
        "person_embeddings",
        sa.Column("tracker_id", sa.Integer(), nullable=True),
    )
    # Composite index for the matcher's Track-resolution lookup.
    op.create_index(
        "ix_person_embeddings_cam_tracker",
        "person_embeddings",
        ["tenant_id", "camera_id", "tracker_id"],
    )

    # 2) persons.embedding_weight_sum — accumulated quality weight backing the
    # incremental canonical-centroid update.
    op.add_column(
        "persons",
        sa.Column(
            "embedding_weight_sum",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("persons", "embedding_weight_sum")
    op.drop_index(
        "ix_person_embeddings_cam_tracker", table_name="person_embeddings"
    )
    op.drop_column("person_embeddings", "tracker_id")
