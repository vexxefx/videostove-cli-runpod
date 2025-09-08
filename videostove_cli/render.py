"""
GPU-enforced rendering integration with run_main.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .media_scan import scan_project_media


class RenderError(Exception):
    """Exception raised for rendering failures"""
    pass


def gpu_visible_via_nvidia_smi() -> bool:
    """
    Check if NVIDIA GPU is visible via nvidia-smi
    
    Returns:
        True if nvidia-smi shows GPUs, False otherwise
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0 and "GPU" in result.stdout
    except FileNotFoundError:
        return False
    except Exception:
        return False


def torch_cuda_available() -> bool:
    """
    Check if PyTorch CUDA is available
    
    Returns:
        True if torch.cuda.is_available(), False otherwise
    """
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False
    except Exception:
        return False


def require_gpu_or_exit() -> None:
    """
    Require GPU availability or exit with error
    
    Exits with code 3 if GPU not available (unless ALLOW_CPU=1 for debug)
    """
    if os.environ.get("ALLOW_CPU") == "1":
        print("⚠️ WARNING: Running in CPU mode (ALLOW_CPU=1 set)")
        return
    
    gpu_nvidia = gpu_visible_via_nvidia_smi()
    gpu_torch = torch_cuda_available()
    
    if not gpu_nvidia:
        print("❌ ERROR: No NVIDIA GPU detected via nvidia-smi")
        print("   Set ALLOW_CPU=1 to bypass (debug only)")
        sys.exit(3)
    
    if not gpu_torch:
        print("❌ ERROR: PyTorch CUDA not available")
        print("   Ensure PyTorch is installed with CUDA support")
        print("   Set ALLOW_CPU=1 to bypass (debug only)")
        sys.exit(3)
    
    print("✅ GPU available: nvidia-smi + torch.cuda")


def enforce_engine_gpu(vs_module) -> None:
    """
    Patch videostove engine CONFIG with GPU settings
    
    Args:
        vs_module: Imported run_main module
    """
    gpu_config = {
        "use_gpu": True,
        "gpu_mode": "cuda",
        "device": "cuda",
    }
    
    # Update CONFIG with GPU enforcement
    for key, value in gpu_config.items():
        if hasattr(vs_module, 'CONFIG') and key in vs_module.CONFIG:
            vs_module.CONFIG[key] = value
        # Also try to set on DEFAULT_CONFIG if it exists
        if hasattr(vs_module, 'DEFAULT_CONFIG') and key in vs_module.DEFAULT_CONFIG:
            vs_module.DEFAULT_CONFIG[key] = value
    
    print(f"🚀 Enforced GPU settings: {gpu_config}")


def prepare_media_for_mode(media_info: Dict, mode: str) -> Dict:
    """
    Prepare media file lists based on render mode
    
    Args:
        media_info: Media info from scan_project_media
        mode: Render mode
        
    Returns:
        Dict with prepared file lists:
        {
            "images": List[str],
            "videos": List[str],
            "main_audio": Optional[str],
        }
    """
    images = []
    videos = []
    
    if mode == "slideshow":
        # Slideshow: images only, no videos
        images = [str(p) for p in media_info["images"]]
        videos = []
        
    elif mode == "videos_only":
        # Videos only: no images
        images = []
        videos = [str(p) for p in media_info["videos"]]
        
    elif mode == "montage":
        # Montage: both images and videos
        images = [str(p) for p in media_info["images"]]
        videos = [str(p) for p in media_info["videos"]]
    
    main_audio = str(media_info["main_audio"]) if media_info["main_audio"] else None
    
    return {
        "images": images,
        "videos": videos,
        "main_audio": main_audio,
    }


def create_render_manifest(
    project_dir: Path,
    output_path: Path,
    preset_config: Dict,
    mode: str,
    assets: Dict,
    media_counts: Dict
) -> Path:
    """
    Create a render manifest file with metadata
    
    Args:
        project_dir: Project directory
        output_path: Output video file path
        preset_config: Preset configuration used
        mode: Render mode
        assets: Asset file paths used
        media_counts: Media file counts
        
    Returns:
        Path to created manifest file
    """
    manifest_path = output_path.with_suffix('.manifest.json')
    
    manifest_data = {
        "videostove_cli": {
            "version": "1.0.0",
            "render_date": None,  # Will be set during render
        },
        "project": {
            "name": project_dir.name,
            "path": str(project_dir),
            "mode": mode,
        },
        "output": {
            "file": str(output_path),
            "size_bytes": None,  # Will be set after render
        },
        "preset": preset_config,
        "assets": {
            "overlay": str(assets.get("overlay")) if assets.get("overlay") else None,
            "font": str(assets.get("font")) if assets.get("font") else None,
            "bgm": str(assets.get("bgm")) if assets.get("bgm") else None,
        },
        "media": media_counts,
    }
    
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
    
    return manifest_path


