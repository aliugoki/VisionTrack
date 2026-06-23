"""ONVIF camera discovery via WS-Discovery.

WS-Discovery sends a SOAP-over-UDP multicast probe to 239.255.255.250:3702.
ONVIF-compliant devices respond with their `XAddrs` — the URL of their
ONVIF device service. We then call GetDeviceInformation (and optionally
GetStreamUri) to enrich each result with manufacturer/model/RTSP URL.

Network requirements (important for the user to know):
  - The backend container must be on the same L2 broadcast domain as the
    cameras. Docker's default bridge network does NOT see LAN multicast.
    For ONVIF discovery to work, the backend should be run in `network_mode: host`
    OR the user should run discovery from a separate host-network container.
  - We design discovery as a separate endpoint that returns results to the
    client; the client decides which devices to add. We DO NOT auto-create
    cameras from discovery — too easy to add the wrong device or duplicate
    existing ones.

Library choice:
  - `wsdiscovery` (pure Python) for the probe — simple, sync, well-maintained.
  - `onvif-zeep-async` for follow-up GetDeviceInformation calls (async, works
    inside FastAPI without thread offloading).

If discovery fails entirely (e.g. running in a bridge network where multicast
doesn't reach cameras), we return an empty list with a structured warning
rather than crashing.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.modules.cameras.schemas import CameraDiscoveryResult

log = get_logger("cameras.onvif")


async def discover_cameras(
    timeout_seconds: int = 5,
    username: str | None = None,
    password: str | None = None,
) -> list[CameraDiscoveryResult]:
    """Run WS-Discovery and enrich results with ONVIF device info.

    Returns an empty list if discovery is unavailable in this environment
    (e.g. container without host networking). Errors are logged, not raised.
    """
    try:
        # Heavy imports are inside the function so the backend boots even if
        # these libs aren't installed (graceful degradation).
        from wsdiscovery import QName  # noqa: F401
        from wsdiscovery.discovery import ThreadedWSDiscovery
    except ImportError:
        log.warning("onvif.wsdiscovery_not_installed")
        return []

    # WS-Discovery is sync + threaded — run it in a thread pool so we
    # don't block the event loop.
    def _probe() -> list[dict[str, Any]]:
        wsd = ThreadedWSDiscovery()
        wsd.start()
        try:
            services = wsd.searchServices(timeout=timeout_seconds)
            results: list[dict[str, Any]] = []
            for svc in services:
                xaddrs = list(svc.getXAddrs())
                if not xaddrs:
                    continue
                results.append(
                    {
                        "xaddr": xaddrs[0],
                        "types": [str(t) for t in svc.getTypes()],
                        "scopes": [str(s) for s in svc.getScopes()],
                    }
                )
            return results
        finally:
            try:
                wsd.stop()
            except Exception:
                pass

    try:
        raw_results = await asyncio.to_thread(_probe)
    except Exception as e:
        log.warning("onvif.wsdiscovery_failed", error=str(e))
        return []

    log.info("onvif.discovered_raw", count=len(raw_results))

    # Enrich each result in parallel
    enriched_tasks = [
        _enrich_device(r, username, password) for r in raw_results
    ]
    enriched = await asyncio.gather(*enriched_tasks, return_exceptions=True)

    final: list[CameraDiscoveryResult] = []
    for item in enriched:
        if isinstance(item, CameraDiscoveryResult):
            final.append(item)
    return final


async def _enrich_device(
    raw: dict[str, Any],
    username: str | None,
    password: str | None,
) -> CameraDiscoveryResult | None:
    """Call GetDeviceInformation / GetStreamUri to fill out device details."""
    xaddr = raw["xaddr"]
    parsed = urlparse(xaddr)
    ip = parsed.hostname or ""
    port = parsed.port or 80

    result = CameraDiscoveryResult(
        ip=ip,
        port=port,
        xaddr=xaddr,
        manufacturer=_extract_scope(raw.get("scopes", []), "name"),
        model=_extract_scope(raw.get("scopes", []), "hardware"),
    )

    # If credentials given, try ONVIF GetDeviceInformation + GetStreamUri.
    # Without credentials, most cameras reject these calls — that's fine,
    # we still return the IP and let the user fill in the RTSP URL manually.
    if not username or not password:
        return result

    try:
        from onvif import ONVIFCamera  # provided by onvif-zeep-async
    except ImportError:
        log.warning("onvif.client_not_installed")
        return result

    try:
        cam = ONVIFCamera(ip, port, username, password)
        await cam.update_xaddrs()
        device_info = await cam.devicemgmt.GetDeviceInformation()
        result.manufacturer = (
            getattr(device_info, "Manufacturer", None) or result.manufacturer
        )
        result.model = getattr(device_info, "Model", None) or result.model
        result.serial = getattr(device_info, "SerialNumber", None)

        media = await cam.create_media_service()
        profiles = await media.GetProfiles()
        if profiles:
            uri_req = media.create_type("GetStreamUri")
            uri_req.ProfileToken = profiles[0].token
            uri_req.StreamSetup = {
                "Stream": "RTP-Unicast",
                "Transport": {"Protocol": "RTSP"},
            }
            uri = await media.GetStreamUri(uri_req)
            result.suggested_rtsp_url = uri.Uri
    except Exception as e:
        log.info(
            "onvif.enrich_failed", ip=ip, error=str(e)[:200]
        )

    return result


def _extract_scope(scopes: list[str], key: str) -> str | None:
    """Extract a value from ONVIF scopes like 'onvif://www.onvif.org/name/AcmeCam'."""
    needle = f"/{key}/"
    for s in scopes:
        idx = s.find(needle)
        if idx >= 0:
            value = s[idx + len(needle):]
            # URL-decode common escapes
            return value.replace("%20", " ").strip() or None
    return None
