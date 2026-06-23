"""P2.5 cross-camera matcher.

Turns accumulated ReID embeddings into cross-camera `Person` identities.

Runtime model
-------------
A background asyncio task started/stopped from app.main lifespan, mirroring
EmbeddingConsumer. One process, single instance. Every
MATCHER_INTERVAL_SECONDS it sweeps each tenant: claims a batch of unmatched
`person_embeddings` (person_id IS NULL), and for each one finds the nearest
existing identity by pgvector cosine similarity against
`persons.canonical_embedding`.

  - sim >= MATCHER_MATCH_THRESHOLD  -> assign to that Person
  - otherwise                       -> create a new Person

On assign/create we set `person_embeddings.person_id`, bump
`appearance_count`, refresh `first/last_seen_at`, fold the vector into the
person's quality-weighted canonical centroid, and resolve + set
`tracks.person_id` for the originating Track.

Why pgvector (not Milvus) for the match search
-----------------------------------------------
pgvector is the source of truth and the matcher must keep forming identities
even when Milvus is degraded. We search the small `persons` centroid table
(one row per identity), not the full embeddings table.

Concurrency / idempotency
--------------------------
The embedding consumer inserts new NULL-person rows continuously. We claim
batches with FOR UPDATE SKIP LOCKED so we never block the consumer's inserts
and a second matcher instance (should one ever run) can't double-process a
row. A row transitions NULL -> person_id exactly once, inside the same
transaction that increments the count, so re-runs can't double-count. The
matcher writes nothing external (no Redis ack, no Milvus), so a rolled-back
batch simply retries deterministically next pass.
"""

from __future__ import annotations

import asyncio
import math
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.persons.models import Person, PersonEmbedding
from app.modules.tenants.models import Tenant
from app.modules.tracks.models import Track

log = get_logger("persons.matcher")


# ---------------------------------------------------------------------------
# Centroid math (pure Python — numpy is intentionally NOT a backend dep)
# ---------------------------------------------------------------------------

