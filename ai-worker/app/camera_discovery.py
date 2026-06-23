"""Camera discovery.

The AI worker doesn't have direct DB access — it discovers cameras by
calling the backend's REST API every N seconds. Only cameras whose
status is "online" are picked up; offline / pending / error / disabled
cameras are skipped (we'd just burn CPU trying to read empty RTSP).

The worker authenticates as the seeded `ai-worker@system` service
account using a long-lived JWT.
"""

from dataclasses import dataclass
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import get_logger

log = get_logger("discovery")


@dataclass(frozen=True)
class DiscoveredCamera:
    """Minimal camera info needed to start a pipeline."""
    id: UUID
    tenant_id: UUID
    name: str
    mediamtx_path: str
    rtsp_url: str  # Computed from MEDIAMTX_RTSP_BASE + mediamtx_path

    @property
    def task_key(self) -> str:
        """Stable key used to track running pipeline tasks."""
        return str(self.id)


class CameraDiscovery:
    """Polls the backend for cameras the worker should be tracking."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.BACKEND_URL,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=10.0,
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_active_cameras(self) -> list[DiscoveredCamera]:
        """Return every ONLINE camera across every tenant.

        The backend's GET /cameras endpoint is scoped to the calling
        user's tenant. The ai-worker service account is multi-tenant
        capable — see the backend's deps.py: when the caller has the
        `tenant:read_all` permission, the tenant scope is bypassed.
        """
        if self._client is None:
            return []

        try:
            r = await self._client.get(
                "/api/v1/cameras", params={"status": "online"}
            )
        except httpx.HTTPError as e:
            log.warning("discovery.fetch_failed", error=str(e))
            return []

        if r.status_code != 200:
            log.warning(
                "discovery.fetch_non_200",
                status=r.status_code,
                body=r.text[:200],
            )
            return []

        try:
            data = r.json()
        except ValueError:
            log.warning("discovery.invalid_json", body=r.text[:200])
            return []

        cameras: list[DiscoveredCamera] = []
        for c in data:
            try:
                path = c["mediamtx_path"]
                rtsp = f"{settings.MEDIAMTX_RTSP_BASE.rstrip('/')}/{path}"
                cameras.append(
                    DiscoveredCamera(
                        id=UUID(c["id"]),
                        tenant_id=UUID(c["tenant_id"]),
                        name=c["name"],
                        mediamtx_path=path,
                        rtsp_url=rtsp,
                    )
                )
            except (KeyError, ValueError) as e:
                log.warning(
                    "discovery.malformed_camera",
                    error=str(e),
                    camera=c.get("id"),
                )
                continue

        return cameras
