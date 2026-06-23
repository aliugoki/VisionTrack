"""Service-layer helpers for the alerts module.

Functions:
  create_alert           — invoked by the evaluator on fire
  list_alerts            — paginated list with filters (used by REST)
  get_alert              — single alert by id, tenant-scoped
  acknowledge_alert      — status transition; publishes status change
  resolve_alert          — status transition; publishes status change

Tenant scoping: every query takes a tenant_id and filters on it. The
router is responsible for passing current_user.tenant_id; no code path
ever queries across tenants.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.modules.alerts.models import Alert
from app.modules.alerts.schemas import AlertCreate


log = get_logger("alerts.service")


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

async def create_alert(db: AsyncSession, payload: AlertCreate) -> Alert:
    """Insert a new alert row. Caller is responsible for committing.

    The evaluator runs as a Celery task that handles its own session
    boundaries — we don't commit here so multiple alerts in one tick
    can be persisted atomically. After flush() the row has server-side
    columns (fired_at) populated, which the evaluator uses to construct
    the pub/sub payload.
    """
    alert = Alert(
        tenant_id=payload.tenant_id,
        plan_id=payload.plan_id,
        zone_id=payload.zone_id,
        zone_name=payload.zone_name,
        rule_id=payload.rule_id,
        rule_kind=payload.rule_kind,
        rule_label=payload.rule_label,
        severity=payload.severity,
        condition_value=payload.condition_value,
        threshold=payload.threshold,
        channels_attempted=list(payload.channels_attempted),
        extra=dict(payload.extra),
    )
    db.add(alert)
    await db.flush()
    # Refresh to load server defaults (fired_at) before the caller reads
    # them for the pub/sub publish. Without this, fired_at can be None.
    await db.refresh(alert)
    return alert


async def acknowledge_alert(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    alert_id: UUID,
    user_id: UUID,
) -> Alert | None:
    """Mark active → acknowledged. Idempotent on already-ack'd or resolved."""
    alert = await get_alert(db, tenant_id=tenant_id, alert_id=alert_id)
    if alert is None:
        return None
    if alert.status == "active":
        alert.status = "acknowledged"
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by_user_id = user_id
        await db.flush()
        await _publish_status_change(tenant_id, alert, kind="acknowledged")
    return alert


async def resolve_alert(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    alert_id: UUID,
    user_id: UUID,
) -> Alert | None:
    """Mark anything → resolved. Idempotent on already-resolved."""
    alert = await get_alert(db, tenant_id=tenant_id, alert_id=alert_id)
    if alert is None:
        return None
    if alert.status != "resolved":
        alert.status = "resolved"
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by_user_id = user_id
        # If resolving without prior ack, fill ack stamps too — operator
        # implicitly acknowledged by acting on it. Keeps audit complete.
        if alert.acknowledged_at is None:
            alert.acknowledged_at = alert.resolved_at
            alert.acknowledged_by_user_id = user_id
        await db.flush()
        await _publish_status_change(tenant_id, alert, kind="resolved")
    return alert


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

async def get_alert(
    db: AsyncSession, *, tenant_id: UUID, alert_id: UUID
) -> Alert | None:
    result = await db.execute(
        select(Alert).where(Alert.tenant_id == tenant_id, Alert.id == alert_id)
    )
    return result.scalar_one_or_none()


async def list_alerts(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    status: Literal["active", "acknowledged", "resolved"] | None = None,
    severity: Literal["info", "warning", "critical"] | None = None,
    zone_id: UUID | None = None,
    since: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Alert], int]:
    """Newest-first paginated alert list with optional filters.

    Returns (items, total) — total is the unfiltered match count so the
    UI can show "showing 50 of 217".
    """
    base = select(Alert).where(Alert.tenant_id == tenant_id)
    if status is not None:
        base = base.where(Alert.status == status)
    if severity is not None:
        base = base.where(Alert.severity == severity)
    if zone_id is not None:
        base = base.where(Alert.zone_id == zone_id)
    if since is not None:
        base = base.where(Alert.fired_at > since)

    # Count first (separate query is fine — avoids window function complexity
    # and the index ix_alerts_tenant_status_fired covers the dashboard path)
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    items_q = base.order_by(Alert.fired_at.desc()).limit(limit).offset(offset)
    items = list((await db.execute(items_q)).scalars().all())
    return items, total


# ---------------------------------------------------------------------------
# Pub/sub publish (for ack/resolve status broadcasts)
# ---------------------------------------------------------------------------

async def _publish_status_change(
    tenant_id: UUID, alert: Alert, *, kind: str
) -> None:
    """Best-effort publish to Redis pub/sub. Mirrors the evaluator's
    fired-alert publish path — the FastAPI bridge picks it up and emits
    via Socket.IO so other connected operators see the status change live.
    """
    payload = {
        "kind": kind,
        "alert": {
            "id": str(alert.id),
            "tenant_id": str(alert.tenant_id),
            "plan_id": str(alert.plan_id),
            "zone_id": str(alert.zone_id),
            "zone_name": alert.zone_name,
            "rule_id": str(alert.rule_id),
            "rule_kind": alert.rule_kind,
            "rule_label": alert.rule_label,
            "severity": alert.severity,
            "condition_value": alert.condition_value,
            "threshold": alert.threshold,
            "status": alert.status,
            "fired_at": alert.fired_at.isoformat() if alert.fired_at else None,
            "acknowledged_at": (
                alert.acknowledged_at.isoformat()
                if alert.acknowledged_at else None
            ),
            "acknowledged_by_user_id": (
                str(alert.acknowledged_by_user_id)
                if alert.acknowledged_by_user_id else None
            ),
            "resolved_at": (
                alert.resolved_at.isoformat() if alert.resolved_at else None
            ),
            "resolved_by_user_id": (
                str(alert.resolved_by_user_id)
                if alert.resolved_by_user_id else None
            ),
            "channels_attempted": alert.channels_attempted,
            "extra": alert.extra,
        },
    }
    try:
        r = redis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        try:
            await r.publish(f"vt:alerts:{tenant_id}", json.dumps(payload))
        finally:
            await r.aclose()
    except Exception as e:
        # Don't fail the HTTP request if pub/sub publish fails. The DB
        # state is the source of truth; live broadcast is a nice-to-have.
        log.warning(
            "alerts.publish_status_failed",
            tenant_id=str(tenant_id),
            alert_id=str(alert.id),
            kind=kind,
            error=str(e),
        )
