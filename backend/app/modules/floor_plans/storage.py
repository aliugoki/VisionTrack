"""Floor Plans — file storage helpers.

Handles MinIO put/get for the floor plan files and PDF→PNG conversion.

Storage layout (single bucket, prefix-namespaced):
  visiontrack/
    floor-plans/
      {tenant_id}/
        {site_id}/
          {plan_id}/
            original.{ext}        — what the user uploaded
            rendered.png          — first-page render (PDFs only)

Why a single bucket with prefixes (instead of one bucket per type)?
  Buckets in S3/MinIO have config overhead (policies, encryption, retention).
  Prefixes give us logical separation without the operational cost.
  Auto-pruning on tenant delete just iterates the prefix.
"""

import io
import os
from typing import BinaryIO
from uuid import UUID

import fitz  # pymupdf — used for PDF rendering AND raster dimension extraction
from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("floor_plans.storage")


# Supported upload formats
ALLOWED_FORMATS = {"png", "jpg", "jpeg", "svg", "pdf"}
# Maximum upload size (matches the FastAPI multipart limit set in the router)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# DPI for PDF rendering. 200 DPI yields ~1700px wide at A4 — readable but
# not enormous. Bumping to 300 DPI would double storage with marginal
# visual benefit on screens.
PDF_RENDER_DPI = 200

# Fallback dimensions for SVG when viewBox is absent. SVG is vector so
# pixel dimensions are nominal — these only matter for marker-coordinate
# math and we want a reasonable canvas to start with.
SVG_FALLBACK_W = 2000
SVG_FALLBACK_H = 1500


def _client() -> Minio:
    """Build a MinIO client per call. Cheap; no connection pool needed."""
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def ensure_bucket() -> None:
    """Idempotent — create the bucket if it doesn't exist."""
    client = _client()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
        log.info("floor_plans.bucket_created", bucket=settings.MINIO_BUCKET)


def _prefix(tenant_id: UUID, site_id: UUID, plan_id: UUID) -> str:
    return f"floor-plans/{tenant_id}/{site_id}/{plan_id}"


class UploadResult:
    """Returned by store_upload — all the metadata the FloorPlan row needs."""

    def __init__(
        self,
        format: str,
        width_px: int,
        height_px: int,
        storage_key_original: str,
        storage_key_rendered: str | None,
        size_bytes: int,
    ):
        self.format = format
        self.width_px = width_px
        self.height_px = height_px
        self.storage_key_original = storage_key_original
        self.storage_key_rendered = storage_key_rendered
        self.size_bytes = size_bytes


def detect_format(filename: str, content_type: str) -> str | None:
    """Return one of {png, jpg, svg, pdf} or None if unsupported."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ct = (content_type or "").lower()
    if ext == "png" or ct == "image/png":
        return "png"
    if ext in ("jpg", "jpeg") or ct in ("image/jpeg", "image/jpg"):
        return "jpg"
    if ext == "svg" or ct in ("image/svg+xml", "image/svg"):
        return "svg"
    if ext == "pdf" or ct == "application/pdf":
        return "pdf"
    return None


def store_upload(
    *,
    tenant_id: UUID,
    site_id: UUID,
    plan_id: UUID,
    filename: str,
    content_type: str,
    content: bytes,
) -> UploadResult:
    """Persist the upload + (for PDFs) render to PNG.

    Raises ValueError for unsupported formats or oversized uploads.
    Raises S3Error for storage failures (caller logs and surfaces).
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit"
        )
    fmt = detect_format(filename, content_type)
    if fmt is None:
        raise ValueError(
            "Unsupported file type. Allowed: PNG, JPG, SVG, PDF"
        )

    ensure_bucket()
    client = _client()
    prefix = _prefix(tenant_id, site_id, plan_id)
    original_key = f"{prefix}/original.{fmt}"

    # Upload the original
    client.put_object(
        settings.MINIO_BUCKET,
        original_key,
        io.BytesIO(content),
        length=len(content),
        content_type=content_type,
    )

    rendered_key: str | None = None
    width_px: int
    height_px: int

    if fmt == "pdf":
        # Render first page to PNG and store as a companion
        png_bytes, width_px, height_px = _render_pdf_first_page(content)
        rendered_key = f"{prefix}/rendered.png"
        client.put_object(
            settings.MINIO_BUCKET,
            rendered_key,
            io.BytesIO(png_bytes),
            length=len(png_bytes),
            content_type="image/png",
        )
    elif fmt == "svg":
        width_px, height_px = _extract_svg_dimensions(content)
    else:
        # PNG / JPG — read dimensions via pymupdf's Pixmap. Avoids adding
        # Pillow as a dependency since pymupdf already handles raster images.
        try:
            pix = fitz.Pixmap(content)
            width_px = pix.width
            height_px = pix.height
            pix = None  # release the C-level resource
        except Exception as e:
            # Roll back the upload
            try:
                client.remove_object(settings.MINIO_BUCKET, original_key)
            except Exception:
                pass
            raise ValueError(f"Could not read image dimensions: {e}") from e

    log.info(
        "floor_plans.upload_stored",
        plan_id=str(plan_id),
        fmt=fmt,
        width=width_px,
        height=height_px,
        size_bytes=len(content),
    )

    return UploadResult(
        format=fmt,
        width_px=width_px,
        height_px=height_px,
        storage_key_original=original_key,
        storage_key_rendered=rendered_key,
        size_bytes=len(content),
    )


