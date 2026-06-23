"""OSNet ReID embedding extraction.

Runs the same `osnet_v2.onnx` model the DeepStream worker uses, so the two
producers share an embedding space — when the in-DeepStream SGIE (P2.3b) is
eventually unblocked, embeddings from both workers cluster into the same
identities with no matcher change.

We run it on CPU via onnxruntime. Sampled at 1-in-N frames per track on tiny
128x256 crops, the load is negligible, and a CPU session sidesteps all
CUDA/cuDNN/ABI matching risk (torch already owns the GPU in this image). To
move it to GPU later, swap the dep to `onnxruntime-gpu` and add
`CUDAExecutionProvider` to the providers list below.

Model contract (verified against the .onnx):
  input  "input"     [batch, 3, 256, 128]   (NCHW, H=256, W=128)
  output "embedding" [batch, 512]
"""

from __future__ import annotations

import cv2
import numpy as np

from app.config import settings
from app.logging_config import get_logger

log = get_logger("reid")

# OSNet input geometry + torchreid's ImageNet normalization.
_IN_W, _IN_H = 128, 256
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


class ReidEmbedder:
    """Lazily-loaded OSNet ONNX session. Degrades gracefully to disabled."""

    def __init__(self) -> None:
        self._session = None
        self._input_name = "input"
        self._enabled = False
        if not settings.REID_ENABLED:
            log.info("reid.disabled_by_config")
            return
        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                settings.REID_MODEL_PATH,
                providers=["CPUExecutionProvider"],
            )
            self._input_name = self._session.get_inputs()[0].name
            self._enabled = True
            log.info(
                "reid.loaded",
                model=settings.REID_MODEL_PATH,
                input=self._input_name,
                providers=self._session.get_providers(),
            )
        except Exception as e:
            # Missing model file / ORT issue — keep the worker running with
            # embeddings disabled. Tracks still publish as before.
            log.warning("reid.load_failed", model=settings.REID_MODEL_PATH, error=str(e))
            self._session = None
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def embed(self, frame_bgr, bbox_xyxy) -> list[float] | None:
        """Return a unit-normalized 512-d embedding for the person crop, or
        None if disabled / the crop is unusable / inference fails."""
        if not self._enabled or self._session is None:
            return None
        h, w = frame_bgr.shape[:2]
        x1, y1, x2, y2 = (int(round(v)) for v in bbox_xyxy)
        # Clamp to frame bounds; reject degenerate boxes.
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None

        crop = frame_bgr[y1:y2, x1:x2]
        try:
            chw = self._preprocess(crop)
            out = self._session.run(None, {self._input_name: chw})[0]  # [1, 512]
        except Exception as e:
            log.warning("reid.infer_failed", error=str(e))
            return None

        vec = np.asarray(out[0], dtype=np.float32)
        norm = float(np.linalg.norm(vec))
        if norm == 0.0:
            return None
        return (vec / norm).tolist()

    def _preprocess(self, crop_bgr) -> np.ndarray:
        """BGR crop -> normalized NCHW float32 batch of 1."""
        resized = cv2.resize(crop_bgr, (_IN_W, _IN_H), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        chw = np.transpose(rgb, (2, 0, 1))  # HWC -> CHW
        chw = (chw - _MEAN) / _STD
        return np.expand_dims(chw, axis=0).astype(np.float32)  # [1,3,256,128]


# One shared instance across all camera pipelines (sessions are thread-safe).
embedder = ReidEmbedder()
