#!/usr/bin/env bash
set -euo pipefail

# VideoStove CLI Docker Entrypoint
# Handles rclone setup, GPU verification, and command execution

echo "🚀 VideoStove CLI - Starting up..."

# Create rclone config directory
mkdir -p "$(dirname "${RCLONE_CONFIG:-/workspace/.config/rclone/rclone.conf}")"

# Step 1: Setup rclone configuration from environment (headless)
echo "⚙️ Setting up rclone configuration..."
python3 -c "
from videostove_cli import rclone_setup
try:
    if rclone_setup.materialize_config_from_env():
        print('✅ rclone configuration created successfully')
    else:
        print('⚠️ No rclone environment variables found')
        print('   Set RCLONE_CONFIG_BASE64 or RCLONE_DRIVE_SERVICE_ACCOUNT_JSON')
except Exception as e:
    print(f'❌ rclone setup failed: {e}')
    exit(1)
"

# Step 2: GPU verification (required unless ALLOW_CPU=1 for debug)
if [[ "${ALLOW_CPU:-0}" != "1" ]]; then
    echo "🔍 Verifying GPU availability..."
    
    if ! nvidia-smi -L >/dev/null 2>&1; then
        echo "❌ ERROR: No NVIDIA GPU detected via nvidia-smi"
        echo "   This container requires GPU access for video rendering"
        echo "   Set ALLOW_CPU=1 to bypass (debug only, not recommended)"
        exit 3
    fi
    
    # Additional PyTorch CUDA check
    python3 -c "
import torch
if not torch.cuda.is_available():
    print('❌ ERROR: PyTorch CUDA not available')
    print('   Ensure PyTorch was installed with CUDA support')
    exit(3)
else:
    device_count = torch.cuda.device_count()
    print(f'✅ GPU verified: {device_count} CUDA device(s) available')
"
    
else
    echo "⚠️ WARNING: Running in CPU mode (ALLOW_CPU=1 set)"
    echo "   This is for debugging only and will be very slow"
fi

# Step 3: Optional remote verification
if [[ -n "${REMOTE_BASE:-}" ]]; then
    echo "🌐 Verifying remote access: ${REMOTE_BASE}"
    
    python3 -c "
import os, sys
from videostove_cli import rclone_setup
remote = os.environ['REMOTE_BASE']
if rclone_setup.verify_remote(remote):
    print(f'✅ Remote verified: {remote}')
else:
    print(f'❌ Remote verification failed: {remote}')
    print('   Check your rclone configuration and remote path')
    exit(2)
"
fi

# Step 4: Execute command
echo "🎬 Starting VideoStove CLI..."

if [[ $# -gt 0 ]]; then
    # Run with provided arguments
    exec videostove "$@"
else
    # Default to interactive wizard with remote from environment
    if [[ -n "${REMOTE_BASE:-}" ]]; then
        exec videostove wizard --root /workspace/videostove_root --remote "${REMOTE_BASE}"
    else
        exec videostove wizard --root /workspace/videostove_root
    fi
fi