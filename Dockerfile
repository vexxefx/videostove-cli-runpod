# syntax=docker/dockerfile:1

FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04
ARG DEBIAN_FRONTEND=noninteractive

# Base tools + ffmpeg + yq + rclone + dos2unix (to fix CRLF on scripts)
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv ffmpeg curl jq git unzip wget ca-certificates dos2unix \
  && rm -rf /var/lib/apt/lists/* \
  && curl -fsSL https://rclone.org/install.sh | bash \
  && wget -q https://github.com/mikefarah/yq/releases/download/v4.44.2/yq_linux_amd64 -O /usr/bin/yq \
  && chmod +x /usr/bin/yq

# Environment
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/root/.local/bin:${PATH}" \
    PYTHONPATH="/app" \
    RUN_MAIN_PATH="/app/run_main.py"

WORKDIR /app

# Python deps
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# App code
COPY . /app

# Ensure scripts are executable and LF-ended
RUN dos2unix /app/start.sh || true && chmod +x /app/start.sh

# Runtime work dirs
RUN mkdir -p /workspace/assets /workspace/jobs /workspace/projects /workspace/output

ENTRYPOINT ["/app/start.sh"]
