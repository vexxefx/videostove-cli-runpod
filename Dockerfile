# VideoStove CLI - Production Docker Image for RunPod GPU instances
FROM runpod/pytorch:3.10-2.1.2-12.1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install rclone
RUN curl -fsSL https://rclone.org/install.sh | bash

# Set up workspace
WORKDIR /workspace
ENV PYTHONUNBUFFERED=1 \
    RCLONE_CONFIG=/workspace/.config/rclone/rclone.conf \
    PATH="/workspace/.local/bin:$PATH"

# Copy source code
COPY videostove_cli /workspace/videostove_cli
COPY run_main.py /workspace/run_main.py
COPY pyproject.toml /workspace/pyproject.toml
COPY README.md /workspace/README.md
COPY entrypoint.sh /workspace/entrypoint.sh

# Make entrypoint executable
RUN chmod +x /workspace/entrypoint.sh

# Install VideoStove CLI
RUN python -m pip install --upgrade pip && \
    pip install -e .

# Create default working directory
RUN mkdir -p /workspace/videostove_root

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD nvidia-smi -L || exit 1

# Set entrypoint
ENTRYPOINT ["/workspace/entrypoint.sh"]
CMD ["wizard"]