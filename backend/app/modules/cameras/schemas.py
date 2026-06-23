"""Pydantic schemas for the cameras module.

The interesting bits:
  - RTSP URL is validated to start with rtsp:// or rtsps://
  - On read, we synthesize the browser-facing HLS URL from the MediaMTX
    public address (settings.MEDIAMTX_HLS_URL) + the mediamtx_path
  - We never echo the rtsp_url credentials back to the frontend if they
    contain a password (it shows as "rtsp://user:****@host/...")
"""

from datetime import datetime
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.config import settings
from app.modules.cameras.models import CameraStatus


def _mask_rtsp_password(rtsp_url: str) -> str:
    """Replace any password in the URL with **** for display."""
    try:
        p = urlparse(rtsp_url)
        if p.password is None:
            return rtsp_url
        # Rebuild netloc with masked password
        username = p.username or ""
        host = p.hostname or ""
        port = f":{p.port}" if p.port else ""
        netloc = f"{username}:****@{host}{port}"
        return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        return rtsp_url


class CameraBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str | None = Field(None, max_length=500)
    site_id: UUID
    rtsp_url: str = Field(..., min_length=10, max_length=2048)
    is_recording: bool = True

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("rtsp://") or v.startswith("rtsps://")):
            raise ValueError("rtsp_url must start with rtsp:// or rtsps://")
        # Basic structural check
        try:
            parsed = urlparse(v)
            if not parsed.hostname:
                raise ValueError("rtsp_url must include a host")
        except Exception as e:
            raise ValueError(f"invalid RTSP URL: {e}")
        return v


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    description: str | None = Field(None, max_length=500)
    rtsp_url: str | None = Field(None, min_length=10, max_length=2048)
    is_recording: bool | None = None
    calibration: dict[str, Any] | None = None

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return CameraBase.validate_rtsp_url(v)


class CameraCalibration(BaseModel):
    """Bird's-Eye-View homography for a camera.

    Maps a point in the camera's source-pixel image space to fractional
    coordinates (0..1) on a floor plan, so live track foot-points can be
    projected onto a top-down view. The 3x3 homography is supplied row-major
    as 9 floats (computed client-side from 4 point correspondences). We keep
    the source/destination points so the calibration can be re-edited.
    """
    floor_plan_id: UUID
    # Row-major 3x3 homography (image px -> floor-plan fractional 0..1).
    homography: list[float] = Field(..., min_length=9, max_length=9)
    # Pixel dimensions of the image the src_points were picked on — the same
    # source space track bboxes live in. Lets the UI re-render correspondences.
    image_ref: dict[str, int] = Field(..., description='{"width": W, "height": H}')
    # The 4 (or more) correspondences, for re-editing the calibration.
    src_points: list[list[float]] = Field(..., min_length=4)
    dst_points: list[list[float]] = Field(..., min_length=4)

    @field_validator("homography")
    @classmethod
    def _finite_homography(cls, v: list[float]) -> list[float]:
        if any((x != x or x in (float("inf"), float("-inf"))) for x in v):
            raise ValueError("homography contains non-finite values")
        return v

    @field_validator("src_points", "dst_points")
    @classmethod
    def _pairs(cls, v: list[list[float]]) -> list[list[float]]:
        if any(len(p) != 2 for p in v):
            raise ValueError("each point must be an [x, y] pair")
        return v


class FloorPlanLocation(BaseModel):
    """One placement of this camera on a floor plan.

    Used by the cameras list to show 'this camera is on N floor plans'
    badges, with click-through to the plan + marker pre-selected.
    """
    plan_id: UUID
    plan_name: str
    marker_id: UUID
    marker_label: str | None = None


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    site_id: UUID
    name: str
    description: str | None
    rtsp_url: str  # masked in the @field_serializer below
    mediamtx_path: str
    status: CameraStatus
    is_recording: bool
    codec: str | None = None
    last_seen_at: datetime | None
    last_status_change_at: datetime | None
    calibration: dict[str, Any]
    stream_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    # Populated by the router when listing cameras; empty by default so
    # single-camera fetches that don't go through the enrichment path
    # still serialize successfully.
    floor_plan_locations: list[FloorPlanLocation] = Field(default_factory=list)

    @field_validator("rtsp_url", mode="before")
    @classmethod
    def mask_password(cls, v: str) -> str:
        return _mask_rtsp_password(v)

    @computed_field
    @property
    def hls_url(self) -> str:
        """Browser-playable HLS URL.

        For H.265 cameras we route the browser to the `-h264` sibling
        path created by the GPU transcoder, since Chrome/Firefox cannot
        play H.265 HLS. The AI worker still reads from the original
        `mediamtx_path` (H.265 directly, no double-decode cost).

        Codec is detected by the health-check task within ~30 seconds of
        a camera coming online. Until codec is known, we point to the
        raw path — that's a safe default and the URL will switch on the
        next refresh once detection completes.
        """
        base = settings.MEDIAMTX_HLS_URL.rstrip("/")
        path = self.mediamtx_path
        if self.codec == "H265":
            path = f"{self.mediamtx_path}-h264"
        return f"{base}/{path}/index.m3u8"


class CameraDiscoveryResult(BaseModel):
    """One discovered ONVIF camera on the LAN."""
    ip: str
    port: int = 80
    manufacturer: str | None = None
    model: str | None = None
    serial: str | None = None
    suggested_rtsp_url: str | None = None
    xaddr: str  # the ONVIF service XAddr returned by WS-Discovery


class CameraDiscoveryRequest(BaseModel):
    """Optional credentials to attempt RTSP URL retrieval from each device."""
    username: str | None = None
    password: str | None = None
    timeout_seconds: int = Field(5, ge=1, le=30)
