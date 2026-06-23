"""AI worker (DeepStream variant) configuration.

Mirrors the existing ai-worker/app/config.py shape so deployment
conventions stay identical. DS-specific settings (model paths,
batched-push timeout, embedding sampling) are appended.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ----- Service identity ---------------------------------------------------
    SERVICE_NAME: str = "ai-worker-ds"
    LOG_LEVEL: str = "INFO"

    # ----- Backend (camera discovery + auth) ----------------------------------
    BACKEND_URL: str = "http://backend:8000"
    BACKEND_TOKEN: str = ""
    BACKEND_TOKEN_FILE: str = "/run/secrets/ai_worker_token"

    # ----- MediaMTX -----------------------------------------------------------
    MEDIAMTX_RTSP_BASE: str = "rtsp://mediamtx:8554"

    # ----- Redis (event publishing) -------------------------------------------
    REDIS_URL: str = "redis://redis:6379/0"
    TRACK_STREAM_PREFIX: str = "vt:ds:tracks"
    LIFECYCLE_STREAM_PREFIX: str = "vt:ds:track_lifecycle"
    # P2.3 — embedding stream prefix. Backend consumer reads from
    # vt:ds:embeddings:<tenant_id> and dual-writes to Milvus + pgvector.
    EMBEDDING_STREAM_PREFIX: str = "vt:ds:embeddings"
    STREAM_MAX_LEN: int = 100_000

    # ----- DeepStream pipeline ------------------------------------------------
    DS_BATCH_PUSH_TIMEOUT_US: int = 40000
    DS_MUX_WIDTH: int = 1280
    DS_MUX_HEIGHT: int = 704  # must be a multiple of 32 (NvDCF tracker requirement)
    DS_LIVE_SOURCE: bool = True

    # ----- Config files -------------------------------------------------------
    PGIE_CONFIG_PATH: str = "/workspace/configs/pgie_peoplenet_transformer.txt"
    TRACKER_CONFIG_PATH: str = "/workspace/configs/tracker_config.txt"
    SGIE_REID_CONFIG_PATH: str = "/workspace/configs/sgie_reid.txt"
    SGIE_REID_TRITON_CONFIG_PATH: str = "/workspace/configs/sgie_reid_triton.txt"

    # ----- Embedding extraction (P2.3) ---------------------------------------
    # Sample 1-per-N-frames per active track. At ~30 fps decode (live),
    # 30 means one embedding every ~1 second per person. Tunable.
    EMBEDDING_SAMPLE_INTERVAL_FRAMES: int = 30
    # Skip embeddings below this quality threshold. Quality is computed as
    # detection_confidence * min(bbox_area / frame_area, 0.3) / 0.3
    # — tiny bboxes get dropped, low-confidence detections get dropped.
    EMBEDDING_QUALITY_FLOOR: float = 0.3
    # Max size of the in-process queue between probe and publisher. If
    # this fills up, the probe drops embeddings (preferred over blocking
    # the GStreamer thread, which would stall the pipeline).
    EMBEDDING_QUEUE_MAXSIZE: int = 1000

    # ----- Camera discovery ---------------------------------------------------
    DISCOVERY_INTERVAL_SECONDS: float = 30.0


settings = Settings()


def load_backend_token() -> str:
    """Read service-account token from env or mounted file (same as ai-worker)."""
    if settings.BACKEND_TOKEN:
        return settings.BACKEND_TOKEN
    try:
        with open(settings.BACKEND_TOKEN_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
