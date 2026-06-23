# =============================================================================
# AI Worker — DeepStream variant (P2)
#
# Forks deepstream_visitor_reid into a VisionTrack-aware container that:
#   - Reuses the existing deepstream-metaxperts:latest image (DS 7.1 base
#     with pyds + Triton + librealsense + UCX + custom additions)
#   - Adds the Python deps the original ai-worker uses (httpx, redis,
#     structlog, pydantic-settings) so we get the same code conventions
#   - Mounts models read-only from the host's deepstream_visitor_reid/
#     directory (models are too big to bake into the image)
#
# This batch (P2.2) ships the container that decodes RTSP and runs the
# detection + tracking inference chain on GPU. It does NOT yet publish
# to Redis Streams or extract embeddings — those are P2.3 and P2.4.
# =============================================================================

FROM deepstream-metaxperts:latest

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Python deps for the VisionTrack control plane (camera discovery,
# Redis publishing, structured logging, pydantic settings). DeepStream
# itself + pyds are already installed in the base image.
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# App code

# YOLO custom parser (built from marcoslucianops/DeepStream-Yolo against this
# image's DS 7.1 + CUDA 12.6 headers). The .so was compiled in ./external and
# is baked into the image so we don't have to mount it at runtime.
COPY external/DeepStream-Yolo/nvdsinfer_custom_impl_Yolo/libnvdsinfer_custom_impl_Yolo.so /opt/yolo/libnvdsinfer_custom_impl_Yolo.so

WORKDIR /workspace
COPY app/ /workspace/app/
COPY configs/ /workspace/configs/

# Override the base image's entrypoint (which runs main_udp.py) and the
# CMD; we want our own main.py.
ENTRYPOINT []
CMD ["python3", "-u", "-m", "app.main"]
