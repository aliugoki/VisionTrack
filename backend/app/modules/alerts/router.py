"""Alerts REST endpoints.

  GET  /alerts                 — list with filters + pagination
  GET  /alerts/{id}            — single alert detail
  POST /alerts/{id}/acknowledge
  POST /alerts/{id}/resolve

Authorization: GET requires alert:read; acknowledge requires
alert:acknowledge; resolve requires alert:resolve. Tenant scoping is
enforced in the service layer — every query is filtered by
current_user.tenant_id; no code path queries across tenants.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import RequirePermission
from app.core.permissions import (
    ALERT_ACKNOWLEDGE,
    ALERT_READ,
    ALERT_RESOLVE,
)
from app.modules.alerts.schemas import AlertListResponse, AlertRead
from app.modules.alerts.service import (
    acknowledge_alert,
    get_alert,
    list_alerts,
    resolve_alert,
)
from app.modules.users.models import User


router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts_endpoint(
    status_filter: Literal["active", "acknowledged", "resolved"] | None = Query(
        None, alias="status"
    ),
    severity: Literal["info", "warning", "critical"] | None = Query(None),
    zone_id: UUID | None = Query(None),
    since: datetime | None = Query(
        None,
        description="Return alerts fired AFTER this timestamp (ISO 8601).",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(RequirePermission(ALERT_READ)),
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """List alerts for the current tenant, newest-first.

    Filters are AND-combined. `since` is used by the WebSocket
    reconnect catch-up path to fetch any alerts missed during disconnect.
    """
    items, total = await list_alerts(
        db,
        tenant_id=current_user.tenant_id,
        status=status_filter,
        severity=severity,
        zone_id=zone_id,
        since=since,
        limit=limit,
        offset=offset,
    )
    return AlertListResponse(
        items=[AlertRead.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert_endpoint(
    alert_id: UUID,
    current_user: User = Depends(RequirePermission(ALERT_READ)),
    db: AsyncSession = Depends(get_db),
) -> AlertRead:
    alert = await get_alert(db, tenant_id=current_user.tenant_id, alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertRead.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert_endpoint(
    alert_id: UUID,
    current_user: User = Depends(RequirePermission(ALERT_ACKNOWLEDGE)),
    db: AsyncSession = Depends(get_db),
) -> AlertRead:
    """Mark alert as acknowledged.

    Acknowledgment indicates an operator has SEEN the alert (vs resolve,
    which indicates the situation is handled). Status transition:
      active → acknowledged
    Re-acknowledgment is a no-op (returns current state, doesn't error).
    """
    alert = await acknowledge_alert(
        db,
        tenant_id=current_user.tenant_id,
        alert_id=alert_id,
        user_id=current_user.id,
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.commit()
    return AlertRead.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert_endpoint(
    alert_id: UUID,
    current_user: User = Depends(RequirePermission(ALERT_RESOLVE)),
    db: AsyncSession = Depends(get_db),
) -> AlertRead:
    """Mark alert as resolved.

    Resolution can happen from any status (active or acknowledged). Once
    resolved, an alert is read-only — no further status transitions.
    """
    alert = await resolve_alert(
        db,
        tenant_id=current_user.tenant_id,
        alert_id=alert_id,
        user_id=current_user.id,
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.commit()
    return AlertRead.model_validate(alert)
