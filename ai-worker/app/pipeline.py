"""Per-camera frame pipeline.

One asyncio task per camera. The task loops forever:

  1. Open RTSP via OpenCV
  2. Read frames at source FPS
  3. Drop frames between target-FPS intervals (we don't need every frame)
  4. Run YOLOv8 inference on the chosen frame
  5. Update the per-camera tracker
  6. Diff against previous tracked-IDs → emit lifecycle events
  7. Publish detections + lifecycle to Redis
  8. On RTSP error: close, sleep with backoff, retry

Why asyncio if OpenCV is blocking?
   cv2.VideoCapture.read() does block, and YOLO inference blocks. We
   wrap both in asyncio.to_thread() so the event loop can supervise
   multiple cameras concurrently and respond to shutdown signals
   cleanly. For 4-8 cameras the threading overhead is negligible.
"""

import asyncio
import time

import cv2

from app.camera_discovery import DiscoveredCamera
from app.config import settings
from app.inference import detector
from app.logging_config import get_logger
from app.publisher import TrackPublisher
from app.reid import embedder
from app.tracker import CameraTracker

log = get_logger("pipeline")


class CameraPipeline:
    """Owns the frame loop for a single camera. Lifecycle managed externally."""

    def __init__(self, camera: DiscoveredCamera, publisher: TrackPublisher) -> None:
        self.camera = camera
        self._publisher = publisher
        self._tracker = CameraTracker(target_fps=settings.TARGET_FPS)
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        # IDs we've already emitted a "started" event for, so we don't
        # spam the lifecycle stream on every frame.
        self._known_track_ids: set[int] = set()
        # Per-track processed-frame counter, for 1-in-N embedding sampling.
        self._emb_frame_count: dict[int, int] = {}

    def start(self) -> None:
        """Spawn the pipeline task. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run(), name=f"cam-{self.camera.id}"
        )

    async def stop(self) -> None:
        """Signal the pipeline to exit and wait for it. Idempotent."""
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                log.warning("pipeline.stop_timeout", camera_id=str(self.camera.id))
                self._task.cancel()

    async def _run(self) -> None:
        """The main per-camera loop. Reconnects forever until stopped."""
        log.info(
            "pipeline.starting",
            camera_id=str(self.camera.id),
            name=self.camera.name,
            rtsp_url=self.camera.rtsp_url,
        )

        backoff = settings.RECONNECT_BACKOFF_MIN
        frame_interval_s = 1.0 / settings.TARGET_FPS

        while not self._stop_event.is_set():
            cap = await asyncio.to_thread(self._open_capture)
            if cap is None or not cap.isOpened():
                log.warning(
                    "pipeline.open_failed",
                    camera_id=str(self.camera.id),
                    backoff=backoff,
                )
                await self._sleep_or_stop(backoff)
                backoff = min(backoff * 2, settings.RECONNECT_BACKOFF_MAX)
                continue

            # Successful connect — reset backoff
            backoff = settings.RECONNECT_BACKOFF_MIN
            last_infer_ts = 0.0
            consecutive_failures = 0

            try:
                while not self._stop_event.is_set():
                    ok, frame = await asyncio.to_thread(cap.read)
                    if not ok or frame is None:
                        consecutive_failures += 1
                        if consecutive_failures >= 5:
                            log.warning(
                                "pipeline.read_failed_giving_up",
                                camera_id=str(self.camera.id),
                            )
                            break
                        await asyncio.sleep(0.1)
                        continue
                    consecutive_failures = 0

                    # FPS gating: drop this frame if we processed one recently.
                    now = time.monotonic()
                    if (now - last_infer_ts) < frame_interval_s:
                        continue
                    last_infer_ts = now

                    await self._process_frame(frame)
            finally:
                await asyncio.to_thread(cap.release)

            if not self._stop_event.is_set():
                log.info(
                    "pipeline.reconnecting",
                    camera_id=str(self.camera.id),
                    backoff=backoff,
                )
                await self._sleep_or_stop(backoff)
                backoff = min(backoff * 2, settings.RECONNECT_BACKOFF_MAX)

        log.info("pipeline.stopped", camera_id=str(self.camera.id))

    def _open_capture(self) -> cv2.VideoCapture | None:
        """Open the RTSP stream. Blocking — called via to_thread."""
        # Force TCP transport for reliability. UDP can lose frames over
        # noisy networks and the savings aren't material for 10 fps.
        # OpenCV reads the OPENCV_FFMPEG_CAPTURE_OPTIONS env var if set;
        # explicit URL parameters are more portable.
        url = self.camera.rtsp_url
        if "?" not in url:
            url = f"{url}?rtsp_transport=tcp"
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        # Small read buffer so cap.read() always returns the latest frame
        # rather than stale buffered ones. This is critical for low latency.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    async def _process_frame(self, frame_bgr) -> None:
        """Run inference + tracking + publish for one frame."""
        frame_ts_ms = int(time.time() * 1000)

        # Inference is blocking (CUDA call). Use to_thread so other
        # camera pipelines aren't starved waiting for our forward pass.
        try:
            detections = await asyncio.to_thread(detector.detect, frame_bgr)
        except Exception as e:
            log.warning(
                "pipeline.inference_error",
                camera_id=str(self.camera.id),
                error=str(e),
            )
            return

        # Tracker update is pure-Python (numpy), cheap to run inline.
        tracked = self._tracker.update(detections)

        # Diff against known IDs to emit lifecycle events
        current_ids = {t.track_id for t in tracked}
        new_ids = current_ids - self._known_track_ids
        ended_ids = self._known_track_ids - current_ids

        # Publish per-frame detections
        if tracked:
            track_dicts = [
                {
                    "track_id": t.track_id,
                    "bbox": list(t.bbox_xyxy),
                    "confidence": t.confidence,
                    "class_id": t.class_id,
                }
                for t in tracked
            ]
            await self._publisher.publish_tracks(
                tenant_id=self.camera.tenant_id,
                camera_id=self.camera.id,
                frame_ts_ms=frame_ts_ms,
                tracks=track_dicts,
            )

        # Sample + publish ReID embeddings (feeds the backend matcher).
        await self._maybe_publish_embeddings(frame_bgr, tracked, frame_ts_ms)

        # Emit lifecycle events
        for tid in new_ids:
            bbox = next(
                (list(t.bbox_xyxy) for t in tracked if t.track_id == tid), None
            )
            await self._publisher.publish_lifecycle(
                tenant_id=self.camera.tenant_id,
                camera_id=self.camera.id,
                track_id=tid,
                event="started",
                ts_ms=frame_ts_ms,
                first_bbox=bbox,
            )
        for tid in ended_ids:
            await self._publisher.publish_lifecycle(
                tenant_id=self.camera.tenant_id,
                camera_id=self.camera.id,
                track_id=tid,
                event="ended",
                ts_ms=frame_ts_ms,
            )
            # Track gone — drop its sampling counter so the dict can't grow
            # without bound over the camera's lifetime.
            self._emb_frame_count.pop(tid, None)

        self._known_track_ids = current_ids

    async def _maybe_publish_embeddings(self, frame_bgr, tracked, frame_ts_ms) -> None:
        """For each active track, sample 1-in-N frames and publish an OSNet
        embedding when the crop quality clears the floor.

        Quality = confidence x normalized bbox area (capped at 30% of frame),
        matching the DeepStream worker's reid_probe scoring so both producers
        weight embeddings the same way.
        """
        if not embedder.enabled or not tracked:
            return
        h, w = frame_bgr.shape[:2]
        frame_area = float(h * w) or 1.0
        n_interval = max(1, settings.EMBEDDING_SAMPLE_INTERVAL_FRAMES)

        for t in tracked:
            count = self._emb_frame_count.get(t.track_id, 0) + 1
            self._emb_frame_count[t.track_id] = count
            # Sample on the first frame seen and every Nth thereafter.
            if count % n_interval != 1:
                continue

            x1, y1, x2, y2 = t.bbox_xyxy
            bbox_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            norm_area = min(bbox_area / frame_area, 0.3) / 0.3
            quality = float(t.confidence) * norm_area
            if quality < settings.EMBEDDING_QUALITY_FLOOR:
                continue

            # ONNX inference is blocking CPU work — offload so the camera
            # loop (and sibling cameras) aren't stalled.
            emb = await asyncio.to_thread(embedder.embed, frame_bgr, t.bbox_xyxy)
            if emb is None:
                continue
            await self._publisher.publish_embedding(
                tenant_id=self.camera.tenant_id,
                camera_id=self.camera.id,
                track_id=t.track_id,
                captured_at_ms=frame_ts_ms,
                quality=quality,
                embedding=emb,
            )

    async def _sleep_or_stop(self, seconds: float) -> None:
        """Sleep, but wake up early if a stop is requested."""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
