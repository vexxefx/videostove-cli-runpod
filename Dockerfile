# VideoStove CLI - Production Docker Image for RunPod GPU instances
FROM runpod/pytorch:3.10-2.1.2-12.1

FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Install system deps
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-pip ffmpeg curl jq git unzip wget \
    && curl -s https://rclone.org/install.sh | bash

# Install yq (YAML processor)
RUN wget https://github.com/mikefarah/yq/releases/download/v4.44.2/yq_linux_amd64 -O /usr/bin/yq \
    && chmod +x /usr/bin/yq

# Set up working dir
WORKDIR /app

# Copy requirements first (to leverage caching)
COPY requirements.txt /app/
RUN pip3 install -r requirements.txt

# Copy the rest of your code
COPY . /app

# Make start.sh executable
RUN chmod +x /app/start.sh

ENTRYPOINT ["bash", "/app/start.sh"]
