"""AI worker entrypoint.

Lifecycle:

  1. Configure logging
  2. Load YOLOv8 model onto GPU (fail-fast if no CUDA)
  3. Connect to Redis
  4. Read service-account token (env or mounted file)
  5. Start camera-discovery polling loop
  6. For each discovered ONLINE camera, spawn a pipeline task
  7. On every discovery cycle, reconcile: start new, stop disappeared
  8. On SIGTERM/SIGINT, gracefully stop all pipelines

This process is meant to run forever inside a Docker container with
NVIDIA runtime. `docker compose restart ai-worker` is the recovery
path; we don't try to self-heal CUDA / driver issues.
"""

import asyncio
import signal
import sys

from app.camera_discovery import CameraDiscovery
from app.config import load_backend_token, settings
from app.inference import detector
from app.logging_config import configure_logging, get_logger
from app.pipeline import CameraPipeline
from app.publisher import TrackPublisher

log = get_logger("main")


class WorkerApp:
    """Top-level supervisor — owns the publisher, discovery, and all pipelines."""

    def __init__(self) -> None:
        self.publisher = TrackPublisher()
        self.discovery: CameraDiscovery | None = None
        self.pipelines: dict[str, CameraPipeline] = {}
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        # Load YOLO first — fails fast if there's no GPU.
        detector.load()

        await self.publisher.start()

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

        log.info(
            "main.started",
            target_fps=settings.TARGET_FPS,
            confidence_threshold=settings.CONFIDENCE_THRESHOLD,
            model=settings.MODEL_NAME,
        )

    async def stop(self) -> None:
        log.info("main.stopping")
        # Stop all pipelines concurrently
        await asyncio.gather(
            *(p.stop() for p in self.pipelines.values()),
            return_exceptions=True,
        )
        self.pipelines.clear()
        if self.discovery is not None:
            await self.discovery.stop()
        await self.publisher.stop()
        log.info("main.stopped")

    async def run_discovery_loop(self) -> None:
        """Periodically fetch cameras and reconcile pipelines."""
        assert self.discovery is not None
        while not self._shutdown.is_set():
            cameras = await self.discovery.fetch_active_cameras()
            await self._reconcile(cameras)
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(),
                    timeout=settings.DISCOVERY_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                pass  # normal — keep polling

    async def _reconcile(self, cameras: list) -> None:
        """Start pipelines for new cameras, stop pipelines for gone ones."""
        desired = {c.task_key: c for c in cameras}

        # Start new
        for key, cam in desired.items():
            if key not in self.pipelines:
                log.info(
                    "main.pipeline_start",
                    camera_id=key,
                    name=cam.name,
                )
                p = CameraPipeline(cam, self.publisher)
                p.start()
                self.pipelines[key] = p

        # Stop disappeared
        to_stop = [k for k in self.pipelines if k not in desired]
        for key in to_stop:
            log.info("main.pipeline_stop", camera_id=key)
            await self.pipelines[key].stop()
            del self.pipelines[key]

    def request_shutdown(self) -> None:
        self._shutdown.set()


async def amain() -> int:
    configure_logging()
    app = WorkerApp()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, app.request_shutdown)

    try:
        await app.start()
    except Exception as e:
        log.error("main.startup_failed", error=str(e))
        return 1

    discovery_task = asyncio.create_task(app.run_discovery_loop())

    # Wait for either shutdown signal or discovery loop crash
    await app._shutdown.wait()
    discovery_task.cancel()
    try:
        await discovery_task
    except asyncio.CancelledError:
        pass

    await app.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
