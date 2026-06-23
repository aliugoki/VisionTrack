"""YOLOv8 person-detection inference.

Wraps Ultralytics' YOLO model with our specific constraints:
  - Person class only (COCO class 0)
  - Configurable confidence and IoU thresholds
  - Returns a clean numpy array of detections, no PyTorch tensor surface

The model is loaded once at startup and shared across all camera
pipelines. PyTorch handles concurrent inference correctly — multiple
asyncio coroutines calling model() interleave through the CUDA scheduler.
"""

from dataclasses import dataclass

import numpy as np
import torch
from ultralytics import YOLO

from app.config import settings
from app.logging_config import get_logger

log = get_logger("inference")


@dataclass
class Detection:
    """One detected person in a frame, in source pixel space."""
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    class_id: int


class PersonDetector:
    """Singleton YOLOv8 wrapper for person detection."""

    def __init__(self) -> None:
        self._model: YOLO | None = None
        self._device: str = "cuda:0"

    def load(self) -> None:
        """Load model weights and move to GPU. Fails hard if CUDA unavailable.

        Called once at worker startup. We deliberately raise here rather
        than fall back to CPU — the deployment plan specifies GPU-only.
        """
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA is not available. The AI worker requires a GPU. "
                "Check that the container has runtime: nvidia and that "
                "NVIDIA Container Toolkit is installed on the host."
            )

        log.info(
            "inference.loading_model",
            model=settings.MODEL_NAME,
            device=self._device,
        )
        self._model = YOLO(settings.MODEL_NAME)
        # Warm up the model so the first real inference isn't slow due
        # to JIT compilation of CUDA kernels.
        dummy = np.zeros((settings.INFERENCE_IMGSZ, settings.INFERENCE_IMGSZ, 3), dtype=np.uint8)
        _ = self._model.predict(
            dummy,
            imgsz=settings.INFERENCE_IMGSZ,
            device=self._device,
            classes=[settings.PERSON_CLASS_ID],
            conf=settings.CONFIDENCE_THRESHOLD,
            iou=settings.IOU_THRESHOLD,
            verbose=False,
        )
        log.info(
            "inference.model_ready",
            cuda_device=torch.cuda.get_device_name(0),
            vram_allocated_mb=int(torch.cuda.memory_allocated() / 1024 / 1024),
        )

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Run person detection on one BGR frame.

        Returns detections in source pixel coordinates (Ultralytics
        rescales the predicted boxes back from inference resolution
        to source resolution automatically).
        """
        if self._model is None:
            raise RuntimeError("Detector not loaded — call load() first")

        results = self._model.predict(
            frame_bgr,
            imgsz=settings.INFERENCE_IMGSZ,
            device=self._device,
            classes=[settings.PERSON_CLASS_ID],
            conf=settings.CONFIDENCE_THRESHOLD,
            iou=settings.IOU_THRESHOLD,
            verbose=False,
        )

        if not results or len(results) == 0:
            return []

        r = results[0]
        if r.boxes is None or len(r.boxes) == 0:
            return []

        # boxes.xyxy: shape (N, 4), float tensor. conf: (N,). cls: (N,).
        # .cpu().numpy() pulls them out of the GPU; cheap for the small
        # sizes we have here (<100 detections per frame in practice).
        xyxy = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        classes = r.boxes.cls.cpu().numpy().astype(int)

        return [
            Detection(
                bbox_xyxy=tuple(xyxy[i].tolist()),
                confidence=float(confs[i]),
                class_id=int(classes[i]),
            )
            for i in range(len(xyxy))
        ]


# Module-level singleton. main.py calls .load() once at startup; every
# pipeline imports this same instance.
detector = PersonDetector()
