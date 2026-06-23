"""Backfill script: scan /recordings and index every existing MP4 into DB.

Usage (run inside the backend container):
  docker compose exec backend python /app/scripts/index_recordings.py

What it does:
  1. For each subdir of /recordings (one per camera's mediamtx_path):
     - Look up the camera by mediamtx_path
     - For each MP4 file in that dir:
       - Parse the filename for started_at (format: YYYY-MM-DD_HH-MM-SS.mp4)
       - Probe the file with ffprobe for duration / size / codec
       - Insert (or skip if storage_path already exists) a Recording row

Why probe?
  MediaMTX's webhook only fires for NEW segments after we enable it.
  Existing files predate the webhook. We want them queryable too.

Idempotency:
  storage_path is UNIQUE — re-running won't double-insert.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# eager-load all models so SQLAlchemy relationship strings can resolve.
# Without these the script-local mapper init blows up on Camera.site
# (which references 'Site' by string).
from app.modules.tenants import models as _tenants  # noqa: F401
from app.modules.users import models as _users  # noqa: F401
from app.modules.roles import models as _roles  # noqa: F401
from app.modules.sites import models as _sites  # noqa: F401
from app.modules.alerts import models as _alerts  # noqa: F401
from app.modules.floor_plans import models as _floor_plans  # noqa: F401
from app.modules.tracks import models as _tracks  # noqa: F401
from app.modules.live_wall import models as _live_wall  # noqa: F401

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.cameras.models import Camera
from app.modules.recordings.models import Recording


log = get_logger("backfill.recordings")

RECORDINGS_ROOT = Path("/recordings")
# Filename pattern: 2026-06-06_10-01-04.mp4
TS_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.mp4$")


def parse_started_at(filename: str) -> datetime | None:
    """Parse a filename like '2026-06-06_10-01-04.mp4' to a UTC datetime."""
    m = TS_PATTERN.match(filename)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def probe_file(path: Path) -> dict:
    """ffprobe -> dict of {duration, codec, width, height}. Best-effort."""
    if not shutil.which("ffprobe"):
        return {}
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=duration,size:stream=codec_name,width,height",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        return {
            "codec": stream.get("codec_name"),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "duration": float(fmt.get("duration") or 0.0) or None,
            "size_bytes": int(fmt.get("size") or 0) or None,
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return {}


async def main() -> int:
    if not RECORDINGS_ROOT.exists():
        print(f"FATAL: {RECORDINGS_ROOT} does not exist", file=sys.stderr)
        return 1

    inserted = 0
    skipped_dup = 0
    skipped_unknown_cam = 0
    skipped_bad_filename = 0

    async with AsyncSessionLocal() as db:
        # Build a lookup of mediamtx_path -> Camera in one query
        cams = (await db.execute(select(Camera))).scalars().all()
        by_path: dict[str, Camera] = {c.mediamtx_path: c for c in cams}
        # Also keep a set of existing storage_paths for fast skip
        existing = set(
            (await db.execute(select(Recording.storage_path))).scalars().all()
        )

        for cam_dir in sorted(RECORDINGS_ROOT.iterdir()):
            if not cam_dir.is_dir():
                continue
            mediamtx_path = cam_dir.name
            camera = by_path.get(mediamtx_path)
            if camera is None:
                print(f"  skip dir {mediamtx_path}: no matching camera")
                continue

            for mp4_path in sorted(cam_dir.glob("*.mp4")):
                started_at = parse_started_at(mp4_path.name)
                if started_at is None:
                    skipped_bad_filename += 1
                    continue
                if str(mp4_path) in existing:
                    skipped_dup += 1
                    continue

                info = probe_file(mp4_path)
                duration = info.get("duration")
                ended_at = None
                if duration:
                    from datetime import timedelta
                    ended_at = started_at + timedelta(seconds=duration)

                # File size fallback via stat() if ffprobe missed it
                size_bytes = info.get("size_bytes")
                if not size_bytes:
                    try:
                        size_bytes = mp4_path.stat().st_size
                    except OSError:
                        size_bytes = 0

                rec = Recording(
                    tenant_id=camera.tenant_id,
                    camera_id=camera.id,
                    started_at=started_at,
                    ended_at=ended_at,
                    storage_path=str(mp4_path),
                    size_bytes=size_bytes,
                    codec=(info.get("codec") or camera.codec or "").upper() or None,
                    width_px=info.get("width"),
                    height_px=info.get("height"),
                    duration_seconds=duration,
                )
                db.add(rec)
                try:
                    await db.flush()
                    inserted += 1
                except IntegrityError:
                    await db.rollback()
                    skipped_dup += 1

        await db.commit()

    print(
        f"Backfill complete: inserted={inserted}, "
        f"skipped_duplicate={skipped_dup}, "
        f"skipped_unknown_camera={skipped_unknown_cam}, "
        f"skipped_bad_filename={skipped_bad_filename}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
