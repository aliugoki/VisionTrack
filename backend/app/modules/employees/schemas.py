"""Pydantic schemas for the employees module."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EmployeeRow(BaseModel):
    id: str
    emp_id: str
    name: str
    external_company_id: str | None = None
    source: str
    synced_at: datetime | None = None
    seen: bool  # has this employee been recognized in VisionTrack (person_identities)?


class EmployeeListResponse(BaseModel):
    total: int
    rows: list[EmployeeRow]
