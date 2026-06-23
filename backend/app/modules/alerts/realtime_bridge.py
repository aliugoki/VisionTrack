"""Bridge: Redis pub/sub (from Celery worker) → Socket.IO broadcast.

Why this exists:
  The alert evaluator runs inside a Celery worker process. The Socket.IO
  server runs inside the FastAPI process. They share Postgres + Redis but
  nothing else, so the worker can't directly call broadcast_to_tenant().

  This module subscribes to a Redis pub/sub pattern (`vt:alerts:*`) from
  inside the FastAPI process, and forwards every received message to
  `broadcast_to_tenant()` for delivery to connected clients.

Channel naming:
  `vt:alerts:<tenant_id>` — one channel per tenant.
  Payload (JSON-encoded): a full AlertRead-shaped dict, plus a `kind`
  field indicating "fired" / "acknowledged" / "resolved" so the client
  knows whether to add or patch in their cache.

Failure model:
  - Redis disconnect: backoff and reconnect. The subscription is rebuilt
    on each connect cycle. Briefly-missed messages are NOT replayed —
    clients use the REST endpoint at WebSocket reconnect time to catch
    up. (Same pattern as the tracks consumer.)
  - Malformed payload: log + skip. Don't crash the whole bridge for
    one bad message.
"""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.modules.realtime.socketio_app import broadcast_to_tenant


log = get_logger("alerts.realtime_bridge")

# Pattern that matches every tenant's alert channel
SUBSCRIBE_PATTERN = "vt:alerts:*"

# Event names emitted to Socket.IO clients. Match what the frontend
# `useAlertsStream` hook listens for.
EVENT_ALERT_FIRED = "alert.fired"
EVENT_ALERT_ACKED = "alert.acknowledged"
EVENT_ALERT_RESOLVED = "alert.resolved"


class AlertsRealtimeBridge:
    """One bridge instance per backend process. Started by main lifespan."""

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return  # already running
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="alerts-realtime-bridge")
        log.info("alerts.bridge.started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
        log.info("alerts.bridge.stopped")

    async def _run(self) -> None:
        """Main loop: subscribe, forward messages, reconnect on failure."""
        while not self._stop.is_set():
            try:
                await self._subscribe_loop()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("alerts.bridge.reconnect_after_error", error=str(e))
                await asyncio.sleep(2.0)

    async def _subscribe_loop(self) -> None:
        self._redis = redis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(SUBSCRIBE_PATTERN)
        log.info("alerts.bridge.subscribed", pattern=SUBSCRIBE_PATTERN)

        try:
            async for message in pubsub.listen():
                if self._stop.is_set():
                    break
                # `listen()` yields ALL events: subscribe acks, pmessage,
                # etc. We only forward pmessage payloads.
                if message.get("type") != "pmessage":
                    continue

                channel = message.get("channel", "")
                # channel = "vt:alerts:<tenant_uuid>"
                _, _, tenant_id = channel.partition("vt:alerts:")
                if not tenant_id:
                    log.warning("alerts.bridge.bad_channel", channel=channel)
                    continue

                raw = message.get("data", "")
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError) as e:
                    log.warning(
                        "alerts.bridge.bad_payload", err=str(e), raw=raw[:200]
                    )
                    continue

                # Payload shape: { kind: "fired"|"acked"|"resolved", alert: {...} }
                kind = payload.get("kind", "fired")
                if kind == "fired":
                    event = EVENT_ALERT_FIRED
                elif kind == "acknowledged":
                    event = EVENT_ALERT_ACKED
                elif kind == "resolved":
                    event = EVENT_ALERT_RESOLVED
                else:
                    log.warning("alerts.bridge.unknown_kind", kind=kind)
                    continue

                await broadcast_to_tenant(
                    tenant_id, event, payload.get("alert", {})
                )
        finally:
            try:
                await pubsub.punsubscribe(SUBSCRIBE_PATTERN)
                await pubsub.aclose()
            except Exception:
                pass


# Module-level singleton — imported and started by main.py's lifespan.
alerts_realtime_bridge = AlertsRealtimeBridge()
