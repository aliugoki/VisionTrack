"""Hotfix patch: append add_transcode_path method to MediaMTXClient.

This is applied as a separate file rather than directly editing
mediamtx_client.py so it's easy to identify what changed from the
checkpoint state. The method is monkey-patched onto MediaMTXClient
via an import-side-effect block in app/modules/cameras/__init__.py.

Why add_transcode_path exists:
  IP cameras typically output H.265 (HEVC) for bandwidth efficiency.
  Browsers can't reliably play H.265 in HLS (Safari can, Chrome/Firefox
  can't). We solve this by creating a SECOND MediaMTX path that runs
  ffmpeg to transcode H.265 -> H.264, which all browsers can play.

  The browser's Live Wall component requests:
    /hls/<camera_path>-h264/index.m3u8
  which serves HLS segments from the ffmpeg-published transcode.

Why runOnInit, not runOnDemand:
  We initially tried `runOnDemand` (launch ffmpeg lazily when a reader
  arrives) but this didn't work with HLS readers in MediaMTX 1.9.3 -
  HLS doesn't trigger the on-demand pattern, only RTSP/RTMP reads do.
  So with runOnDemand, HLS requests returned 404 indefinitely.

  Switching to `runOnInit` makes MediaMTX start ffmpeg as soon as the
  path is registered. ffmpeg keeps the transcode running continuously.
  Cost is ~1 small ffmpeg process per H.265 camera. With libx264
  ultrafast at 720p that's roughly 5-10% of a CPU core per camera -
  reasonable for current scale, easy to switch to nvenc later.
"""

from app.modules.cameras.mediamtx_client import MediaMTXClient
from app.core.logging import get_logger


log = get_logger("cameras.mediamtx")


async def add_transcode_path(
    self: MediaMTXClient,
    *,
    sibling_name: str,
    source_path: str,
) -> bool:
    """Provision a transcoded H.264 sibling path for browser HLS playback.

    Args:
      sibling_name: The path name to expose to readers (e.g.
        "cam-8a0b2ad47173-h264").
      source_path: The existing source path that's serving H.265
        (e.g. "cam-8a0b2ad47173").

    Strategy:
      Register a MediaMTX path with `runOnInit` set to an ffmpeg command
      that reads the H.265 source over RTSP and republishes as H.264
      over RTSP to the sibling path. MediaMTX then exposes that sibling
      automatically over HLS at /hls/<sibling_name>/index.m3u8.

      ffmpeg flags:
        -rtsp_transport tcp                   # Reliable transport
        -i rtsp://localhost:8554/<source>     # Read from MediaMTX itself
        -c:v libx264                          # Software H.264 encoder
        -preset ultrafast -tune zerolatency   # Minimize latency
        -an                                   # Strip audio (unused)
        -f rtsp rtsp://localhost:8554/<sib>   # Push back to MediaMTX

      `localhost` works because ffmpeg runs inside the MediaMTX container
      and MediaMTX listens on localhost:8554 within that same network ns.

    Idempotency:
      If the sibling already exists this returns True without changes.
      MediaMTX's add returns a body containing "already exists" - we
      treat that as success since the desired state is achieved.
    """
    ffmpeg_cmd = (
        f"ffmpeg -hide_banner -loglevel warning "
        f"-rtsp_transport tcp "
        f"-i rtsp://localhost:8554/{source_path} "
        f"-c:v libx264 -preset ultrafast -tune zerolatency "
        f"-an -f rtsp rtsp://localhost:8554/{sibling_name}"
    )
    # We deliberately use runOnInit (not runOnDemand). In MediaMTX 1.9.3,
    # runOnDemand fires for RTSP/RTMP readers but not HLS readers, so
    # browser HLS requests would never trigger ffmpeg. runOnInit fires
    # as soon as MediaMTX loads the path config, regardless of reader
    # presence. runOnInitRestart auto-respawns ffmpeg if it dies.
    payload = {
        "runOnInit": ffmpeg_cmd,
        "runOnInitRestart": True,
        # No recording on the transcoded sibling - original H.265 is
        # the canonical archive; the transcode is purely for browser
        # consumption and would just bloat disk.
        "record": False,
    }

    status, body = await self._request(
        "POST", f"/v3/config/paths/add/{sibling_name}", payload
    )

    if status in (200, 201):
        log.info(
            "mediamtx.transcode_added",
            sibling=sibling_name,
            source=source_path,
        )
        return True

    # "Already exists" is success - desired state achieved.
    if status == 400 and body and "already" in str(body).lower():
        log.info("mediamtx.transcode_already_exists", sibling=sibling_name)
        return True

    log.warning(
        "mediamtx.transcode_add_failed",
        sibling=sibling_name,
        source=source_path,
        status=status,
        body=body,
    )
    return False


# Monkey-patch onto the class so existing code paths
# (cameras.service.ensure_browser_path) can call it without code changes.
MediaMTXClient.add_transcode_path = add_transcode_path
