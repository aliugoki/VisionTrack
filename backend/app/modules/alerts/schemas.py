"""Alert Pydantic schemas.

Originally Batch C only needed the internal create shape (used by the
evaluator when it inserts a row). Batch E adds the public read/list
shape + the list response envelope used by the REST endpoints.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AlertStatus = Literal["active", "acknowledged", "resolved"]
AlertSeverity = Literal["info", "warning", "critical"]


class AlertCreate(BaseModel):
    """Internal: what the evaluator writes when a rule fires."""
    tenant_id: UUID
    plan_id: UUID
    zone_id: UUID
    zone_name: str = Field(..., max_length=120)
    rule_id: UUID
    rule_kind: str = Field(..., max_length=32)
    rule_label: str | None = Field(default=None, max_length=120)
    severity: AlertSeverity
    condition_value: float
    threshold: float
    channels_attempted: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class AlertRead(BaseModel):
    """Public: what Batch E's feed endpoint returns."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    plan_id: UUID
    zone_id: UUID
    zone_name: str
    rule_id: UUID
    rule_kind: str
    rule_label: str | None
    severity: AlertSeverity
    condition_value: float
    threshold: float
    status: AlertStatus
    fired_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by_user_id: UUID | None
    resolved_at: datetime | None
    resolved_by_user_id: UUID | None
    channels_attempted: list[str]
    extra: dict[str, Any]


class AlertListResponse(BaseModel):
    """Paginated list envelope.

    Pagination is offset-based for simplicity. The list page is sorted
    newest-first by fired_at, so offset works fine even with continuous
    writes — new rows always land at offset=0 and push the rest down.
    Total is the unfiltered match count.
    """
    items: list[AlertRead]
    total: int
    limit: int
    offset: int
