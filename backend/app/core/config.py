"""Application configuration.

All environment variables are loaded here and validated by Pydantic.
Every other module imports `settings` from this file — never read os.environ
directly elsewhere.
"""

from functools import lru_cache
from typing import List

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Application -----------------------------------------------------------
    APP_NAME: str = "VisionTrack"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # IMPORTANT: stored as a raw string from the env (comma-separated) and
    # exposed as a list via the computed CORS_ORIGINS property below.
    #
    # We can't type this as List[str] because pydantic-settings v2 tries to
    # JSON-decode any list-typed env value before any validator runs, which
    # rejects plain "a,b,c" with a confusing JSONDecodeError.
    CORS_ORIGINS_RAW: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    @computed_field
    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Parsed list of CORS origins."""
        raw = self.CORS_ORIGINS_RAW.strip()
        if not raw:
            return []
        if raw.startswith("["):
            import json
            try:
                value = json.loads(raw)
                if isinstance(value, list):
                    return [str(o).strip() for o in value if str(o).strip()]
            except json.JSONDecodeError:
                pass
        return [o.strip() for o in raw.split(",") if o.strip()]

    # -- Security --------------------------------------------------------------
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    # -- Database --------------------------------------------------------------
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "visiontrack"
    POSTGRES_PASSWORD: str = "visiontrack"
    POSTGRES_DB: str = "visiontrack"

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Sync URL for Alembic migrations."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # -- Redis -----------------------------------------------------------------
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @computed_field
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # Redis Streams used by the AI worker -> backend consumer pipeline.
    # Names must match ai-worker/app/config.py so the consumer reads the
    # streams the worker actually writes to.
    TRACK_STREAM_PREFIX: str = "vt:tracks"
    LIFECYCLE_STREAM_PREFIX: str = "vt:track_lifecycle"

    # -- MinIO -----------------------------------------------------------------
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "visiontrack"
    MINIO_SECRET_KEY: str = "visiontrack"
    MINIO_BUCKET: str = "visiontrack"
    MINIO_SECURE: bool = False

    # -- MediaMTX --------------------------------------------------------------
    MEDIAMTX_API_URL: str = "http://mediamtx:9997"
    MEDIAMTX_HLS_URL: str = "http://mediamtx:8888"
    MEDIAMTX_RTSP_URL: str = "rtsp://mediamtx:8554"
    # ----- Milvus (P2.3) -----------------------------------------------------
    MILVUS_HOST: str = "milvus"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "person_embeddings"

    # ----- Embedding stream (P2.3) -------------------------------------------
    # ai-worker-ds publishes to vt:ds:embeddings:<tenant_id>; the backend
    # consumer reads from here and dual-writes to pgvector + Milvus.
    EMBEDDING_STREAM_PREFIX: str = "vt:ds:embeddings"

    # ----- Face identity feed (external face-recognition pipeline) -----------
    # A separate face-recognition pipeline publishes recognized identities to
    # vt:face:identities:<tenant_id>. The face-identity consumer correlates each
    # event to an active track (camera + bbox IoU + time) and labels its Person.
    # Kept separate from ReID clustering: face identity is an overlay, never an
    # input to matching.
    FACE_IDENTITY_ENABLED: bool = True
    FACE_IDENTITY_STREAM_PREFIX: str = "vt:face:identities"
    FACE_ID_CORRELATION_WINDOW_MS: int = 1500  # match track_points within +/- this
    FACE_ID_MIN_IOU: float = 0.2               # min bbox IoU to bind to a track
    FACE_ID_CANDIDATE_LIMIT: int = 200         # max track_points scanned per event

    # ----- Matcher (P2.5) ----------------------------------------------------
    # The cross-camera matcher sweeps unmatched person_embeddings, clusters
    # them into Person identities via pgvector cosine similarity, and assigns
    # tracks.person_id.
    MATCHER_ENABLED: bool = True
    MATCHER_INTERVAL_SECONDS: int = 30   # how often the sweep wakes
    MATCHER_BATCH_SIZE: int = 200        # rows claimed per tenant per pass
    MATCHER_MATCH_THRESHOLD: float = 0.65  # cosine sim >= this => same person
    MATCHER_MIN_QUALITY_WEIGHT: float = 0.01  # centroid weight floor for low/null quality

    # ----- Multi-view fuser (MV3DT Phase A) ----------------------------------
    # Stitches per-camera tracks into site-wide global trajectories using
    # floor-plan world positions (+ appearance person_id). See docs/MV3DT.md.
    MV3DT_ENABLED: bool = True
    MV3DT_INTERVAL_SECONDS: int = 20    # how often the fuser sweeps
    MV3DT_WINDOW_SECONDS: int = 180     # look back this far for completed tracks
    MV3DT_SETTLE_SECONDS: int = 5       # only fuse tracks that ended >= this ago
    MV3DT_WORLD_EPS: float = 0.08       # same-place threshold (fraction of plan)
    MV3DT_LINK_GAP_SECONDS: int = 10    # max time gap for an appearance link
    MV3DT_FUSE_BUCKET_MS: int = 500     # time bucket for averaging fused points


    # -- First superuser (one-time seeding) ------------------------------------
    FIRST_SUPERUSER_EMAIL: str = "admin@visiontrack.io"
    FIRST_SUPERUSER_PASSWORD: str = "ChangeMe123!"
    FIRST_TENANT_NAME: str = "Demo Tenant"
    FIRST_TENANT_SUBDOMAIN: str = "demo"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — avoids re-reading .env on every call."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