def _l2_normalize(vec: list[float]) -> list[float]:
    """Return vec scaled to unit L2 norm. Zero vectors are returned as-is."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return list(vec)
    return [x / norm for x in vec]


def update_centroid(
    c_prev: list[float],
    w_prev: float,
    v_new: list[float],
    w_new: float,
) -> list[float]:
    """Fold a new (unit) vector into a quality-weighted running centroid.

    The centroid is the weighted mean of the contributing unit vectors,
    re-normalized to unit length (a mean of unit vectors is not itself unit
    length). `w_prev` is the accumulated weight backing `c_prev`.

        raw   = w_prev * c_prev + w_new * v_new
        result = raw / ||raw||
    """
    raw = [w_prev * c + w_new * x for c, x in zip(c_prev, v_new)]
    return _l2_normalize(raw)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Plain cosine similarity. Used by unit tests / when not delegating to
    pgvector. Returns 0.0 if either vector is zero-length."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class PersonMatcher:
    """Background supervisor — periodically sweeps every tenant.

    Started from app.main lifespan, stopped from the same.
    """

    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="person-matcher")
        log.info(
            "matcher.started",
            interval_s=settings.MATCHER_INTERVAL_SECONDS,
            threshold=settings.MATCHER_MATCH_THRESHOLD,
        )

    async def stop(self) -> None:
        log.info("matcher.stopping")
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        log.info("matcher.stopped")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                tenant_ids = await self._fetch_tenant_ids()
                for tid in tenant_ids:
                    await self._run_tenant(tid)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # never let the loop die
                log.warning("matcher.sweep_failed", error=str(e))

            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=settings.MATCHER_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                pass

    async def _fetch_tenant_ids(self) -> list[UUID]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tenant.id))
            return [row[0] for row in result.all()]

    async def _run_tenant(self, tenant_id: UUID) -> None:
        """Drain this tenant's backlog one batch at a time until empty."""
        total = 0
        while not self._stop.is_set():
            n = await self._run_tenant_batch(tenant_id)
            total += n
            if n < settings.MATCHER_BATCH_SIZE:
                break  # drained (a short batch means no more unmatched rows)
        if total:
            log.info("matcher.tenant_done", tenant_id=str(tenant_id), matched=total)

    async def _run_tenant_batch(self, tenant_id: UUID) -> int:
        """Process one batch of unmatched embeddings. Returns rows processed."""
        async with AsyncSessionLocal() as db:
            try:
                rows = await self._claim_batch(db, tenant_id)
                if not rows:
                    return 0
                for emb in rows:
                    await self._match_one(db, tenant_id, emb)
                    await db.flush()  # so the next row sees new identities
                await db.commit()
                return len(rows)
            except Exception:
                await db.rollback()
                raise

    async def _claim_batch(
        self, db: AsyncSession, tenant_id: UUID
    ) -> list[PersonEmbedding]:
        stmt = (
            select(PersonEmbedding)
            .where(
                PersonEmbedding.tenant_id == tenant_id,
                PersonEmbedding.person_id.is_(None),
            )
            .order_by(PersonEmbedding.captured_at)  # oldest first
            .limit(settings.MATCHER_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _match_one(
        self, db: AsyncSession, tenant_id: UUID, emb: PersonEmbedding
    ) -> None:
        vec = _l2_normalize(list(emb.embedding))
        weight = max(
            emb.quality_score if emb.quality_score is not None else 0.0,
            settings.MATCHER_MIN_QUALITY_WEIGHT,
        )

        # Nearest existing identity by cosine distance (pgvector <=>).
        distance = Person.canonical_embedding.cosine_distance(vec)
        nearest = (
            await db.execute(
                select(Person, distance.label("distance"))
                .where(
                    Person.tenant_id == tenant_id,
                    Person.canonical_embedding.is_not(None),
                )
                .order_by(distance)
                .limit(1)
            )
        ).first()

        if nearest is not None:
            person, dist = nearest
            similarity = 1.0 - float(dist)
        else:
            person, similarity = None, -1.0

        if person is not None and similarity >= settings.MATCHER_MATCH_THRESHOLD:
            # ---- assign to existing identity ----
            person.appearance_count += 1
            if emb.captured_at > person.last_seen_at:
                person.last_seen_at = emb.captured_at
            if emb.captured_at < person.first_seen_at:
                person.first_seen_at = emb.captured_at
            person.canonical_embedding = update_centroid(
                list(person.canonical_embedding),
                person.embedding_weight_sum,
                vec,
                weight,
            )
            person.embedding_weight_sum += weight
        else:
            # ---- create a new identity ----
            person = Person(
                tenant_id=tenant_id,
                first_seen_at=emb.captured_at,
                last_seen_at=emb.captured_at,
                appearance_count=1,
                canonical_embedding=vec,
                embedding_weight_sum=weight,
            )
            db.add(person)
            await db.flush()  # assign person.id

        emb.person_id = person.id
        await self._link_track(db, tenant_id, emb, person.id)

    async def _link_track(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        emb: PersonEmbedding,
        person_id: UUID,
    ) -> None:
        """Resolve the originating Track and set tracks.person_id.

        The embedding carries the per-camera integer tracker_id; we find the
        Track whose lifetime window contains captured_at. Silent no-op if we
        can't resolve one (e.g. lifecycle event not yet consumed) — a later
        embedding of the same track will link it.
        """
        if emb.tracker_id is None or emb.camera_id is None:
            return
        track_id = (
            await db.execute(
                select(Track.id)
                .where(
                    Track.tenant_id == tenant_id,
                    Track.camera_id == emb.camera_id,
                    Track.tracker_id == emb.tracker_id,
                    Track.started_at <= emb.captured_at,
                    or_(
                        Track.ended_at.is_(None),
                        Track.ended_at >= emb.captured_at,
                    ),
                )
                .order_by(Track.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if track_id is None:
            return
        await db.execute(
            update(Track)
            .where(Track.id == track_id, Track.tenant_id == tenant_id)
            .values(person_id=person_id)
        )
        emb.track_id = track_id  # backfill the UUID FK now that we know it


# Module-level singleton (matches consumer.py shape).
matcher = PersonMatcher()
