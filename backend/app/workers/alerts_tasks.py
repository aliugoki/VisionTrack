"""Background task: evaluate all zone rules across all tenants.

Runs every ~5 seconds via Celery beat. Each invocation:
  1. For each active tenant, drain the AI worker's track stream into
     Redis presence sorted sets
  2. Load every floor plan + zones for the tenant
  3. For each zone:
     a. Find which cameras (via their marker positions on this plan)
        sit inside the zone polygon
     b. Sum their currently-active person counts → zone occupancy
     c. For each rule on the zone:
       - Check schedule
       - Run evaluator → maybe fire
       - Persist new rule state to Redis
       - Insert Alert row if fired
  4. Commit DB

Task-level idempotency:
  Beat sends one task per tick. If two ticks overlap (slow Redis or
  blocked DB), the second is harmless — the consumer group makes
  stream reads exactly-once and the rule-state lock prevents double
  fires. Worst case: a tick takes 7s instead of 5s, the next is
  delayed slightly, no duplicate alerts.

Limitations encoded here:
  - Dwell rules: not evaluated. Logged as "skipped: dwell needs Step 8".
  - Position resolution: a camera's marker position IS the position
    used for all its detections. Documented coarse approximation.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Force-load every ORM model so SQLAlchemy can resolve string-referenced
# relationships when this worker process boots. See tasks.py for the
# full rationale; the short version: without this, mapper initialization
# fails for any model with a forward-reference to one not in our local
# import graph.
from app.core import models as _models  # noqa: F401

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.modules.alerts.evaluator import (
    evaluate_entry_rule,
    evaluate_occupancy_rule,
)
from app.modules.alerts.schedule import is_rule_active_now
from app.modules.alerts.schemas import AlertCreate
from app.modules.alerts.service import create_alert
from app.modules.alerts.track_state import (
    drain_tracks_stream,
    get_active_track_count,
    load_prev_zone_count,
    load_rule_state,
    save_prev_zone_count,
    save_rule_state,
)
from app.modules.floor_plans.models import FloorPlan
from app.modules.floor_plans.zones_math import point_in_polygon
from app.modules.tenants.models import Tenant
from app.workers.celery_app import celery_app


log = get_logger("workers.alerts_tasks")


@celery_app.task(name="vt.alerts.evaluate", bind=True)
def evaluate_alerts_task(self):
    """Beat entrypoint. Runs every 5 seconds."""
    try:
        from datetime import datetime, timezone

        now_utc = datetime.now(timezone.utc)
        now_ms = int(now_utc.timestamp() * 1000)
        result = asyncio.run(_evaluate_all_tenants(now_utc=now_utc, now_ms=now_ms))
        log.info(
            "alerts.evaluation_completed",
            task_id=self.request.id,
            **result,
        )
        return result
    except Exception as e:
        log.warning("alerts.evaluation_failed", task_id=self.request.id, error=str(e))
        return {"error": str(e)}


async def _evaluate_all_tenants(*, now_utc, now_ms: int) -> dict[str, int]:
    """One full evaluation pass across every active tenant."""
    counts = {
        "tenants_evaluated": 0,
        "plans_evaluated": 0,
        "zones_evaluated": 0,
        "rules_evaluated": 0,
        "alerts_fired": 0,
        "stream_entries_processed": 0,
        "dwell_rules_skipped": 0,
    }

    # One Redis client per tick (cheap, NullPool pattern matches DB).
    r = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    # Per-tenant accumulator for fired-alert payloads. We publish AFTER
    # the DB commit succeeds — otherwise we'd push ghost alerts to
    # operators that never make it to the audit log.
    fired_per_tenant: dict[str, list[dict]] = {}
    try:
        async with AsyncSessionLocal() as db:
            tenants = await _load_active_tenants(db)
            for tenant in tenants:
                counts["tenants_evaluated"] += 1
                t_result = await _evaluate_tenant(
                    db=db, r=r, tenant=tenant, now_utc=now_utc, now_ms=now_ms
                )
                # _evaluate_tenant may return (counts, fired_payloads)
                # in the patched version, or just counts in the original.
                # Support both for graceful upgrades.
                if isinstance(t_result, tuple):
                    t_counts, t_fired = t_result
                    if t_fired:
                        fired_per_tenant[str(tenant.id)] = t_fired
                else:
                    t_counts = t_result
                for k, v in t_counts.items():
                    counts[k] = counts.get(k, 0) + v
            # All tenant evaluations done — commit any inserted alerts.
            await db.commit()

        # Now that the DB commit landed, publish each fired alert via
        # Redis pub/sub. The FastAPI bridge picks these up and forwards
        # to connected Socket.IO clients. Best-effort: a publish failure
        # doesn't undo the DB row — operators will still see it via the
        # next REST list call.
        for tenant_id, alerts in fired_per_tenant.items():
            for alert_payload in alerts:
                try:
                    await r.publish(
                        f"vt:alerts:{tenant_id}",
                        json.dumps({"kind": "fired", "alert": alert_payload}),
                    )
                except Exception as e:
                    log.warning(
                        "alerts.publish_failed",
                        tenant_id=tenant_id,
                        alert_id=alert_payload.get("id"),
                        error=str(e),
                    )
    finally:
        await r.aclose()

    return counts


async def _load_active_tenants(db: AsyncSession) -> list[Tenant]:
    result = await db.execute(select(Tenant).where(Tenant.is_active == True))
    return list(result.scalars().all())


async def _evaluate_tenant(
    *,
    db: AsyncSession,
    r: redis.Redis,
    tenant: Tenant,
    now_utc,
    now_ms: int,
) -> dict[str, int]:
    """Evaluate all rules in all zones across all plans for one tenant."""
    counts = {
        "plans_evaluated": 0,
        "zones_evaluated": 0,
        "rules_evaluated": 0,
        "alerts_fired": 0,
        "stream_entries_processed": 0,
        "dwell_rules_skipped": 0,
    }

    # 1) Drain new track events into Redis presence state.
    processed = await drain_tracks_stream(r, tenant.id, now_ms)
    counts["stream_entries_processed"] = processed

    # 2) Load all floor plans for this tenant. Zones live as JSONB on
    #    these rows. Each plan also carries `markers` we need for
    #    camera-position lookup.
    plans_result = await db.execute(
        select(FloorPlan).where(FloorPlan.tenant_id == tenant.id)
    )
    plans = list(plans_result.scalars().all())

    for plan in plans:
        if not plan.zones:
            continue  # plan has no zones → nothing to evaluate
        counts["plans_evaluated"] += 1

        # Build a quick lookup of (camera_id → marker) for this plan.
        markers_by_camera: dict[str, dict[str, Any]] = {}
        for m in plan.markers or []:
            cam_id = m.get("camera_id")
            if cam_id:
                markers_by_camera[str(cam_id)] = m

        for zone in plan.zones:
            counts["zones_evaluated"] += 1
            zone_id = str(zone.get("id"))
            zone_name = zone.get("name", "Zone")
            polygon = [
                (float(p["x"]), float(p["y"]))
                for p in (zone.get("polygon") or [])
            ]
            if len(polygon) < 3:
                # Defensive — shouldn't happen given schema validation
                continue

            # 3) Compute current occupancy: which cameras' markers lie
            #    inside this polygon, and how many active tracks each has.
            #    Documented limitation: per-camera count is a proxy for
            #    "people in zone" (no homography until Step 8).
            cameras_in_zone: list[tuple[str, int]] = []
            total_count = 0
            for cam_id, marker in markers_by_camera.items():
                mx = float(marker.get("x", 0.0))
                my = float(marker.get("y", 0.0))
                if not point_in_polygon((mx, my), polygon):
                    continue
                cam_count = await get_active_track_count(
                    r, tenant.id, cam_id, now_ms
                )
                cameras_in_zone.append((cam_id, cam_count))
                total_count += cam_count

            # 4) Evaluate each rule on this zone
            rules = zone.get("rules") or []
            prev_count = await load_prev_zone_count(r, tenant.id, zone_id)
            for rule in rules:
                counts["rules_evaluated"] += 1
                if not rule.get("enabled", True):
                    continue
                kind = rule.get("kind")
                if kind == "dwell":
                    counts["dwell_rules_skipped"] += 1
                    continue
                if not is_rule_active_now(rule.get("schedule"), tenant.timezone, now_utc):
                    continue

                rule_id = str(rule["id"])
                state = await load_rule_state(r, tenant.id, zone_id, rule_id)
                threshold = float(rule.get("threshold", 0))
                hold_time_s = int(rule.get("hold_time_s", 0))

                if kind in ("occupancy_max", "occupancy_min"):
                    outcome = evaluate_occupancy_rule(
                        kind=kind,
                        threshold=threshold,
                        hold_time_s=hold_time_s,
                        current_count=total_count,
                        state=state,
                        now_ms=now_ms,
                    )
                elif kind == "entry":
                    outcome = evaluate_entry_rule(
                        threshold=threshold,
                        prev_count=prev_count,
                        current_count=total_count,
                        state=state,
                        now_ms=now_ms,
                    )
                else:
                    log.warning("alerts.unknown_rule_kind", kind=kind)
                    continue

                await save_rule_state(r, tenant.id, zone_id, rule_id, outcome.new_state)

                if outcome.fire:
                    counts["alerts_fired"] += 1
                    await create_alert(
                        db,
                        AlertCreate(
                            tenant_id=tenant.id,
                            plan_id=plan.id,
                            zone_id=UUID(zone_id),
                            zone_name=zone_name,
                            rule_id=UUID(rule_id),
                            rule_kind=kind,
                            rule_label=rule.get("label"),
                            severity=rule.get("severity", "warning"),
                            condition_value=float(total_count),
                            threshold=threshold,
                            channels_attempted=["in_app"],  # Batch F adds more
                            extra={
                                "cameras_in_zone": [
                                    {"camera_id": c, "count": n}
                                    for c, n in cameras_in_zone
                                ],
                                "reason": outcome.reason,
                            },
                        ),
                    )
                    log.info(
                        "alerts.fired",
                        tenant_id=str(tenant.id),
                        zone=zone_name,
                        rule_kind=kind,
                        count=total_count,
                        threshold=threshold,
                    )

            # Persist the count for the NEXT tick's entry-rule edge
            # comparison. Done once per zone, after all rules on it.
            await save_prev_zone_count(r, tenant.id, zone_id, total_count)

    return counts
