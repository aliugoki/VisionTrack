"""AI worker configuration.

All settings come from environment variables. Defaults are chosen so the
worker can boot inside docker-compose with no env file required, but
every value can be overridden at deploy time.
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
    SERVICE_NAME: str = "ai-worker"
    LOG_LEVEL: str = "INFO"

    # ----- Backend (camera discovery + auth) ----------------------------------
    BACKEND_URL: str = "http://backend:8000"
    # JWT for the seeded ai-worker@system service account. Read from a file
    # mounted by the backend (see deployment notes) or set via env.
    BACKEND_TOKEN: str = ""
    BACKEND_TOKEN_FILE: str = "/run/secrets/ai_worker_token"

    # ----- MediaMTX (source of RTSP frames) -----------------------------------
    # We read RTSP from MediaMTX, not from the camera directly. MediaMTX
    # already has the camera connection, so we piggyback on it. This avoids
    # camera-side RTSP session limits (most cameras allow ~2-4 sessions).
    MEDIAMTX_RTSP_BASE: str = "rtsp://mediamtx:8554"

    # ----- Redis (event publishing) -------------------------------------------
    REDIS_URL: str = "redis://redis:6379/0"
    # Stream key prefixes. We use one stream per tenant for sharding;
    # Batch D's consumer can scale horizontally per tenant if needed.
    TRACK_STREAM_PREFIX: str = "vt:tracks"
    LIFECYCLE_STREAM_PREFIX: str = "vt:track_lifecycle"
    # Max length per stream — old events get trimmed. With 10 fps and 8
    # cameras = 80 events/sec, 100k entries = ~20 minutes of buffer.
    # Plenty for a consumer that processes in real time.
    STREAM_MAX_LEN: int = 100_000

    # ----- Inference settings -------------------------------------------------
    # YOLOv8n is the default per Step 3 planning. Override with yolov8s.pt,
    # yolov8m.pt etc. for higher accuracy on a beefier GPU.
    MODEL_NAME: str = "yolov8n.pt"
    # Person class only — COCO class index 0. Filter at the model level so
    # we don't even allocate memory for non-person detections.
    PERSON_CLASS_ID: int = 0
    # Inference resolution. YOLOv8 default is 640. Smaller is faster, larger
    # is more accurate for small subjects (people far from the camera).
    INFERENCE_IMGSZ: int = 640
    # Confidence floor. 0.35 = balanced (default), 0.5 = strict, 0.25 = permissive.
    CONFIDENCE_THRESHOLD: float = 0.35
    # IOU threshold for NMS. Default Ultralytics value.
    IOU_THRESHOLD: float = 0.45

    # ----- ReID embeddings (P2.5 producer) ------------------------------------
    # Extracts OSNet embeddings from sampled person crops and publishes them
    # to vt:ds:embeddings:<tenant_id> — the same stream the backend embedding
    # consumer + matcher read. Uses the same osnet_v2.onnx the DeepStream
    # worker uses, mounted at /models, so both producers share one space.
    REID_ENABLED: bool = True
    REID_MODEL_PATH: str = "/models/osnet_v2.onnx"
    EMBEDDING_STREAM_PREFIX: str = "vt:ds:embeddings"
    # Sample one embedding per this many processed frames, per track. At
    # TARGET_FPS=10 a value of 30 is ~1 embedding / 3s of continuous track.
    EMBEDDING_SAMPLE_INTERVAL_FRAMES: int = 30
    # Drop embeddings whose quality (confidence x normalized bbox area) is
    # below this floor — tiny/uncertain detections make poor ReID samples.
    EMBEDDING_QUALITY_FLOOR: float = 0.3

    # ----- Frame pipeline -----------------------------------------------------
    # Target inference FPS per camera. 10 is the Step 3 default — see
    # planning notes. We achieve this by dropping frames between
    # inferences rather than throttling the decoder.
    TARGET_FPS: float = 10.0
    # Reconnect backoff. If RTSP drops we sleep min, retry, then back off
    # exponentially up to max. Reset on a successful frame.
    RECONNECT_BACKOFF_MIN: float = 2.0
    RECONNECT_BACKOFF_MAX: float = 30.0

    # ----- Camera discovery ---------------------------------------------------
    # How often we re-fetch the camera list from the backend. Each fetch
    # is a single small API call; 30s matches Batch A's health check
    # cadence so worker state is at most ~60s stale.
    DISCOVERY_INTERVAL_SECONDS: float = 30.0


settings = Settings()


def load_backend_token() -> str:
    """Read the backend service token from env or mounted file.

    Returns "" if neither is set — main.py treats that as a fatal config
    error and exits with a clear message.
    """
    if settings.BACKEND_TOKEN:
        return settings.BACKEND_TOKEN
    try:
        with open(settings.BACKEND_TOKEN_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
