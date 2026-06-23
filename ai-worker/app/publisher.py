"""Redis Streams publisher.

Two streams per tenant:

  vt:tracks:<tenant_id>            — high-volume per-frame events. One entry
                                     per camera per inference cycle, containing
                                     a list of {track_id, bbox, confidence}.

  vt:track_lifecycle:<tenant_id>   — low-volume start/end events. One entry
                                     when a new track_id appears, one when it
                                     disappears (no detection for N frames).

The backend in Batch D consumes these via XREAD/XREADGROUP and persists
to TimescaleDB. Stream-based pub/sub gives us back-pressure for free
(if the consumer falls behind, events queue up rather than getting lost).
"""

import json
from typing import Any
from uuid import UUID

import redis.asyncio as redis

from app.config import settings
from app.logging_config import get_logger

log = get_logger("publisher")


class TrackPublisher:
    """Publishes detection + lifecycle events to Redis Streams.

    One instance shared across all camera pipelines. The redis client is
    asyncio-aware and the connection pool is thread-safe.
    """

    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    async def start(self) -> None:
        self._client = redis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        # Ping to surface connection errors at startup
        await self._client.ping()
        log.info("publisher.connected", redis_url=settings.REDIS_URL)

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def publish_tracks(
        self,
        tenant_id: UUID,
        camera_id: UUID,
        frame_ts_ms: int,
        tracks: list[dict[str, Any]],
    ) -> None:
        """Publish detections from one frame.

        `tracks` is a list of dicts shaped like:
          {
            "track_id": int,
            "bbox": [x1, y1, x2, y2],   # in source pixel space
            "confidence": float,
            "class_id": int,             # 0 = person
          }
        """
        if self._client is None or not tracks:
            return

        stream_key = f"{settings.TRACK_STREAM_PREFIX}:{tenant_id}"
        payload = {
            "camera_id": str(camera_id),
            "frame_ts_ms": frame_ts_ms,
            "tracks": json.dumps(tracks),
        }
        try:
            await self._client.xadd(
                stream_key,
                payload,
                maxlen=settings.STREAM_MAX_LEN,
                approximate=True,  # ~10x faster trim, slightly fuzzy length
            )
        except Exception as e:
            # Don't crash the inference loop on a transient Redis blip.
            log.warning("publisher.tracks_failed", error=str(e))

    async def publish_lifecycle(
        self,
        tenant_id: UUID,
        camera_id: UUID,
        track_id: int,
        event: str,  # "started" or "ended"
        ts_ms: int,
        first_bbox: list[float] | None = None,
    ) -> None:
        """Publish a track-start or track-end event."""
        if self._client is None:
            return

        stream_key = f"{settings.LIFECYCLE_STREAM_PREFIX}:{tenant_id}"
        payload = {
            "camera_id": str(camera_id),
            "track_id": str(track_id),
            "event": event,
            "ts_ms": ts_ms,
        }
        if first_bbox is not None:
            payload["bbox"] = json.dumps(first_bbox)
        try:
            await self._client.xadd(
                stream_key,
                payload,
                maxlen=settings.STREAM_MAX_LEN,
                approximate=True,
            )
        except Exception as e:
            log.warning("publisher.lifecycle_failed", error=str(e))

    async def publish_embedding(
        self,
        tenant_id: UUID,
        camera_id: UUID,
        track_id: int,
        captured_at_ms: int,
        quality: float,
        embedding: list[float],
    ) -> None:
        """Publish one ReID embedding to vt:ds:embeddings:<tenant_id>.

        Field schema MUST match the backend embedding consumer
        (backend/app/modules/persons/consumer.py): camera_id, track_id,
        captured_at_ms, quality, embedding (JSON-encoded 512-float list).
        `track_id` is the ByteTrack id — the same id used for this camera's
        Track rows, so the matcher can link the embedding back to its Track.
        """
        if self._client is None:
            return
        stream_key = f"{settings.EMBEDDING_STREAM_PREFIX}:{tenant_id}"
        payload = {
            "camera_id": str(camera_id),
            "track_id": str(track_id),
            "captured_at_ms": str(captured_at_ms),
            "quality": str(quality),
            "embedding": json.dumps(embedding),
        }
        try:
            await self._client.xadd(
                stream_key,
                payload,
                maxlen=settings.STREAM_MAX_LEN,
                approximate=True,
            )
        except Exception as e:
            log.warning("publisher.embedding_failed", error=str(e))
