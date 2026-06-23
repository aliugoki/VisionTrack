# =============================================================================
# MediaMTX + NVIDIA-accelerated FFmpeg (built from source)
#
# We compile FFmpeg with --enable-nvenc --enable-cuvid on top of NVIDIA's
# official CUDA runtime image. This is the canonical approach documented
# at https://docs.nvidia.com/video-technologies/video-codec-sdk/
#
# First build: ~5-8 minutes (FFmpeg compilation).
# Subsequent builds: seconds (Docker layer cache).
#
# Runtime requirements:
#   - NVIDIA Container Toolkit installed on host
#   - docker-compose service declares `runtime: nvidia`
#   - NVIDIA_VISIBLE_DEVICES=all in environment
# =============================================================================

# Stage 1 — grab the mediamtx binary from its official image
FROM bluenviron/mediamtx:1.9.3 AS mediamtx-binary

# Stage 2 — build FFmpeg with NVENC/NVDEC support on CUDA base
# Using cuda 12.4 runtime (matches what's commonly available with recent
# NVIDIA Container Toolkit installs). We need the -devel image to get
# the CUDA headers needed during the FFmpeg compile.
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS ffmpeg-builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    git \
    wget \
    yasm \
    nasm \
    libssl-dev \
    libx264-dev \
    libnuma-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# NVIDIA codec headers — provides nvenc/nvdec/cuvid C headers FFmpeg needs
RUN git clone --depth 1 --branch n12.2.72.0 \
    https://git.videolan.org/git/ffmpeg/nv-codec-headers.git /tmp/nv-codec-headers \
    && cd /tmp/nv-codec-headers \
    && make install \
    && cd / && rm -rf /tmp/nv-codec-headers

# FFmpeg with NVENC + NVDEC + CUDA accel
# FFmpeg with NVENC + NVDEC + CUDA accel.
# Source from GitHub mirror because git.ffmpeg.org has intermittent
# TLS/connection failures from many networks.
RUN git clone --depth 1 --branch n7.1 \
    https://github.com/FFmpeg/FFmpeg.git /tmp/ffmpeg \
    && cd /tmp/ffmpeg \
    && ./configure \
        --prefix=/usr/local \
        --enable-gpl \
        --enable-nonfree \
        --enable-cuda-nvcc \
        --enable-libnpp \
        --enable-cuvid \
        --enable-nvenc \
        --enable-libx264 \
        --enable-openssl \
        --extra-cflags=-I/usr/local/cuda/include \
        --extra-ldflags=-L/usr/local/cuda/lib64 \
        --disable-debug \
        --disable-doc \
    && make -j"$(nproc)" \
    && make install \
    && cd / && rm -rf /tmp/ffmpeg

# Stage 3 — runtime image
# Use the CUDA runtime (smaller than devel, no compiler/headers needed at runtime)
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Runtime libs needed by our compiled FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libx264-163 \
    libssl3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the FFmpeg binaries we built
COPY --from=ffmpeg-builder /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg-builder /usr/local/bin/ffprobe /usr/local/bin/ffprobe
COPY --from=ffmpeg-builder /usr/local/lib/ /usr/local/lib/
RUN ldconfig

# MediaMTX binary
COPY --from=mediamtx-binary /mediamtx /mediamtx

# Quick sanity check during build — fails fast if FFmpeg doesn't have nvenc
RUN /usr/local/bin/ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_nvenc \
    && echo "OK: ffmpeg has h264_nvenc encoder" \
    || (echo "FAIL: ffmpeg was built without h264_nvenc" && exit 1)

CMD ["/mediamtx", "/mediamtx.yml"]