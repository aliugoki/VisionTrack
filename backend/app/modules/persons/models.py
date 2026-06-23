"""Person and PersonEmbedding ORM models.

A Person is a cross-camera identity — one row per "physical person"
the cross-camera matcher has decided belongs together. Created
opportunistically by the matcher (P2.5 batch); read-only via API
in this batch (P2.1).

A PersonEmbedding is a single ReID feature vector sampled from a
detection. Sparse — not every frame; sampled by the AI worker
every N frames per track based on quality_score.

Schema relationship:

    persons (cross-camera identity)
       ↓ 1:N
    tracks (per-camera tracks, person_id added as nullable FK)
       ↓ 1:N
    track_points (unchanged — high-volume frame data)

    persons (cross-camera identity)
       ↓ 1:N
    person_embeddings (ReID vectors, sparse)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


# Dimensionality of OSNet-x0_25 embeddings (confirmed via torchreid model card).
# If we ever switch to TransReID (768) or OSNet-x1_0 (also 512), this is the
# place to change. Keep the migration's vector(N) in sync.
REID_DIM = 512


class Person(Base):
    """A cross-camera person identity.

    Created by the matcher (P2.5) when a new track's embedding doesn't
    match any existing person within distance threshold. Updated as new
    appearances arrive — `last_seen_at` and `appearance_count` are
    refreshed on every match; `canonical_embedding` is a running
    centroid updated periodically.
    """

    __tablename__ = "persons"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # How many distinct tracks across all cameras have been matched to
    # this person. Updated by the matcher.
    appearance_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Optional centroid embedding — running mean of all person_embeddings
    # for this person. Speeds up nearest-neighbor lookup (one query
    # against persons.canonical_embedding vs N queries against the
    # full person_embeddings table). Updated periodically by matcher,
    # nullable until the first embedding is observed.
    canonical_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(REID_DIM), nullable=True
    )

    # Accumulated quality weight behind canonical_embedding. The centroid is
    # a quality-weighted mean of unit vectors; this running sum lets the
    # matcher update it incrementally and exactly. Seeded by the matcher when
    # the first embedding is observed (see migration 0015).
    embedding_weight_sum: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PersonEmbedding(Base):
    """One ReID feature vector sample.

    Written by the AI worker once every N frames per active track when
    detection quality is high enough. Sparse storage by design — at
    full per-frame writes we'd have 30M+ rows/tenant/month; at 1-in-30
    sampling we're at ~1M/tenant/month which pgvector handles
    comfortably with HNSW.
    """

    __tablename__ = "person_embeddings"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # NULL until the matcher (P2.5) claims this embedding for an identity —
    # see migration 0014. The DeepStream consumer writes embeddings before
    # any Person exists.
    person_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The track this embedding was sampled from. Nullable because tracks
    # can be deleted (retention sweep) without losing the embedding —
    # we still want to know the person's history. The UUID FK is written
    # NULL at ingest (the worker only has the integer tracker id); the
    # matcher resolves and sets it via `tracker_id` below.
    track_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tracks.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The per-camera integer tracker id (ByteTrack/NvDCF). Stored so the
    # matcher can resolve the originating Track by
    # (tenant_id, camera_id, tracker_id) + captured_at window. See migration
    # 0015. Not a FK — collides across camera reboots.
    tracker_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    camera_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cameras.id", ondelete="SET NULL"),
        nullable=True,
    )

    embedding: Mapped[list[float]] = mapped_column(
        Vector(REID_DIM), nullable=False
    )

    # Heuristic: detection_confidence × normalized_bbox_area.
    # Used by the matcher to weight embeddings (high-quality ones
    # contribute more to the canonical centroid).
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class PersonIdentity(Base):
    """An external (face-recognition) identity label correlated onto a Person.

    Written by the face-identity consumer, which reads
    vt:face:identities:<tenant_id> (published by a separate face-recognition
    pipeline) and binds each event to a Person by correlating the event bbox to
    an active track (camera + bbox IoU + time). Deliberately separate from
    ReID: a face label is an OVERLAY on the tracked person, never an input to
    the cross-camera matcher, so a mislabel can't corrupt clustering.

    person_id is nullable because the event may correlate to a track that the
    matcher has not yet assigned to a Person; such rows are reconciled later.
    """

    __tablename__ = "person_identities"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # The track the event was correlated to (audit / reconciliation). Nullable
    # because tracks are subject to the retention sweep.
    track_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tracks.id", ondelete="SET NULL"),
        nullable=True,
    )
    camera_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cameras.id", ondelete="SET NULL"),
        nullable=True,
    )

    # The external identity (employee id + display name) from the face pipeline.
    emp_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="face"
    )

    # Running confidence + how many correlated events backed this label. A
    # vote/decay scheme upstream means one bad correlation can't flip a label.
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    votes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    first_labeled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_labeled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # One row per (tenant, person, emp_id). Rows with NULL person_id are
        # treated as distinct by Postgres (acceptable: they're pre-match audit).
        UniqueConstraint(
            "tenant_id", "person_id", "emp_id", name="uq_person_identity"
        ),
    )
