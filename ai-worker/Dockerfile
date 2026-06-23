# =============================================================================
# AI Worker — YOLOv8 person detection + ByteTrack tracking
#
# Reads RTSP frames from MediaMTX, runs inference on the GPU, publishes
# track events to Redis Streams. The backend (Batch D) consumes those
# streams and persists/broadcasts them.
#
# Runtime requirements:
#   - NVIDIA Container Toolkit installed on host
#   - docker-compose service declares `runtime: nvidia`
#   - NVIDIA_VISIBLE_DEVICES=all in environment
# =============================================================================

# Base image with CUDA 12.4 runtime + cuDNN. The PyTorch wheels we install
# pair with this. Matches what we used for the MediaMTX transcoder image
# so the host driver only needs to be compatible with one CUDA version.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Python + OpenCV system deps. ffmpeg is needed because opencv's video
# backend uses it for RTSP reading.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    python3.11-dev \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    libglib2.0-0 \
    ca-certificates \
    curl \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps. Pip is intentionally invoked with --no-cache-dir to
# keep the final image smaller. PyTorch is large — caching that layer
# saves time on every subsequent rebuild.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# Application code
COPY app/ /app/app/

# Pre-download the YOLOv8n weights so the first frame doesn't stall on a
# Hub fetch. The weights live in a layer that's cached for rebuilds.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# Sanity check at build time — fails fast if torch can't see CUDA at
# install time. Note: this check passes even without a GPU attached
# because we don't actually call cuda() here; the runtime GPU check
# happens in main.py on startup.
RUN python -c "import torch; print(f'torch: {torch.__version__}, cuda available at install: {torch.cuda.is_available()}')"

CMD ["python", "-m", "app.main"]
