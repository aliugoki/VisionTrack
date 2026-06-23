"""DeepStream AI worker entrypoint.

Architecture (P2.2):
  - Asyncio event loop on the main thread (matches existing ai-worker pattern)
  - GLib mainloop runs on a background thread, started from inside DeepStreamPipeline
  - Camera discovery polls the backend every DISCOVERY_INTERVAL_SECONDS
  - On camera-list change: tear down current pipeline, rebuild with new sources

Lifecycle:
  1. Configure logging
  2. Load backend service token
  3. Start camera discovery
  4. Build pipeline with discovered cameras
  5. Loop: re-poll cameras; rebuild pipeline if list changed
  6. On SIGTERM/SIGINT: stop pipeline + discovery; exit

NOT YET IMPLEMENTED IN P2.2 (intentionally — see docs/P2-ARCHITECTURE.md):
  - Probes attached for embedding extraction (P2.3)
  - Redis Streams publishing (P2.4)
  - Cross-camera matcher trigger (P2.5)
"""

from __future__ import annotations

import asyncio
import signal
import sys

from app.camera_discovery import CameraDiscovery, DiscoveredCamera
from app.config import load_backend_token, settings
from app.logging_config import configure_logging, get_logger
from app.pipeline import DeepStreamPipeline, cameras_changed

log = get_logger("main")


class WorkerApp:
    """Top-level supervisor."""

    def __init__(self) -> None:
        self.discovery: CameraDiscovery | None = None
        self.pipeline: DeepStreamPipeline | None = None
        self.current_cameras: list[DiscoveredCamera] = []
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        token = load_backend_token()
        if not token:
            log.error(
                "main.no_token",
                hint=(
                    "Set BACKEND_TOKEN env var, or mount a token at "
                    f"{settings.BACKEND_TOKEN_FILE}. The backend seeds "
                    "this token for the ai-worker@system user."
                ),
            )
            sys.exit(1)

        self.discovery = CameraDiscovery(token=token)
        await self.discovery.start()
        log.info("main.started")

    async def stop(self) -> None:
        log.info("main.stopping")
        if self.pipeline is not None:
            # pipeline.stop() is sync but should be quick (~seconds).
            # Run in a thread so we don't block the asyncio loop.
            await asyncio.to_thread(self.pipeline.stop)
            self.pipeline = None
        if self.discovery is not None:
            await self.discovery.stop()
            self.discovery = None
        log.info("main.stopped")

    async def reconcile_loop(self) -> None:
        """Periodically fetch cameras + rebuild pipeline if changed."""
        assert self.discovery is not None
        while not self._shutdown.is_set():
            cameras = await self.discovery.fetch_active_cameras()

            if not cameras:
                # No online cameras — tear down any running pipeline and wait.
                if self.pipeline is not None:
                    log.info("main.no_cameras_tearing_down")
                    await asyncio.to_thread(self.pipeline.stop)
                    self.pipeline = None
                    self.current_cameras = []
            elif self.pipeline is None or cameras_changed(self.current_cameras, cameras):
                log.info(
                    "main.cameras_changed",
                    old_count=len(self.current_cameras),
                    new_count=len(cameras),
                )
                if self.pipeline is not None:
                    await asyncio.to_thread(self.pipeline.stop)
                # Build + start new pipeline on a thread (build can block on
                # GStreamer element creation).
                self.pipeline = DeepStreamPipeline(cameras)
                try:
                    await asyncio.to_thread(self.pipeline.start)
                    self.current_cameras = cameras
                    log.info("main.pipeline_running", cameras=len(cameras))
                except Exception as e:
                    log.error("main.pipeline_start_failed", error=str(e))
                    self.pipeline = None
                    self.current_cameras = []

            # Wait DISCOVERY_INTERVAL_SECONDS or until shutdown signal
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(),
                    timeout=settings.DISCOVERY_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                pass

    def request_shutdown(self) -> None:
        log.info("main.shutdown_signal")
        self._shutdown.set()


async def amain() -> int:
    configure_logging()
    app = WorkerApp()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, app.request_shutdown)
        except NotImplementedError:
            # Windows / restricted envs — fall back to default signal handling.
            pass

    try:
        await app.start()
    except Exception as e:
        log.error("main.startup_failed", error=str(e))
        return 1

    reconcile_task = asyncio.create_task(app.reconcile_loop())

    await app._shutdown.wait()
    reconcile_task.cancel()
    try:
        await reconcile_task
    except asyncio.CancelledError:
        pass

    await app.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
