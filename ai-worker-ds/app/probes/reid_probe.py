"""ReID embedding extraction probe (P2.3).

Attached to the SGIE element's src pad. For every batch of detections
that has SGIE-produced tensor metadata:
  - Walk the per-object user-meta list to find the inference tensor
  - Copy the embedding from GPU memory to a numpy array (one host copy)
  - Compute a quality score (detection conf × bbox size)
  - Drop low-quality or over-sampled entries
  - Push to an async queue for the publisher to drain

DESIGN: this probe MUST be non-blocking. It's called from the GStreamer
thread; any blocking I/O here stalls the entire DS pipeline. So:
  - No Redis writes here (publisher thread does that)
  - No DB calls
  - No async/await — probe is sync, queue.put_nowait() is the only
    handoff. If the queue is full we drop the embedding rather than
    block.

Adapted from ~/deepstream_visitor_reid/probes/reid_probe.py with:
  - Tenant + camera context plumbed in (lab version had module-level globals)
  - Sampling logic (1-per-N-frames-per-track)
  - Quality filter
  - Async queue handoff instead of synchronous identify_visitor() call
  - Removed text overlay code (no OSD in our pipeline)
"""

from __future__ import annotations

import time
from queue import Full, Queue
from typing import Any
from uuid import UUID

import ctypes

import numpy as np
import pyds

from app.config import settings
from app.logging_config import get_logger

log = get_logger("reid_probe")


# Per-track frame counter for sampling. Keyed by (camera_id, track_id)
# to avoid track-id collision across cameras. Cleaned up periodically by
# the supervisor (P2.5 will manage this); for now grows unbounded —
# acceptable for short demo runs, must be bounded before production.
_track_frame_count: dict[tuple[str, int], int] = {}

# Stats for log throttling
_drop_count_qfull = 0
_drop_count_quality = 0
_publish_count = 0
_last_stats_log_ts = 0.0


def _compute_quality_score(
    confidence: float, bbox_area: float, frame_area: float
) -> float:
    """Combine detection confidence + relative bbox size into a single score.

    Tiny bboxes (person far from camera) make poor ReID samples — the
    feature extractor sees too few pixels. Cap the bbox-area term at 30%
    of the frame; anything larger doesn't add value (we'd be sampling a
    near-cropped face).
    """
    if frame_area <= 0:
        return 0.0
    area_ratio = bbox_area / frame_area
    area_term = min(area_ratio, 0.3) / 0.3
    return float(confidence) * float(area_term)


def _extract_embedding_from_obj_meta(obj_meta) -> np.ndarray | None:
    """Walk obj_user_meta_list, find the first NvDsInferTensorMeta,
    copy the float buffer into a numpy array.

    Returns None if no tensor meta was attached to this object — which
    happens when SGIE didn't run on this object (e.g. wrong class).
    """
    user_meta_list = obj_meta.obj_user_meta_list
    while user_meta_list is not None:
        try:
            user_meta = pyds.NvDsUserMeta.cast(user_meta_list.data)
        except Exception:
            user_meta_list = user_meta_list.next
            continue

        # NVDSINFER_TENSOR_OUTPUT_META = 12 (per nvdsmeta_schema.h); using
        # the constant directly avoids importing nvdsmeta from C bindings.
        # If the user-meta isn't a tensor output, skip it.
        if user_meta.base_meta.meta_type != pyds.NvDsMetaType.NVDSINFER_TENSOR_OUTPUT_META:
            user_meta_list = user_meta_list.next
            continue

        try:
            tensor_meta = pyds.NvDsInferTensorMeta.cast(user_meta.user_meta_data)
            layer = tensor_meta.output_layers_info[0]
            n = int(layer.inferDims.numElements)
            if n <= 0:
                return None
            # CRITICAL: pyds.get_ptr() returns a raw int address. We MUST
            # cast it to a properly-typed ctypes pointer BEFORE handing
            # it to numpy. Passing the raw int causes np.ctypeslib to
            # interpret it as a host pointer of unspecified type — which
            # at best reads garbage, at worst SIGSEGVs.
            raw_ptr = pyds.get_ptr(layer.buffer)
            float_ptr = ctypes.cast(raw_ptr, ctypes.POINTER(ctypes.c_float))
            arr = np.ctypeslib.as_array(float_ptr, shape=(n,))
            # Copy out so we own the bytes after DS reuses the buffer.
            return arr.astype(np.float32, copy=True)
        except Exception as e:
            log.debug("probe.tensor_extract_failed", error=str(e))
            return None

        # not reached, but defensive
        user_meta_list = user_meta_list.next

    return None


