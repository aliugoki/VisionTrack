"""Redis state for the alert evaluator.

Two state domains live here:

1. Per-camera track presence (which track_ids have been seen recently).
   Source: AI worker's `vt:tracks:<tenant_id>` stream.
   Storage: `vt:track_presence:<tenant_id>:<camera_id>` sorted set,
            score = last_seen_ms.

2. Per-rule evaluator state (hold-time + hysteresis).
   Storage: `vt:alert_state:<tenant_id>:<zone_id>:<rule_id>` hash,
            fields {condition_since_ms, armed, last_fire_ms}.

Why a sorted set for track presence?
  - O(log N) for inserting a "track seen at time T"
  - O(log N + count) for "how many tracks seen in the last 5 seconds"
    via ZRANGEBYSCORE — fast even with thousands of tracks
  - O(log N + removed) for garbage-collecting expired entries

This module is async because it calls Redis via redis.asyncio. The
Celery task layer above uses asyncio.run() to bridge.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any
from uuid import UUID

import redis.asyncio as redis

from app.modules.alerts.evaluator import RuleState


log = logging.getLogger("alerts.track_state")


# Active window: a track is considered "currently in view" if its last
# detection was within this many ms ago. Matches the camera frame rate
# we publish at (10 fps → 100ms/frame) with generous slack for buffering.
ACTIVE_WINDOW_MS = 5_000

# How long to keep a stale track in the sorted set before garbage-collecting.
# Larger than ACTIVE_WINDOW_MS so a brief network blip doesn't cause us to
# forget a person who returns.
RETENTION_MS = 30_000

# Stream consumer group + name. Group must be created idempotently on
# first read of each new tenant stream.
CONSUMER_GROUP = "alerts-evaluator"
CONSUMER_NAME = "celery-worker-1"

# How many entries to read per stream fetch. The AI worker publishes
# one entry per camera per frame; at 10 fps × N cameras × 5s tick we
# expect 50N entries per tick. Reading 500 covers up to 10 cameras
# comfortably. If we fall behind it's still progress.
STREAM_BATCH_SIZE = 500
STREAM_READ_BLOCK_MS = 50  # short block so the evaluator doesn't hang


# ---------------------------------------------------------------------------
# Stream consumption
# ---------------------------------------------------------------------------

async def ensure_consumer_group(
    r: redis.Redis, stream_key: str, group: str = CONSUMER_GROUP
) -> None:
    """Create the consumer group if it doesn't exist. No-op if it does.

    We use MKSTREAM so the group can be created even before the AI
    worker has published anything.
    """
    try:
        await r.xgroup_create(stream_key, group, id="0", mkstream=True)
    except redis.ResponseError as e:
        # BUSYGROUP means already exists — that's fine.
        if "BUSYGROUP" not in str(e):
            raise


async def drain_tracks_stream(
    r: redis.Redis,
    tenant_id: UUID,
    now_ms: int,
) -> int:
    """Consume new track entries from the tenant's stream, update presence.

    Returns the number of stream entries processed.

    Stream entry shape (set by ai-worker/app/publisher.py):
      camera_id    str (UUID)
      frame_ts_ms  int
      tracks       json-encoded list of {track_id, bbox, confidence, class_id}

    We only care about class_id == 0 (person). Other classes (vehicles
    etc. in future) get ignored for occupancy purposes.
    """
    stream_key = f"vt:tracks:{tenant_id}"
    await ensure_consumer_group(r, stream_key)

    # Read NEW entries since last cursor. The "&gt;" cursor means
    # "deliver entries that have not yet been delivered to any
    # consumer in this group" — exactly the once-only semantics we want.
    try:
        result = await r.xreadgroup(
            CONSUMER_GROUP,
            CONSUMER_NAME,
            {stream_key: ">"},
            count=STREAM_BATCH_SIZE,
            block=STREAM_READ_BLOCK_MS,
        )
    except redis.ResponseError as e:
        log.warning("xreadgroup failed: %s", e)
        return 0

    if not result:
        return 0

    processed = 0
    # result is [(stream_key, [(entry_id, {fields}), ...])]
    for _stream_name, entries in result:
        for entry_id, fields in entries:
            processed += 1
            try:
                camera_id = fields["camera_id"]
                frame_ts_ms = int(fields["frame_ts_ms"])
                tracks_raw = fields.get("tracks", "[]")
                tracks = json.loads(tracks_raw)
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                # Bad message shape — log and move on; ack it so we don't
                # keep retrying.
                log.warning(
                    "malformed track entry id=%s err=%s", entry_id, e
                )
                await r.xack(stream_key, CONSUMER_GROUP, entry_id)
                continue

            # Update presence for each person-class detection
            presence_key = f"vt:track_presence:{tenant_id}:{camera_id}"
            pipe = r.pipeline(transaction=False)
            any_person = False
            for det in tracks:
                if det.get("class_id") != 0:
                    continue  # not a person
                any_person = True
                tid = str(det.get("track_id"))
                # ZADD with score = frame_ts_ms; updates score if already present
                pipe.zadd(presence_key, {tid: frame_ts_ms})
            if any_person:
                # Bound the set size — drop entries older than RETENTION_MS
                pipe.zremrangebyscore(
                    presence_key, "-inf", now_ms - RETENTION_MS
                )
                # Set a key TTL so a permanently offline camera's set
                # eventually clears out of Redis.
                pipe.expire(presence_key, 300)
            await pipe.execute()
            await r.xack(stream_key, CONSUMER_GROUP, entry_id)
    return processed


async def get_active_track_count(
    r: redis.Redis, tenant_id: UUID, camera_id: str, now_ms: int
) -> int:
    """How many tracks have been seen on this camera within ACTIVE_WINDOW_MS."""
    key = f"vt:track_presence:{tenant_id}:{camera_id}"
    return await r.zcount(key, now_ms - ACTIVE_WINDOW_MS, "+inf")


# ---------------------------------------------------------------------------
# Rule state (hold-time + hysteresis)
# ---------------------------------------------------------------------------

def _rule_state_key(tenant_id: UUID, zone_id: str, rule_id: str) -> str:
    return f"vt:alert_state:{tenant_id}:{zone_id}:{rule_id}"


async def load_rule_state(
    r: redis.Redis, tenant_id: UUID, zone_id: str, rule_id: str
) -> RuleState:
    """Read the persisted state, or return a fresh state if absent."""
    data = await r.hgetall(_rule_state_key(tenant_id, zone_id, rule_id))
    if not data:
        return RuleState(condition_since_ms=None, armed=False, last_fire_ms=None)
    return RuleState(
        condition_since_ms=(
            int(data["condition_since_ms"])
            if data.get("condition_since_ms") not in (None, "", "None")
            else None
        ),
        armed=data.get("armed", "0") == "1",
        last_fire_ms=(
            int(data["last_fire_ms"])
            if data.get("last_fire_ms") not in (None, "", "None")
            else None
        ),
    )


async def save_rule_state(
    r: redis.Redis,
    tenant_id: UUID,
    zone_id: str,
    rule_id: str,
    state: RuleState,
) -> None:
    """Persist state; key auto-expires after 24h of inactivity (safety net)."""
    key = _rule_state_key(tenant_id, zone_id, rule_id)
    pipe = r.pipeline(transaction=False)
    pipe.hset(
        key,
        mapping={
            "condition_since_ms": (
                str(state.condition_since_ms)
                if state.condition_since_ms is not None
                else ""
            ),
            "armed": "1" if state.armed else "0",
            "last_fire_ms": (
                str(state.last_fire_ms)
                if state.last_fire_ms is not None
                else ""
            ),
        },
    )
    pipe.expire(key, 86_400)
    await pipe.execute()


# ---------------------------------------------------------------------------
# Per-zone previous count (for entry rules)
# ---------------------------------------------------------------------------

async def load_prev_zone_count(
    r: redis.Redis, tenant_id: UUID, zone_id: str
) -> int:
    key = f"vt:zone_prev_count:{tenant_id}:{zone_id}"
    val = await r.get(key)
    return int(val) if val is not None else 0


async def save_prev_zone_count(
    r: redis.Redis, tenant_id: UUID, zone_id: str, count: int
) -> None:
    key = f"vt:zone_prev_count:{tenant_id}:{zone_id}"
    await r.set(key, count, ex=86_400)
