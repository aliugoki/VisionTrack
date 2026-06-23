"""Milvus connection and collection bootstrap.

Strategy:
  - Single collection ('person_embeddings') with tenant_id as partition
    key. Cross-tenant searches are physically impossible at the query
    layer because partition key filtering happens before the vector
    search runs.
  - HNSW index on the embedding column (cosine metric — matches the
    pgvector side, OSNet's typical similarity space).
  - Connection bootstrapped on backend startup. If Milvus is down the
    consumer raises and dual-write returns "milvus failed" — pgvector
    write still succeeds, so we don't lose data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("milvus")

# pymilvus is sync-only as of 2.4. We wrap it in asyncio.to_thread on
# the call sites; the connection itself is a global module-level object
# the way pymilvus expects.
try:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        connections,
        utility,
    )
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False
    log.warning("milvus.pymilvus_not_installed")


COLLECTION_ALIAS = "default"
EMBEDDING_DIM = 512


def is_available() -> bool:
    return PYMILVUS_AVAILABLE


def connect() -> bool:
    """Connect to Milvus + ensure collection exists. Idempotent.

    Returns True on success, False on any failure. Caller decides whether
    to abort startup or continue degraded (we continue degraded — pg
    side still works).
    """
    if not PYMILVUS_AVAILABLE:
        log.warning("milvus.skip_connect", reason="pymilvus_not_installed")
        return False

    try:
        connections.connect(
            alias=COLLECTION_ALIAS,
            host=settings.MILVUS_HOST,
            port=str(settings.MILVUS_PORT),
        )
    except Exception as e:
        log.warning(
            "milvus.connect_failed",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
            error=str(e),
        )
        return False

    log.info(
        "milvus.connected",
        host=settings.MILVUS_HOST,
        port=settings.MILVUS_PORT,
    )

    try:
        _ensure_collection()
    except Exception as e:
        log.warning("milvus.ensure_collection_failed", error=str(e))
        return False

    return True


def disconnect() -> None:
    if not PYMILVUS_AVAILABLE:
        return
    try:
        connections.disconnect(alias=COLLECTION_ALIAS)
        log.info("milvus.disconnected")
    except Exception as e:
        log.warning("milvus.disconnect_failed", error=str(e))


def _ensure_collection() -> "Collection":  # type: ignore[name-defined]
    """Create the collection if absent, load it into memory if present.

    Schema:
      - id              INT64       (auto-id, primary key)
      - pg_embedding_id VARCHAR(36) (UUID matching pg row, source-of-truth FK)
      - tenant_id       VARCHAR(36) (partition key — physically isolates queries)
      - track_id        VARCHAR(36)
      - camera_id       VARCHAR(36)
      - captured_at     INT64       (unix milliseconds)
      - quality         FLOAT
      - embedding       FLOAT_VECTOR(512)
    """
    name = settings.MILVUS_COLLECTION

    if utility.has_collection(name, using=COLLECTION_ALIAS):
        coll = Collection(name, using=COLLECTION_ALIAS)
        # Ensure loaded into memory for searches
        try:
            coll.load()
        except Exception as e:
            log.warning("milvus.load_failed", error=str(e))
        log.info("milvus.collection_exists", name=name)
        return coll

    log.info("milvus.creating_collection", name=name)

    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True,
        ),
        FieldSchema(
            name="pg_embedding_id",
            dtype=DataType.VARCHAR,
            max_length=36,
        ),
        # tenant_id is a partition key — Milvus uses it to physically
        # shard the data. Queries that filter by tenant_id only touch
        # the relevant partition.
        FieldSchema(
            name="tenant_id",
            dtype=DataType.VARCHAR,
            max_length=36,
            is_partition_key=True,
        ),
        FieldSchema(
            name="track_id",
            dtype=DataType.VARCHAR,
            max_length=36,
        ),
        FieldSchema(
            name="camera_id",
            dtype=DataType.VARCHAR,
            max_length=36,
        ),
        FieldSchema(
            name="captured_at",
            dtype=DataType.INT64,
        ),
        FieldSchema(
            name="quality",
            dtype=DataType.FLOAT,
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=EMBEDDING_DIM,
        ),
    ]

    schema = CollectionSchema(
        fields=fields,
        description="VisionTrack person ReID embeddings, partitioned by tenant",
        enable_dynamic_field=False,
        # 16 partitions per tenant_key — Milvus default for partition_key fields.
        # Each tenant's data is distributed across this many physical partitions.
        # Bumping later requires recreating the collection.
        num_partitions=16,
    )

    coll = Collection(
        name=name,
        schema=schema,
        using=COLLECTION_ALIAS,
    )

    # HNSW index — high recall, fast queries. M and efConstruction match
    # what we set on the pgvector side for consistency.
    index_params = {
        "metric_type": "COSINE",
        "index_type": "HNSW",
        "params": {"M": 16, "efConstruction": 64},
    }
    coll.create_index(field_name="embedding", index_params=index_params)
    coll.load()
    log.info("milvus.collection_created", name=name)
    return coll


def get_collection() -> "Collection | None":  # type: ignore[name-defined]
    """Return the collection handle, or None if Milvus isn't available."""
    if not PYMILVUS_AVAILABLE:
        return None
    try:
        return Collection(settings.MILVUS_COLLECTION, using=COLLECTION_ALIAS)
    except Exception as e:
        log.warning("milvus.get_collection_failed", error=str(e))
        return None