class ReidProbe:
    """Configured probe bound to a pipeline + queue.

    The pipeline supplies a `source_id_to_camera` map so we can resolve
    each frame's source_id (the streammux sink-pad index) back to its
    camera and tenant.

    Use case: pipeline.attach_probe(sgie_src_pad, ReidProbe(queue, source_map))
    """

    def __init__(
        self,
        queue: "Queue[dict[str, Any]]",
        source_id_to_camera: dict[int, Any],
    ) -> None:
        self._queue = queue
        self._source_id_to_camera = source_id_to_camera
        self._frame_w = settings.DS_MUX_WIDTH
        self._frame_h = settings.DS_MUX_HEIGHT
        self._frame_area = float(self._frame_w * self._frame_h)
        self._sample_interval = settings.EMBEDDING_SAMPLE_INTERVAL_FRAMES
        self._quality_floor = settings.EMBEDDING_QUALITY_FLOOR

    # GStreamer pad probe signature: (pad, info, user_data) -> PadProbeReturn
    def __call__(self, pad, info, user_data) -> Any:
        global _drop_count_qfull, _drop_count_quality, _publish_count
        global _last_stats_log_ts

        # Importing Gst at module level can fail if GST isn't initialized
        # in this thread context; defer until inside the probe.
        from gi.repository import Gst

        # DIAG: use print(flush=True) — log lib buffers, crash eats it
        print("PROBE_ENTER", flush=True)

        gst_buffer = info.get_buffer()
        print(f"PROBE_GOT_BUFFER buffer={gst_buffer is not None}", flush=True)
        if gst_buffer is None:
            return Gst.PadProbeReturn.OK

        try:
            print("PROBE_PRE_BATCH_META", flush=True)
            batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
            print(f"PROBE_BATCH_META is_none={batch_meta is None}", flush=True)
        except Exception as e:
            log.warning("probe.no_batch_meta", error=str(e))
            return Gst.PadProbeReturn.OK

        if batch_meta is None:
            return Gst.PadProbeReturn.OK

        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            try:
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except Exception:
                l_frame = l_frame.next
                continue

            source_id = frame_meta.source_id
            camera = self._source_id_to_camera.get(source_id)
            if camera is None:
                # Unknown source — could be a stale frame between rebuilds
                l_frame = l_frame.next
                continue

            # Process detections in this frame
            l_obj = frame_meta.obj_meta_list
            while l_obj is not None:
                try:
                    obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                except Exception:
                    l_obj = l_obj.next
                    continue

                track_id = int(obj_meta.object_id)
                if track_id < 0:
                    # No tracker assignment yet (probationary track)
                    l_obj = l_obj.next
                    continue

                # Sample 1-per-N-frames per (camera, track)
                key = (str(camera.id), track_id)
                count = _track_frame_count.get(key, 0)
                _track_frame_count[key] = count + 1
                if count % self._sample_interval != 0:
                    l_obj = l_obj.next
                    continue

                # Compute quality before doing the GPU->CPU copy. If quality
                # is too low, skip the expensive copy entirely.
                rect = obj_meta.rect_params
                bbox_area = float(rect.width) * float(rect.height)
                quality = _compute_quality_score(
                    confidence=float(obj_meta.confidence),
                    bbox_area=bbox_area,
                    frame_area=self._frame_area,
                )
                if quality < self._quality_floor:
                    _drop_count_quality += 1
                    l_obj = l_obj.next
                    continue

                embedding = _extract_embedding_from_obj_meta(obj_meta)
                if embedding is None:
                    l_obj = l_obj.next
                    continue

                # Build payload — keep it small. Backend reconstructs UUIDs
                # from strings.
                payload = {
                    "tenant_id": str(camera.tenant_id),
                    "camera_id": str(camera.id),
                    "track_id": track_id,
                    "captured_at_ms": int(time.time() * 1000),
                    "quality": quality,
                    "embedding": embedding.tolist(),  # 512 floats; ~6KB JSON
                }

                try:
                    self._queue.put_nowait(payload)
                    _publish_count += 1
                except Full:
                    # Queue is backed up — publisher can't keep up with
                    # Redis. Drop rather than block the GStreamer thread.
                    _drop_count_qfull += 1

                l_obj = l_obj.next

            l_frame = l_frame.next

        # Throttled stats log (every 30 sec)
        now = time.time()
        if now - _last_stats_log_ts > 30.0:
            log.info(
                "probe.stats",
                published=_publish_count,
                dropped_quality=_drop_count_quality,
                dropped_qfull=_drop_count_qfull,
            )
            _last_stats_log_ts = now

        return Gst.PadProbeReturn.OK
