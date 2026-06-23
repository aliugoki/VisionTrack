"""Camera model.

Every camera belongs to exactly one Site (which belongs to a Tenant).
The `rtsp_url` is the camera's stream endpoint — we store it as-is and
push it to MediaMTX as a `source` for that camera's path.

Status is updated by the health check background task every ~30s.

`calibration` is reserved for Phase 3 (MV3DT): it'll store the homography
matrix that maps pixel coords -> floor-plan world coords. JSONB now so the
column doesn't need to change later.

`mediamtx_path` is the path name we register with MediaMTX; for new
cameras it's typically `cam-{short_id}`. Storing it explicitly (rather
than deriving from the camera id) lets operators rename a camera in
MediaMTX for reasons we can't anticipate.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Index,
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CameraStatus(str, Enum):
    """Last-known camera connectivity, updated by health check task."""
    PENDING = "pending"      # newly created, never probed
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"          # MediaMTX reports the source as failed
    DISABLED = "disabled"    # admin-disabled, health checks skipped


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_cameras_tenant_name"),
        UniqueConstraint("mediamtx_path", name="uq_cameras_mediamtx_path"),
        Index("ix_cameras_codec", "codec"),
        Index("ix_cameras_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rtsp_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    mediamtx_path: Mapped[str] = mapped_column(String(120), nullable=False)

    status: Mapped[CameraStatus] = mapped_column(
        String(20), default=CameraStatus.PENDING.value, nullable=False
    )
    is_recording: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Video codec of the source RTSP stream — populated by the health
    # check task by querying MediaMTX after first successful pull.
    # H265 sources need an NVENC-transcoded -h264 sibling for browser playback.
    codec: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Reserved for Phase 3 — pixel-to-world homography, intrinsics, lens model
    calibration: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    # Stream configuration (resolution, fps, codec hints) — populated by health probe
    stream_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    site: Mapped["Site"] = relationship(back_populates="cameras")  # type: ignore  # noqa: F821
