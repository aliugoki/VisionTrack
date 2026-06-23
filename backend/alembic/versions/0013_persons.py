"""P2.1 — persons + person_embeddings + tracks.person_id + tenants.use_deepstream

Foundations for the DeepStream + ReID migration (P2 ADR section 7-8).

This migration:
  1. Creates the pgvector extension (PostgreSQL 0.7.2+, bundled in
     timescale/timescaledb:2.17.0-pg16).
  2. Creates the `persons` table — one row per cross-camera identity.
  3. Creates `person_embeddings` table with HNSW index for fast
     nearest-neighbor over 512-dim OSNet-x0_25 ReID vectors.
  4. Adds `tracks.person_id` (nullable FK) so the matcher can assign
     each per-camera track to a cross-camera person.
  5. Adds `tenants.use_deepstream` feature flag (defaults FALSE) for
     parallel-run / cutover toggle.

ROLLBACK:
  Drops the two new tables, drops `tracks.person_id`, drops
  `tenants.use_deepstream`. Leaves the vector extension installed
  (cheap to leave, expensive to drop with dependents).

NOTE: This migration is reversible. After cutover (P2.6), if you
want to fully roll back to P1, downgrade to the previous revision.

Revision ID: 0013_persons
Revises: <PARENT_HEAD>
Create Date: 2026-06-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Revision identifiers, used by Alembic.
revision: str = "0013_persons"
down_revision: str | None = "0012_tenant_retention"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # 1) pgvector extension — required for the Vector column type
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2) persons table
    op.create_table(
        "persons",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "appearance_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        # canonical_embedding is the running centroid of all
        # person_embeddings for this person. Created as nullable here,
        # then we alter the type to vector(512) via raw SQL because the
        # SQLAlchemy types don't support the parametric form in DDL.
        sa.Column(
            "canonical_embedding",
            sa.LargeBinary(),  # placeholder — altered below
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_persons_tenant_id", "persons", ["tenant_id"])

    # Convert placeholder column to vector(512)
    op.execute("ALTER TABLE persons DROP COLUMN canonical_embedding")
    op.execute("ALTER TABLE persons ADD COLUMN canonical_embedding vector(512)")

    # 3) person_embeddings table
    op.create_table(
        "person_embeddings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
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
        sa.Column(
            "embedding",
            sa.LargeBinary(),  # placeholder — altered below
            nullable=False,
        ),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_person_embeddings_person_id", "person_embeddings", ["person_id"]
    )
    op.create_index(
        "ix_person_embeddings_tenant_id", "person_embeddings", ["tenant_id"]
    )
    op.create_index(
        "ix_person_embeddings_captured_at",
        "person_embeddings",
        ["captured_at"],
    )

    # Convert placeholder embedding column to vector(512)
    op.execute("ALTER TABLE person_embeddings DROP COLUMN embedding")
    # Empty table at this migration point — safe to add the column
    # NOT NULL without a DEFAULT (no existing rows to populate).
    op.execute(
        "ALTER TABLE person_embeddings ADD COLUMN embedding vector(512) NOT NULL"
    )

    # HNSW index on the embedding column for nearest-neighbor search.
    # Cosine distance because OSNet embeddings are L2-normalized so
    # cosine and Euclidean rank identically; cosine is the convention.
    # m=16, ef_construction=64 are pgvector's recommended defaults for
    # general use; bump these only after measuring recall on a real
    # corpus.
    op.execute(
        "CREATE INDEX ix_person_embeddings_vector "
        "ON person_embeddings USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # 4) tracks.person_id — nullable FK. Existing tracks stay NULL;
    # the matcher will only populate person_id for tracks created
    # after DeepStream cutover.
    op.add_column(
        "tracks",
        sa.Column(
            "person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_tracks_person_id", "tracks", ["person_id"])

    # 5) tenants.use_deepstream — feature flag, default FALSE
    op.add_column(
        "tenants",
        sa.Column(
            "use_deepstream",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    # Reverse order of upgrade
    op.drop_column("tenants", "use_deepstream")

    op.drop_index("ix_tracks_person_id", table_name="tracks")
    op.drop_column("tracks", "person_id")

    op.drop_index(
        "ix_person_embeddings_vector", table_name="person_embeddings"
    )
    op.drop_index(
        "ix_person_embeddings_captured_at", table_name="person_embeddings"
    )
    op.drop_index(
        "ix_person_embeddings_tenant_id", table_name="person_embeddings"
    )
    op.drop_index(
        "ix_person_embeddings_person_id", table_name="person_embeddings"
    )
    op.drop_table("person_embeddings")

    op.drop_index("ix_persons_tenant_id", table_name="persons")
    op.drop_table("persons")

    # Note: we intentionally do NOT drop the vector extension.
    # Dropping it cascades to any column using vector(N) and is
    # expensive to recover. Leaving it costs nothing.
