#!/usr/bin/env python3
"""Inject synthetic track events into the AI worker's Redis Stream.

Used to test the alert evaluator without needing a real person to walk
in front of a camera. Matches the exact shape `ai-worker/app/publisher.py`
produces, so the alert evaluator can't tell the difference.

Usage examples:

  # Burst: emit N people on a camera for a fixed duration, then stop.
  # Lets you verify occupancy_max + entry rules trigger correctly.
  python scripts/seed_test_tracks.py burst \
    --tenant-id 4ae93489-babb-4e8e-a476-c64f9bc8f64b \
    --camera-id 8a0b2ad4-7173-45e0-8f35-88a940ff460e \
    --count 7 \
    --duration 60

  # Pulse: alternate present/absent in a cycle. Lets you watch the
  # evaluator's rearm logic in action.
  python scripts/seed_test_tracks.py pulse \
    --tenant-id <tenant> \
    --camera-id <camera> \
    --on-seconds 20 --off-seconds 30 --cycles 3 --count 6

Run from inside the backend container so REDIS_URL resolves:
  docker compose exec backend python /app/scripts/seed_test_tracks.py burst ...
"""

import argparse
import asyncio
import json
import time
from uuid import UUID

import redis.asyncio as redis


# Match the AI worker's stream key convention (see ai-worker/app/publisher.py)
STREAM_PREFIX = "vt:tracks"
STREAM_MAX_LEN = 10_000
FRAME_INTERVAL_S = 0.1  # 10 fps publish rate


def _build_track(track_id: int) -> dict:
    """Synthetic detection with bbox roughly centered in 1920x1080 frame."""
    base_x = 600 + (track_id % 5) * 120
    return {
        "track_id": track_id,
        "bbox": [base_x, 400, base_x + 100, 800],
        "confidence": 0.92,
        "class_id": 0,  # person
    }


async def emit_frame(r, tenant_id: str, camera_id: str, count: int) -> None:
    """One frame's worth of events for `count` synthetic people."""
    tracks = [_build_track(i + 1) for i in range(count)]
    stream_key = f"{STREAM_PREFIX}:{tenant_id}"
    await r.xadd(
        stream_key,
        {
            "camera_id": camera_id,
            "frame_ts_ms": int(time.time() * 1000),
            "tracks": json.dumps(tracks),
        },
        maxlen=STREAM_MAX_LEN,
        approximate=True,
    )


async def run_burst(args) -> None:
    r = redis.from_url(args.redis_url, encoding="utf-8", decode_responses=True)
    try:
        end_at = time.time() + args.duration
        frames = 0
        while time.time() < end_at:
            await emit_frame(r, args.tenant_id, args.camera_id, args.count)
            frames += 1
            await asyncio.sleep(FRAME_INTERVAL_S)
        print(f"Burst complete: emitted {frames} frames × {args.count} tracks")
    finally:
        await r.aclose()


async def run_pulse(args) -> None:
    r = redis.from_url(args.redis_url, encoding="utf-8", decode_responses=True)
    try:
        for cycle in range(args.cycles):
            # ON phase
            print(f"Cycle {cycle + 1}/{args.cycles}: ON ({args.count} tracks for {args.on_seconds}s)")
            end_at = time.time() + args.on_seconds
            while time.time() < end_at:
                await emit_frame(r, args.tenant_id, args.camera_id, args.count)
                await asyncio.sleep(FRAME_INTERVAL_S)
            # OFF phase — emit zero-track frames so the evaluator sees count=0
            print(f"Cycle {cycle + 1}/{args.cycles}: OFF ({args.off_seconds}s)")
            end_at = time.time() + args.off_seconds
            while time.time() < end_at:
                await emit_frame(r, args.tenant_id, args.camera_id, 0)
                await asyncio.sleep(FRAME_INTERVAL_S)
        print("Pulse complete")
    finally:
        await r.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic track publisher")
    parser.add_argument(
        "--redis-url",
        default="redis://redis:6379/0",
        help="Redis URL. Default works inside docker-compose.",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    burst = sub.add_parser("burst", help="Constant N people for D seconds")
    burst.add_argument("--tenant-id", required=True)
    burst.add_argument("--camera-id", required=True)
    burst.add_argument("--count", type=int, default=5)
    burst.add_argument("--duration", type=int, default=60, help="seconds")
    burst.set_defaults(func=run_burst)

    pulse = sub.add_parser("pulse", help="Cycle on/off — tests rearm logic")
    pulse.add_argument("--tenant-id", required=True)
    pulse.add_argument("--camera-id", required=True)
    pulse.add_argument("--count", type=int, default=5)
    pulse.add_argument("--on-seconds", type=int, default=20)
    pulse.add_argument("--off-seconds", type=int, default=30)
    pulse.add_argument("--cycles", type=int, default=3)
    pulse.set_defaults(func=run_pulse)

    args = parser.parse_args()
    # Validate UUIDs early so a typo doesn't burn 60 seconds before erroring
    UUID(args.tenant_id)
    UUID(args.camera_id)
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
