"""ByteTrack multi-object tracker.

Wraps `supervision.ByteTrack` so callers get a simple interface:
detections in → tracked detections (with stable IDs) out.

One ByteTrack instance per camera. Tracker state is per-stream — IDs
don't cross cameras. (That's what Phase 3 ReID will add.)
"""

from dataclasses import dataclass

import numpy as np
import supervision as sv

from app.inference import Detection
from app.logging_config import get_logger

log = get_logger("tracker")


@dataclass
class TrackedDetection:
    """A detection that's been associated with a stable track ID by ByteTrack."""
    track_id: int
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    class_id: int


class CameraTracker:
    """One ByteTrack instance for one camera."""

    def __init__(self, target_fps: float) -> None:
        # supervision's ByteTrack parameters:
        #   track_activation_threshold: min confidence to start a new track
        #   lost_track_buffer: frames to keep a lost track around before
        #     dropping it. We tune this in frame units relative to our FPS.
        #   minimum_matching_threshold: IoU+visual match threshold for
        #     associating a detection to an existing track.
        #   frame_rate: tells ByteTrack our actual FPS so it can scale its
        #     internal motion model.
        self._tracker = sv.ByteTrack(
            track_activation_threshold=0.25,
            # 30 frames at 10 fps = 3 seconds. A person briefly occluded
            # behind a column should still re-associate with the same ID.
            lost_track_buffer=30,
            minimum_matching_threshold=0.8,
            frame_rate=int(target_fps),
        )

    def update(self, detections: list[Detection]) -> list[TrackedDetection]:
        """Update tracker with this frame's detections, return tracked output.

        The tracker may also return predicted positions for tracks that
        had no matching detection this frame (within lost_track_buffer);
        supervision only returns those when supplied an empty Detections
        object, which we don't do here.
        """
        if not detections:
            # Tell the tracker we saw nothing this frame so lost-track ages tick
            sv_dets = sv.Detections(
                xyxy=np.empty((0, 4), dtype=np.float32),
                confidence=np.empty((0,), dtype=np.float32),
                class_id=np.empty((0,), dtype=int),
            )
            self._tracker.update_with_detections(sv_dets)
            return []

        sv_dets = sv.Detections(
            xyxy=np.array([d.bbox_xyxy for d in detections], dtype=np.float32),
            confidence=np.array([d.confidence for d in detections], dtype=np.float32),
            class_id=np.array([d.class_id for d in detections], dtype=int),
        )

        tracked = self._tracker.update_with_detections(sv_dets)

        out: list[TrackedDetection] = []
        if tracked.tracker_id is None or len(tracked) == 0:
            return out

        for i in range(len(tracked)):
            tid = tracked.tracker_id[i]
            if tid is None:
                continue
            out.append(
                TrackedDetection(
                    track_id=int(tid),
                    bbox_xyxy=tuple(tracked.xyxy[i].tolist()),
                    confidence=float(tracked.confidence[i]) if tracked.confidence is not None else 0.0,
                    class_id=int(tracked.class_id[i]) if tracked.class_id is not None else 0,
                )
            )
        return out