def open_for_streaming(
    storage_key: str,
) -> tuple[BinaryIO, int, str]:
    """Open a stored object for streaming back to the browser.

    Returns (stream, length, content_type). Caller must close the stream.
    """
    client = _client()
    obj = client.get_object(settings.MINIO_BUCKET, storage_key)
    length = int(obj.headers.get("Content-Length", 0))
    content_type = obj.headers.get("Content-Type", "application/octet-stream")
    return obj, length, content_type


def delete_plan_files(
    tenant_id: UUID, site_id: UUID, plan_id: UUID
) -> None:
    """Best-effort: delete every object under this plan's prefix.

    Called on FloorPlan row delete. Failures are logged but don't raise —
    we don't want orphan files to block a delete forever.
    """
    client = _client()
    prefix = _prefix(tenant_id, site_id, plan_id)
    try:
        objects = client.list_objects(
            settings.MINIO_BUCKET, prefix=prefix, recursive=True
        )
        for obj in objects:
            try:
                client.remove_object(settings.MINIO_BUCKET, obj.object_name)
            except S3Error as e:
                log.warning(
                    "floor_plans.delete_object_failed",
                    key=obj.object_name,
                    error=str(e),
                )
    except S3Error as e:
        log.warning(
            "floor_plans.delete_prefix_failed",
            prefix=prefix,
            error=str(e),
        )


# -- helpers ------------------------------------------------------------------


def _render_pdf_first_page(pdf_bytes: bytes) -> tuple[bytes, int, int]:
    """Render the first page of a PDF as a PNG at PDF_RENDER_DPI.

    Returns (png_bytes, width_px, height_px).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.page_count == 0:
        raise ValueError("PDF has no pages")
    try:
        page = doc.load_page(0)
        # Zoom = DPI / 72 (PDF native is 72 DPI)
        zoom = PDF_RENDER_DPI / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        png_bytes = pix.tobytes("png")
        return png_bytes, pix.width, pix.height
    finally:
        doc.close()


def _extract_svg_dimensions(svg_bytes: bytes) -> tuple[int, int]:
    """Try to read width/height from an SVG's viewBox or width/height attrs.

    Falls back to SVG_FALLBACK_W / SVG_FALLBACK_H if extraction fails.
    """
    try:
        import re

        text = svg_bytes.decode("utf-8", errors="ignore")
        # Try viewBox first (most authoritative)
        vb = re.search(
            r'viewBox=["\']\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*["\']',
            text,
        )
        if vb:
            return int(float(vb.group(3))), int(float(vb.group(4)))
        # Fall back to width/height attributes
        w = re.search(r'<svg[^>]*\swidth=["\']?([\d.]+)', text)
        h = re.search(r'<svg[^>]*\sheight=["\']?([\d.]+)', text)
        if w and h:
            return int(float(w.group(1))), int(float(h.group(1)))
    except Exception:
        pass
    return SVG_FALLBACK_W, SVG_FALLBACK_H
