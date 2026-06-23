"""Socket.IO server.

One Socket.IO room per tenant. Connected clients receive every track
update from every camera in their tenant, at the full 10 fps cadence
(no sampling — the sampling happens before persistence, but Socket.IO
broadcasts everything).

Authentication:
  Clients pass a JWT as the `auth` payload in the Socket.IO handshake:

    const socket = io({
      auth: { token: localStorage.getItem('vt_token') }
    });

  The token is the same JWT used for REST API auth. We decode it and
  resolve the user's tenant to pick the room.

Why rooms instead of namespaces?
  Namespaces require explicit URL paths from the client which complicates
  the Vite proxy setup. Rooms are dynamic and don't require client URL
  changes when tenants are added/removed.

This module exposes:
  - `sio`: the AsyncServer instance
  - `socket_app`: an ASGI app mounted by main.py at /socket.io
  - `broadcast_to_tenant(tenant_id, event_name, data)`: the publish helper
    used by the Redis consumer
"""

from uuid import UUID

import socketio
from jose import JWTError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import decode_token

log = get_logger("realtime.socketio")


sio = socketio.AsyncServer(
    async_mode="asgi",
    # We share an HTTP server with FastAPI via ASGI; CORS for the WS
    # handshake itself is handled here rather than by the FastAPI middleware.
    cors_allowed_origins="*",
    # Trade some latency for fewer dropped frames over flaky cell networks.
    ping_interval=25,
    ping_timeout=20,
    logger=False,
    engineio_logger=False,
)

# ASGI sub-app that FastAPI mounts at /socket.io
socket_app = socketio.ASGIApp(sio, socketio_path="socket.io")


def _room_for_tenant(tenant_id: UUID | str) -> str:
    return f"tenant:{tenant_id}"


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None):
    """Validate JWT, join the client to their tenant's room.

    On failure we raise ConnectionRefusedError which Socket.IO translates
    into a clean disconnect with a reason. The client should react by
    refreshing the token and reconnecting.
    """
    if not auth or not auth.get("token"):
        log.info("socketio.connect_rejected", sid=sid, reason="no_token")
        raise socketio.exceptions.ConnectionRefusedError("missing token")

    token = auth["token"]
    try:
        payload = decode_token(token)
    except JWTError:
        log.info("socketio.connect_rejected", sid=sid, reason="invalid_token")
        raise socketio.exceptions.ConnectionRefusedError("invalid token")

    if payload.get("typ") != "access":
        raise socketio.exceptions.ConnectionRefusedError("wrong token type")

    tenant_id = payload.get("tid")
    user_id = payload.get("sub")
    if not tenant_id or not user_id:
        raise socketio.exceptions.ConnectionRefusedError("malformed token")

    room = _room_for_tenant(tenant_id)
    await sio.enter_room(sid, room)

    # Save the user/tenant on the session so disconnect handlers can log it.
    await sio.save_session(sid, {"user_id": user_id, "tenant_id": tenant_id})

    log.info(
        "socketio.client_connected",
        sid=sid,
        user_id=user_id,
        tenant_id=tenant_id,
        room=room,
    )


@sio.event
async def disconnect(sid: str):
    try:
        session = await sio.get_session(sid)
    except KeyError:
        session = {}
    log.info(
        "socketio.client_disconnected",
        sid=sid,
        user_id=session.get("user_id"),
        tenant_id=session.get("tenant_id"),
    )


async def broadcast_to_tenant(
    tenant_id: UUID | str, event_name: str, data: dict
) -> None:
    """Send an event to every client in a tenant's room. No reply expected.

    Called from the Redis consumer for every incoming track event.
    Non-blocking — if no clients are connected, this is essentially a no-op.
    """
    room = _room_for_tenant(tenant_id)
    await sio.emit(event_name, data, room=room)
