"""Redis Streams → dual-write (pgvector + Milvus) for ReID embeddings.

Mirrors the pattern in app.modules.tracks.consumer. Reads from one
stream per tenant:

  vt:ds:embeddings:<tenant_id>

Each message has fields:
  camera_id        (UUID string)
  track_id         (int as string)
  captured_at_ms   (int as string)
  quality          (float as string)
  embedding        (JSON-encoded list of 512 floats)

Consumer group: vt-backend-consumers
Consumer name: $HOSTNAME

Failure model:
  - pg write fails: don't ack, message redelivered later
  - Milvus write fails: ack anyway, pg has the row; reconciliation later
  - Redis disconnect: backoff and retry
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from redis.exceptions import ResponseError
from sqlalchemy import select

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.persons.embedding_writer import write_embedding
from app.modules.tenants.models import Tenant

log = get_logger("persons.consumer")

# Match the conventions in tracks/consumer.py
CONSUMER_GROUP = "vt-backend-consumers"
CONSUMER_NAME = os.getenv("HOSTNAME", "backend-1")
BLOCK_MS = 1000
READ_COUNT = 100


class EmbeddingConsumer:
    """Top-level supervisor — one task per tenant for the embeddings stream.

    Started from app.main lifespan, stopped from same.
    """

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._stop = asyncio.Event()
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        self._redis = redis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        await self._redis.ping()
        log.info("consumer.connected", redis_url=settings.REDIS_URL)

        self._tasks["__discovery"] = asyncio.create_task(
            self._discovery_loop(), name="embeddings-discovery"
        )

    async def stop(self) -> None:
        log.info("consumer.stopping")
        self._stop.set()
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        log.info("consumer.stopped")

    async def _discovery_loop(self) -> None:
        while not self._stop.is_set():
            try:
                tenant_ids = await self._fetch_tenant_ids()
                for tid in tenant_ids:
                    self._ensure_task(
                        f"embeddings:{tid}",
                        self._consume_embedding_stream(tid),
                    )
            except Exception as e:
                log.warning("consumer.discovery_failed", error=str(e))

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass

    def _ensure_task(self, key: str, coro) -> None:
        existing = self._tasks.get(key)
        if existing is not None and not existing.done():
            return
        if existing is not None and existing.done():
            exc = existing.exception() if not existing.cancelled() else None
            if exc is not None:
                log.warning("consumer.task_died_respawning", key=key, error=str(exc))
        self._tasks[key] = asyncio.create_task(coro, name=key)

    async def _fetch_tenant_ids(self) -> list[UUID]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tenant.id))
            return [row[0] for row in result.all()]

    async def _ensure_consumer_group(self, stream_key: str) -> None:
        """Create the consumer group if it doesn't already exist.

        XGROUP CREATE on a non-existent stream with MKSTREAM=True
        bootstraps the stream itself, so we don't need a separate XADD
        seed before the worker starts producing.
        """
        if self._redis is None:
            return
        try:
            await self._redis.xgroup_create(
                name=stream_key,
                groupname=CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            log.info("consumer.group_created", stream=stream_key)
        except ResponseError as e:
            # BUSYGROUP = already exists; benign.
            if "BUSYGROUP" not in str(e):
                log.warning("consumer.group_create_failed", error=str(e))

    async def _consume_embedding_stream(self, tenant_id: UUID) -> None:
        stream_key = f"{settings.EMBEDDING_STREAM_PREFIX}:{tenant_id}"
        await self._ensure_consumer_group(stream_key)

        log.info("consumer.embeddings_starting", tenant_id=str(tenant_id))

        backoff = 1.0
        while not self._stop.is_set():
            try:
                entries = await self._redis.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={stream_key: ">"},
                    count=READ_COUNT,
                    block=BLOCK_MS,
                )
            except Exception as e:
                log.warning(
                    "consumer.read_failed",
                    tenant_id=str(tenant_id),
                    error=str(e),
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            backoff = 1.0

            if not entries:
                continue

            for _, items in entries:
                ids_to_ack: list[str] = []
                for entry_id, fields in items:
                    try:
                        await self._handle_embedding(tenant_id, fields)
                        ids_to_ack.append(entry_id)
                    except Exception as e:
                        log.warning(
                            "consumer.handle_failed",
                            tenant_id=str(tenant_id),
                            entry_id=entry_id,
                            error=str(e),
                        )
                if ids_to_ack:
                    try:
                        await self._redis.xack(stream_key, CONSUMER_GROUP, *ids_to_ack)
                    except Exception as e:
                        log.warning("consumer.ack_failed", error=str(e))

    async def _handle_embedding(
        self, tenant_id: UUID, fields: dict[str, str]
    ) -> None:
        """Decode + dual-write one embedding."""
        try:
            camera_id = UUID(fields["camera_id"])
            track_id = int(fields["track_id"])
            captured_at_ms = int(fields["captured_at_ms"])
            quality = float(fields["quality"])
            embedding = json.loads(fields["embedding"])
        except (KeyError, ValueError) as e:
            log.warning("consumer.decode_failed", error=str(e), fields=str(fields)[:200])
            # Don't re-raise — let it ack so we don't redeliver bad data forever
            return

        # Sanity-check the embedding shape (512-dim float vector)
        if not isinstance(embedding, list) or len(embedding) != 512:
            log.warning(
                "consumer.invalid_embedding_shape",
                length=len(embedding) if isinstance(embedding, list) else -1,
            )
            return

        async with AsyncSessionLocal() as db:
            try:
                await write_embedding(
                    db=db,
                    tenant_id=tenant_id,
                    camera_id=camera_id,
                    track_id=track_id,
                    captured_at_ms=captured_at_ms,
                    quality=quality,
                    embedding=embedding,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise  # propagate so we don't ack


# Module-level singleton (matches tracks/consumer.py shape)
consumer = EmbeddingConsumer()
