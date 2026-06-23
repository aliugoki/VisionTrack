"""Dual-write embedding persistence.

Writes one ReID embedding to BOTH pgvector (source of truth) AND Milvus
(hot path for similarity search).

Order matters:
  1. Write to pgvector FIRST. If this fails, abort. We never write to
     Milvus without a pg row, because the matcher (P2.5) treats pg as
     authoritative and orphan Milvus entries would point at nothing.
  2. Write to Milvus SECOND, referencing the pg row's UUID. If this
     fails, the pg row is still valid — the matcher can fall back to
     pgvector. Background reconciliation can later rebuild missing
     Milvus rows from pg.

This is at-most-once for Milvus, exactly-once for pg. Acceptable: pg
is the source of truth.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core import milvus as milvus_module
from app.modules.persons.models import PersonEmbedding

log = get_logger("persons.embedding_writer")


async def write_embedding(
    db: AsyncSession,
    tenant_id: UUID,
    camera_id: UUID,
    track_id: int,
    captured_at_ms: int,
    quality: float,
    embedding: list[float],
) -> UUID | None:
    """Write one embedding to pg + Milvus. Returns the pg row UUID, or
    None if the pg write failed.

    person_id is left NULL (P2.5 matcher will claim it later — see
    migration 0014).
    The pg `track_id` FK to tracks.id requires the UUID, which we don't
    have at ingest (the worker only knows the integer tracker id). So we
    persist that integer in `tracker_id` (see migration 0015) and leave
    the UUID FK NULL; the matcher resolves the Track by
    (tenant_id, camera_id, tracker_id) + captured_at window and sets both
    `track_id` and `tracks.person_id`. Milvus also keeps the int for
    debugging/re-association.
    """
    embedding_id = uuid4()
    captured_at = datetime.fromtimestamp(captured_at_ms / 1000.0, tz=timezone.utc)

    # ---- 1. pgvector (source of truth) -----------------------------
    row = PersonEmbedding(
        id=embedding_id,
        person_id=None,  # Matcher will set this — see migration 0014
        tenant_id=tenant_id,
        embedding=embedding,
        quality_score=quality,
        captured_at=captured_at,
        camera_id=camera_id,
        # UUID FK left NULL — matcher resolves it from tracker_id. See docstring.
        track_id=None,
        tracker_id=track_id,
    )
    try:
        db.add(row)
        await db.flush()
    except Exception as e:
        log.warning(
            "writer.pg_failed",
            tenant_id=str(tenant_id),
            camera_id=str(camera_id),
            track_id=track_id,
            error=str(e),
        )
        # Don't proceed to Milvus. Caller will not ack and Redis redelivers.
        raise

    # ---- 2. Milvus (best-effort hot path) --------------------------
    if not milvus_module.is_available():
        return embedding_id

    coll = milvus_module.get_collection()
    if coll is None:
        log.debug("writer.milvus_unavailable_skipping")
        return embedding_id

    try:
        # pymilvus is sync; run in thread to keep the consumer loop responsive.
        await asyncio.to_thread(
            _milvus_insert,
            coll,
            embedding_id=str(embedding_id),
            tenant_id=str(tenant_id),
            track_id=str(track_id),
            camera_id=str(camera_id),
            captured_at_ms=captured_at_ms,
            quality=quality,
            embedding=embedding,
        )
    except Exception as e:
        log.warning(
            "writer.milvus_failed",
            embedding_id=str(embedding_id),
            error=str(e),
        )
        # pg row is already committed-ready (flushed). Don't raise — we
        # return success-from-pg's perspective; Milvus is best-effort.

    return embedding_id


def _milvus_insert(
    coll,
    embedding_id: str,
    tenant_id: str,
    track_id: str,
    camera_id: str,
    captured_at_ms: int,
    quality: float,
    embedding: list[float],
) -> None:
    """Sync Milvus insert. Called via asyncio.to_thread."""
    coll.insert(
        [
            [embedding_id],
            [tenant_id],
            [track_id],
            [camera_id],
            [captured_at_ms],
            [float(quality)],
            [embedding],
        ]
    )
    # No flush() here — Milvus auto-flushes periodically. Explicit flush
    # would block; we accept ~1s search lag for inserted vectors as the
    # trade-off.
