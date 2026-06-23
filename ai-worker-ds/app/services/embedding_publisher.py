"""Embedding publisher.

Long-lived asyncio task that drains the in-process queue populated by
reid_probe.py and XADDs each entry to Redis Streams.

Why a separate task and not direct XADD from the probe:
  - The probe runs on the GStreamer thread. Any blocking I/O there
    stalls the pipeline. We use queue.put_nowait() (microsecond) and let
    this task do the (potentially slow) Redis push asynchronously.
  - This decouples GST timing from network latency. If Redis spikes to
    100ms, the queue absorbs the burst.

Why drop on overflow:
  - If the queue is full, the probe drops (Queue.Full). If Redis is
    down, this task's XADD raises and we sleep + retry. The probe keeps
    running; we lose some embeddings but the pipeline doesn't stop.
  - At-most-once semantics are acceptable for embeddings: we sample
    ~1-per-second per person. Missing one sample doesn't lose the
    person.

Stream naming: vt:ds:embeddings:<tenant_id>
"""

from __future__ import annotations

import asyncio
import json
from queue import Empty, Queue
from typing import Any

import redis.asyncio as redis

from app.config import settings
from app.logging_config import get_logger

log = get_logger("embedding_publisher")

# Max wait per Redis XADD batch. Short — we want low latency between
# detection and Milvus availability.
BATCH_DRAIN_MS = 50


class EmbeddingPublisher:
    """Drains a sync queue into Redis Streams."""

    def __init__(self, queue: "Queue[dict[str, Any]]") -> None:
        self._queue = queue
        self._redis: redis.Redis | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._redis = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await self._redis.ping()
        log.info("publisher.connected", redis_url=settings.REDIS_URL)
        self._task = asyncio.create_task(self._run(), name="embedding-publisher")

    async def stop(self) -> None:
        log.info("publisher.stopping")
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        log.info("publisher.stopped")

    async def _run(self) -> None:
        """Drain loop. Reads from the sync queue, batches if possible,
        XADDs to Redis with tenant-scoped stream key."""
        published = 0
        errors = 0
        while not self._stop.is_set():
            # Drain whatever's available, up to a small batch. Sync queue
            # has no async interface, so we tick-drain in a loop with
            # tiny sleeps; not perfectly efficient but bounded latency.
            batch: list[dict[str, Any]] = []
            try:
                # First item: blocking-ish wait via short timeout
                item = await asyncio.to_thread(self._queue_get_with_timeout, 0.5)
                if item is not None:
                    batch.append(item)
            except Exception as e:
                log.warning("publisher.queue_read_failed", error=str(e))
                await asyncio.sleep(0.5)
                continue

            # Drain anything else queued without waiting
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except Empty:
                    break

            if not batch:
                continue

            try:
                pipeline = self._redis.pipeline(transaction=False)
                for payload in batch:
                    stream_key = (
                        f"{settings.EMBEDDING_STREAM_PREFIX}:{payload['tenant_id']}"
                    )
                    # XADD with explicit cap. The trimming is approximate
                    # (~) — Redis approximate trims are faster than exact.
                    fields = {
                        "camera_id": payload["camera_id"],
                        "track_id": str(payload["track_id"]),
                        "captured_at_ms": str(payload["captured_at_ms"]),
                        "quality": str(payload["quality"]),
                        # JSON-encode the embedding vector; ~6KB
                        "embedding": json.dumps(payload["embedding"]),
                    }
                    pipeline.xadd(
                        stream_key,
                        fields,
                        maxlen=settings.STREAM_MAX_LEN,
                        approximate=True,
                    )
                await pipeline.execute()
                published += len(batch)
            except Exception as e:
                errors += 1
                log.warning(
                    "publisher.xadd_failed",
                    batch_size=len(batch),
                    error=str(e),
                )
                # Don't requeue: at-most-once. Pause briefly to avoid
                # tight-loop on a sustained Redis outage.
                await asyncio.sleep(1.0)
                continue

            # Throttled progress log every ~1000 published
            if published % 1000 == 0 and published > 0:
                log.info("publisher.progress", published=published, errors=errors)

    def _queue_get_with_timeout(self, timeout: float) -> dict[str, Any] | None:
        """Sync wrapper for queue.get(timeout=…) to use via asyncio.to_thread."""
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None
