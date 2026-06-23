"""Async client for the MediaMTX control API.

MediaMTX exposes its config via REST at /v3/config/paths/{add,patch,delete}/{name}.
We use it to register each VisionTrack camera as a "path" with `source = <rtsp_url>`,
which causes MediaMTX to pull that RTSP source and republish it as HLS.

Reference: https://github.com/bluenviron/mediamtx/blob/main/apidocs/openapi.yaml

Design notes:
  - All methods are idempotent where possible: add_path catches "already exists"
    and patches instead. delete_path returns silently if the path is already gone.
  - We log every call so failures are diagnosable from `docker compose logs backend`.
  - The client doesn't raise on MediaMTX errors except for outright network failure
    — instead it returns a structured result so the calling service can decide
    whether a sync failure should block the DB write. (Usually it shouldn't:
    the camera exists in our DB regardless of MediaMTX state, and a background
    reconciler can re-sync.)
"""

from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("cameras.mediamtx")


class MediaMTXClient:
    """Stateless async client. Safe to instantiate per request."""

    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        self.base_url = (base_url or settings.MEDIAMTX_API_URL).rstrip("/")
        self.timeout = timeout

    # -- Internals -------------------------------------------------------------
    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any] | None]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(method, url, json=json)
            body: dict[str, Any] | None = None
            if resp.content:
                try:
                    body = resp.json()
                except ValueError:
                    body = {"raw": resp.text}
            return resp.status_code, body
        except httpx.HTTPError as e:
            log.error("mediamtx.http_error", method=method, path=path, error=str(e))
            return 0, {"error": str(e)}

    # -- Public API ------------------------------------------------------------
    async def add_path(self, name: str, rtsp_source: str, record: bool = True) -> bool:
        """Add a path to MediaMTX. If it exists, patch it instead.

        Returns True on success, False on failure (logged).
        """
        payload = {
            "source": rtsp_source,
            "sourceOnDemand": False,
            "record": record,
            # Use TCP for RTSP transport — far more reliable than UDP over WAN
            # and uniformly supported by IP cameras.
            "rtspTransport": "tcp",
        }
        status, body = await self._request(
            "POST", f"/v3/config/paths/add/{name}", payload
        )

        if status in (200, 201):
            log.info("mediamtx.path_added", path=name, source=_redact(rtsp_source))
            return True

        # 400 with "path already exists" -> fall through to patch
        if status == 400 and body and "already" in str(body).lower():
            log.info("mediamtx.path_exists_patching", path=name)
            return await self.patch_path(name, rtsp_source, record)

        log.warning(
            "mediamtx.add_failed", path=name, status=status, body=body
        )
        return False

    async def patch_path(self, name: str, rtsp_source: str, record: bool = True) -> bool:
        payload = {
            "source": rtsp_source,
            "sourceOnDemand": False,
            "record": record,
            "rtspTransport": "tcp",
        }
        status, body = await self._request(
            "PATCH", f"/v3/config/paths/patch/{name}", payload
        )
        if status in (200, 201):
            log.info("mediamtx.path_patched", path=name)
            return True
        log.warning(
            "mediamtx.patch_failed", path=name, status=status, body=body
        )
        return False

    async def delete_path(self, name: str) -> bool:
        """Remove a path. Returns True if deleted or already absent."""
        status, body = await self._request("DELETE", f"/v3/config/paths/delete/{name}")
        if status in (200, 204):
            log.info("mediamtx.path_deleted", path=name)
            return True
        if status == 404:
            log.info("mediamtx.path_already_absent", path=name)
            return True
        log.warning(
            "mediamtx.delete_failed", path=name, status=status, body=body
        )
        return False

    async def get_path_runtime(self, name: str) -> dict[str, Any] | None:
        """Return the runtime state of a path (ready / not ready, source readers, etc.).

        Used by the health-check task to determine ONLINE vs OFFLINE vs ERROR.
        """
        status, body = await self._request("GET", f"/v3/paths/get/{name}")
        if status == 200 and body:
            return body
        if status == 404:
            return None
        log.warning("mediamtx.get_failed", path=name, status=status)
        return None

    async def list_paths(self) -> list[dict[str, Any]]:
        """Return the runtime state of every active path in one call.

        The health-check task builds a {name: path_state} map from this to
        evaluate all cameras per tick (ready / readers / source) without a
        round-trip per camera. Returns [] on failure (the task then treats
        cameras as not-ready for that tick rather than crashing).
        """
        status, body = await self._request("GET", "/v3/paths/list")
        if status == 200 and body:
            items = body.get("items")
            if isinstance(items, list):
                return items
        log.warning("mediamtx.list_failed", status=status)
        return []


def _redact(rtsp_url: str) -> str:
    """Best-effort password redaction for log output."""
    if "@" not in rtsp_url:
        return rtsp_url
    scheme_split = rtsp_url.split("://", 1)
    if len(scheme_split) != 2:
        return rtsp_url
    scheme, rest = scheme_split
    if "@" not in rest:
        return rtsp_url
    creds, host_part = rest.rsplit("@", 1)
    if ":" in creds:
        user, _ = creds.split(":", 1)
        return f"{scheme}://{user}:****@{host_part}"
    return rtsp_url