def render_project(
    project_dir: Path,
    out_path: Path,
    preset_config: Dict,
    mode: str,
    overlay: Optional[Path] = None,
    font: Optional[Path] = None,
    bgm: Optional[Path] = None,
    show_read: bool = False
) -> bool:
    """
    Render a project using the VideoStove engine
    
    Args:
        project_dir: Project directory path
        out_path: Output video file path
        preset_config: Preset configuration dictionary
        mode: Render mode ("slideshow", "montage", "videos_only")
        overlay: Optional overlay video file
        font: Optional font file
        bgm: Optional background music file
        show_read: Whether to show detailed readout
        
    Returns:
        True if render succeeded, False otherwise
        
    Raises:
        RenderError: If render fails
    """
    from datetime import datetime
    
    print(f"\n🎬 Starting render: {project_dir.name}")
    print(f"   Mode: {mode}")
    print(f"   Output: {out_path}")
    
    # Step 1: GPU requirement check
    require_gpu_or_exit()
    
    # Step 2: Scan project media
    print("📊 Scanning project media...")
    media_info = scan_project_media(project_dir)
    
    if show_read:
        from .media_scan import format_media_summary
        print(f"\n{format_media_summary(media_info, project_dir.name)}")
    
    # Step 3: Prepare media for mode
    prepared_media = prepare_media_for_mode(media_info, mode)
    
    print(f"   📁 Images: {len(prepared_media['images'])}")
    print(f"   🎬 Videos: {len(prepared_media['videos'])}")
    if prepared_media['main_audio']:
        print(f"   🎵 Main Audio: {Path(prepared_media['main_audio']).name}")
    
    # Step 4: Import and configure engine
    print("⚙️ Configuring VideoStove engine...")
    
    try:
        # Import run_main from parent directory
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import run_main as vs
    except ImportError as e:
        raise RenderError(f"Failed to import run_main.py: {e}")
    
    # Update engine CONFIG with preset
    vs.CONFIG.update(preset_config)
    vs.CONFIG["project_type"] = mode  # Force mode override
    
    # Enforce GPU settings
    enforce_engine_gpu(vs)
    
    if show_read:
        from .presets import get_preset_summary
        summary = get_preset_summary(vs.CONFIG)
        print("\n📋 Active Configuration:")
        for key, value in summary.items():
            print(f"   {key}: {value}")
    
    # Step 5: Create output directory
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Step 6: Create render manifest
    media_counts = {
        "images": len(prepared_media["images"]),
        "videos": len(prepared_media["videos"]), 
        "audio": len(media_info["audio"]),
        "total_size_mb": round(media_info["total_size"] / (1024 * 1024), 1),
    }
    
    assets = {
        "overlay": overlay,
        "font": font,
        "bgm": bgm,
    }
    
    manifest_path = create_render_manifest(
        project_dir, out_path, preset_config, mode, assets, media_counts
    )
    
    # Step 7: Run render
    print("🚀 Starting VideoStove render...")
    start_time = datetime.now()
    
    try:
        # Create VideoCreator instance
        def update_callback(message):
            print(f"   {message}")
        
        vc = vs.VideoCreator(update_callback=update_callback)
        
        # Call create_slideshow (handles all modes)
        success = vc.create_slideshow(
            image_files=prepared_media["images"],
            video_files=prepared_media["videos"],
            main_audio=prepared_media["main_audio"],
            bg_music=str(bgm) if bgm else None,
            overlay_video=str(overlay) if overlay else None,
            output_file=str(out_path),
        )
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        if success and out_path.exists():
            # Update manifest with final info
            manifest_data = json.loads(manifest_path.read_text())
            manifest_data["videostove_cli"]["render_date"] = end_time.isoformat()
            manifest_data["output"]["size_bytes"] = out_path.stat().st_size
            manifest_data["render_duration_seconds"] = duration.total_seconds()
            
            manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False))
            
            print(f"✅ Render completed successfully!")
            print(f"   Duration: {duration}")
            print(f"   Output: {out_path}")
            print(f"   Size: {out_path.stat().st_size / (1024*1024):.1f} MB")
            print(f"   Manifest: {manifest_path}")
            
            return True
            
        else:
            print(f"❌ Render failed - output file not created")
            return False
            
    except Exception as e:
        end_time = datetime.now()
        duration = end_time - start_time
        
        print(f"❌ Render failed after {duration}")
        print(f"   Error: {e}")
        
        # Update manifest with error info
        try:
            manifest_data = json.loads(manifest_path.read_text())
            manifest_data["videostove_cli"]["render_date"] = end_time.isoformat()
            manifest_data["error"] = str(e)
            manifest_data["render_duration_seconds"] = duration.total_seconds()
            manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False))
        except:
            pass
        
        raise RenderError(f"Render failed: {e}")


def doctor_gpu() -> Dict:
    """
    Check GPU availability and configuration
    
    Returns:
        Dict with GPU diagnostic information
    """
    result = {
        "nvidia_smi_available": False,
        "nvidia_gpus": [],
        "torch_available": False,
        "torch_cuda_available": False,
        "cuda_device_count": 0,
        "allow_cpu_set": os.environ.get("ALLOW_CPU") == "1",
    }
    
    # Check nvidia-smi
    try:
        cmd_result = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            check=False
        )
        if cmd_result.returncode == 0:
            result["nvidia_smi_available"] = True
            # Parse GPU lines
            for line in cmd_result.stdout.strip().split('\n'):
                if line.startswith('GPU '):
                    result["nvidia_gpus"].append(line.strip())
    except FileNotFoundError:
        pass
    
    # Check PyTorch
    try:
        import torch
        result["torch_available"] = True
        result["torch_cuda_available"] = torch.cuda.is_available()
        if result["torch_cuda_available"]:
            result["cuda_device_count"] = torch.cuda.device_count()
    except ImportError:
        pass
    
    return result