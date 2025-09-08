# VideoStove CLI

Production-ready VideoStove CLI for RunPod GPU instances - preset-first, mode-aware, GPU-enforced video rendering.

[![CI](https://github.com/videostove/videostove-cli/workflows/CI/badge.svg)](https://github.com/videostove/videostove-cli/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://hub.docker.com/)

## Features

- 🎯 **Preset-first workflow**: Choose rendering presets before projects
- 🚀 **GPU-enforced**: Requires NVIDIA GPU, fails fast without it
- 🌐 **Remote-first**: Pull projects and assets from any rclone remote
- 📊 **Mode-aware**: Auto-detects slideshow/montage/videos_only modes
- 🔢 **Numeric UI**: Clean terminal interface optimized for headless use
- 📦 **RunPod optimized**: Docker container ready for GPU instances
- 🎬 **Real rendering**: No dummy outputs - integrates with VideoStove engine

## Quick Start

### Local Installation

```bash
# Clone and install
git clone https://github.com/videostove/videostove-cli.git
cd videostove-cli
pip install -e .

# Run interactive wizard
videostove wizard --root ./workspace --remote gdrive:VideoStove
```

### Docker (Recommended for RunPod)

```bash
# Build image
docker build -t videostove-cli .

# Run with environment setup
docker run --rm --gpus all \
  -e RCLONE_CONFIG_BASE64="your_base64_config" \
  -e REMOTE_BASE="gdrive:VideoStove" \
  videostove-cli
```

## RunPod Usage

### Environment Variables

**Required** (choose one):
- `RCLONE_CONFIG_BASE64` - Full base64-encoded rclone config file
- `RCLONE_DRIVE_SERVICE_ACCOUNT_JSON` + `RCLONE_REMOTE_NAME` - Service account setup

**Optional**:
- `REMOTE_BASE` - Default remote path (e.g., `gdrive:VideoStove`)
- `ALLOW_CPU=1` - Debug mode to bypass GPU requirement (not recommended)

### Example Configurations

#### Option 1: Base64 Config (Recommended)

1. Create rclone config locally: `rclone config`
2. Encode config: `base64 -w 0 ~/.config/rclone/rclone.conf`
3. Set in RunPod:

```bash
RCLONE_CONFIG_BASE64=W2dkcml2ZV0KdHlwZSA9IGRyaXZlCmNsaWVudF9pZCA9IHlvdXJfY2xpZW50X2lkLmNvbQ==
REMOTE_BASE=gdrive:VideoStove
```

#### Option 2: Service Account

```bash
RCLONE_DRIVE_SERVICE_ACCOUNT_JSON={"type": "service_account", "project_id": "your-project"...}
RCLONE_REMOTE_NAME=gdrive
REMOTE_BASE=gdrive:VideoStove
```

### RunPod Commands

#### Interactive Wizard
```bash
# Default: interactive mode with remote from environment
videostove wizard --root /workspace/videostove_root
```

#### Non-Interactive Batch Processing
```bash
# Process all projects with specific preset
videostove wizard \
  --root /workspace/videostove_root \
  --remote gdrive:VideoStove \
  --preset twovet_2025.json \
  --select all \
  --yes --push
```

#### Utility Commands
```bash
# Check system status
videostove doctor

# Pull specific projects only
videostove pull --remote gdrive:VideoStove --projects "project1,project2"

# Push outputs after manual rendering
videostove push --remote gdrive:VideoStove --projects all

# Scan local projects
videostove scan --root /workspace/videostove_root --json
```

## Directory Structure

### Remote Structure (rclone)
```
<REMOTE_BASE>/
├── assets/                    # Shared assets
│   ├── presets/              # Preset JSON files
│   │   ├── slideshow.json
│   │   └── montage.json
│   ├── overlays/             # Video overlays
│   ├── fonts/                # Font files
│   └── bgmusic/              # Background music
├── project1/                 # Project directories
│   ├── assets/               # Per-project assets (optional)
│   ├── img1.jpg
│   ├── img2.png
│   └── main_audio.wav
├── project2/
│   ├── video1.mp4
│   └── video2.mov
└── outputs/                  # Rendered outputs
    ├── project1/
    └── project2/
```

### Local Workspace
```
/workspace/videostove_root/
├── assets/                   # Pulled from remote/assets
│   ├── presets/
│   ├── overlays/
│   └── bgmusic/
├── project1/                 # Pulled projects
│   ├── assets/               # Per-project assets
│   ├── out/                  # Local render outputs
│   │   ├── project1_slideshow.mp4
│   │   └── project1_slideshow.manifest.json
│   ├── img1.jpg
│   └── main_audio.wav
└── project2/
    ├── out/
    ├── video1.mp4
    └── video2.mov
```

## Workflow Details

### 1. Preset-First Selection
- Pulls shared assets including presets
- User selects preset before seeing projects
- Mode is detected from preset (`project_type`)
- Can override mode with `--mode` flag

### 2. Project Filtering
- Lists available remote projects
- Scans each for media content
- Filters eligibility by render mode:
  - `slideshow`: Requires images ≥1, videos = 0
  - `montage`: Requires videos ≥1 (images optional)  
  - `videos_only`: Requires videos ≥1 (images ignored)

### 3. Asset Selection
- Finds available overlays, fonts, background music
- Allows selection for all projects or per-project
- Assets pulled from both shared and per-project locations

### 4. GPU-Enforced Rendering
- Verifies GPU via `nvidia-smi -L`
- Checks PyTorch CUDA availability
- Forces engine to use CUDA settings
- Calls VideoStove engine with real media files

### 5. Output Management
- Creates manifest files with render metadata
- Optionally pushes outputs to `<remote>/outputs/<project>/`
- Provides detailed success/failure reporting

## Preset Format

VideoStove CLI supports preset exports from the main VideoStove application:

```json
{
  "metadata": {
    "export_type": "videostove_preset",
    "export_date": "2025-01-15T10:30:00",
    "videostove_version": "1.0"
  },
  "preset": {
    "my_preset": {
      "project_type": "slideshow",
      "image_duration": 8.0,
      "use_crossfade": true,
      "crossfade_duration": 0.6,
      "crf": 22,
      "use_gpu": true,
      "animation_style": "Sequential Motion"
    }
  }
}
```

### Key Preset Fields
- `project_type`: `"slideshow"`, `"montage"`, or `"videos_only"`
- `image_duration`: Seconds per image
- `use_crossfade`: Enable crossfade transitions
- `crossfade_duration`: Crossfade duration in seconds
- `crf`: Video quality (0-51, lower = higher quality)
- `use_gpu`: GPU acceleration flag
- `animation_style`: Motion type for images

## API Reference

### Main Commands

#### `videostove wizard`
Main rendering wizard with preset-first workflow.

**Arguments:**
- `--root PATH` - Working directory (default: `/workspace/videostove_root`)
- `--remote REMOTE` - rclone remote path (e.g., `gdrive:VideoStove`)
- `--preset NAME` - Preset name or path
- `--select PROJECTS` - Select projects: `all` or `name1,name2`
- `--mode MODE` - Override preset mode: `slideshow|montage|videos_only`
- `--overlay PATH` - Overlay video file
- `--font PATH` - Font file  
- `--bgm PATH` - Background music file
- `--show-read` - Show detailed configuration readout
- `--yes` - Auto-confirm all prompts
- `--push / --no-push` - Push outputs to remote

#### `videostove pull`
Pull projects and assets from remote.

**Arguments:**
- `--remote REMOTE` - rclone remote path (required)
- `--root PATH` - Working directory
- `--projects NAMES` - Projects: `all` or `name1,name2`
- `--shared-only` - Pull only shared assets

#### `videostove push`
Push rendered outputs to remote.

**Arguments:**
- `--remote REMOTE` - rclone remote path (required)
- `--root PATH` - Working directory  
- `--projects NAMES` - Projects: `all` or `name1,name2`

#### `videostove scan`
Scan local projects for media.

**Arguments:**
- `--root PATH` - Working directory
- `--json` - Output as JSON

#### `videostove doctor`
Check system requirements and configuration.

#### `videostove rclone-setup`  
Setup rclone configuration from environment variables.

## GPU Requirements

VideoStove CLI **requires** NVIDIA GPU for rendering:

- NVIDIA GPU with CUDA support
- `nvidia-smi` command available
- PyTorch installed with CUDA support
- Docker: `--gpus all` flag required

**Debug bypass**: Set `ALLOW_CPU=1` to run without GPU (very slow, not recommended for production).

## Troubleshooting

### rclone Issues

**Problem**: Remote verification failed
**Solution**: 
- Check `RCLONE_CONFIG_BASE64` is properly encoded
- Verify service account JSON is valid
- Test with: `rclone lsf <your_remote>:`

**Problem**: No remotes configured
**Solution**:
- Run `videostove rclone-setup` to create config
- Check environment variables are set correctly
- Manually test: `rclone listremotes`

### GPU Issues

**Problem**: No NVIDIA GPU detected
**Solution**:
- Ensure `--gpus all` flag in Docker
- Check `nvidia-smi -L` works
- Verify RunPod instance has GPU

**Problem**: PyTorch CUDA not available  
**Solution**:
- Container uses PyTorch with CUDA pre-installed
- For local install: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118`

### Rendering Issues

**Problem**: No projects eligible for mode
**Solution**:
- Check project media content matches mode requirements
- Use `videostove scan` to inspect media
- Override mode with `--mode` if needed

**Problem**: Preset not found
**Solution**:
- Ensure presets are in `assets/presets/` directory
- Use full path with `--preset /path/to/preset.json`
- Check preset JSON format is valid

## Development

### Local Development Setup

```bash
git clone https://github.com/videostove/videostove-cli.git
cd videostove-cli
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -e .[dev]
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=videostove_cli

# Run specific test file
pytest tests/test_preset_detect.py -v
```

### Code Quality

```bash
# Format code
black videostove_cli tests

# Sort imports  
isort videostove_cli tests

# Lint
flake8 videostove_cli
```

### Building Docker Image

```bash
docker build -t videostove-cli .
docker run --rm --gpus all videostove-cli doctor
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run quality checks: `black`, `isort`, `flake8`, `pytest`
5. Submit pull request

## Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/videostove/videostove-cli/issues)
- 📖 **Documentation**: This README and inline code documentation
- 🚀 **RunPod**: Optimized for RunPod GPU instances with CUDA support