"""
Media scanning and eligibility checking
"""

from pathlib import Path
from typing import Dict, List, Optional

from .config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, SKIP_DIRS


def scan_project_media(project_path: Path) -> Dict:
    """
    Recursively scan a project directory for media files
    
    Args:
        project_path: Path to project directory
        
    Returns:
        Dict with media file lists and metadata:
        {
            "images": [Path, ...],
            "videos": [Path, ...], 
            "audio": [Path, ...],
            "main_audio": Path or None,
            "total_size": int (bytes),
        }
    """
    if not project_path.exists():
        return {
            "images": [],
            "videos": [],
            "audio": [],
            "main_audio": None,
            "total_size": 0,
        }
    
    images = []
    videos = []
    audio = []
    total_size = 0
    
    # Walk directory tree
    for item in project_path.rglob("*"):
        # Skip if in excluded directory
        if any(skip_dir in item.parts for skip_dir in SKIP_DIRS):
            continue
            
        if not item.is_file():
            continue
            
        suffix = item.suffix.lower()
        
        # Categorize by extension
        if suffix in IMAGE_EXTENSIONS:
            images.append(item)
            total_size += item.stat().st_size
        elif suffix in VIDEO_EXTENSIONS:
            videos.append(item)
            total_size += item.stat().st_size
        elif suffix in AUDIO_EXTENSIONS:
            audio.append(item)
            total_size += item.stat().st_size
    
    # Sort all lists by name for consistent ordering
    images.sort()
    videos.sort()
    audio.sort()
    
    # Select main audio file
    main_audio = select_main_audio(audio)
    
    return {
        "images": images,
        "videos": videos,
        "audio": audio,
        "main_audio": main_audio,
        "total_size": total_size,
    }


def select_main_audio(audio_files: List[Path]) -> Optional[Path]:
    """
    Select the main audio file from a list
    
    Prefers files with "main" in the basename, otherwise returns first file
    
    Args:
        audio_files: List of audio file paths
        
    Returns:
        Path to main audio file, or None if no audio files
    """
    if not audio_files:
        return None
    
    # Look for files with "main" in the name
    main_candidates = [f for f in audio_files if "main" in f.stem.lower()]
    
    if main_candidates:
        return main_candidates[0]  # First match
    
    # Fallback to first file in sorted order
    return audio_files[0]


def check_project_eligibility(project_path: Path, mode: str) -> Dict:
    """
    Check if a project is eligible for the specified render mode
    
    Args:
        project_path: Path to project directory
        mode: Render mode ("slideshow", "montage", "videos_only")
        
    Returns:
        Dict with eligibility info:
        {
            "eligible": bool,
            "reason": str,
            "media_counts": Dict,
            "project_name": str,
        }
    """
    project_name = project_path.name
    media_info = scan_project_media(project_path)
    
    image_count = len(media_info["images"])
    video_count = len(media_info["videos"])
    
    media_counts = {
        "images": image_count,
        "videos": video_count,
        "audio": len(media_info["audio"]),
        "total_size_mb": round(media_info["total_size"] / (1024 * 1024), 1),
    }
    
    # Check eligibility based on mode
    eligible = False
    reason = ""
    
    if mode == "slideshow":
        # Slideshow: requires images ≥1 and videos == 0 (strict images-only)
        if image_count >= 1 and video_count == 0:
            eligible = True
            reason = f"✅ {image_count} images, no videos"
        elif video_count > 0:
            reason = f"❌ Contains {video_count} videos (slideshow requires images only)"
        else:
            reason = f"❌ No images found"
    
    elif mode in ("montage", "videos_only"):
        # Montage/videos_only: requires videos ≥1 (images optional)
        if video_count >= 1:
            eligible = True
            if image_count > 0:
                reason = f"✅ {video_count} videos, {image_count} images"
            else:
                reason = f"✅ {video_count} videos"
        else:
            reason = f"❌ No videos found (required for {mode})"
    
    else:
        reason = f"❌ Unknown mode: {mode}"
    
    return {
        "eligible": eligible,
        "reason": reason,
        "media_counts": media_counts,
        "project_name": project_name,
    }


def scan_multiple_projects(project_paths: List[Path], mode: str) -> Dict:
    """
    Scan multiple projects and return eligibility summary
    
    Args:
        project_paths: List of project directory paths
        mode: Render mode
        
    Returns:
        Dict with scan results:
        {
            "eligible": [Path, ...],
            "ineligible": [(Path, reason), ...],
            "summary": Dict,
        }
    """
    eligible = []
    ineligible = []
    
    total_images = 0
    total_videos = 0
    total_audio = 0
    total_size = 0
    
    for project_path in project_paths:
        result = check_project_eligibility(project_path, mode)
        
        if result["eligible"]:
            eligible.append(project_path)
        else:
            ineligible.append((project_path, result["reason"]))
        
        # Accumulate stats
        counts = result["media_counts"]
        total_images += counts["images"]
        total_videos += counts["videos"]
        total_audio += counts["audio"]
        total_size += counts["total_size_mb"]
    
    summary = {
        "total_projects": len(project_paths),
        "eligible_projects": len(eligible),
        "ineligible_projects": len(ineligible),
        "total_images": total_images,
        "total_videos": total_videos,
        "total_audio": total_audio,
        "total_size_mb": round(total_size, 1),
        "mode": mode,
    }
    
    return {
        "eligible": eligible,
        "ineligible": ineligible,
        "summary": summary,
    }


def find_asset_files(asset_dirs: List[Path]) -> Dict[str, List[Path]]:
    """
    Find available asset files in asset directories
    
    Args:
        asset_dirs: List of asset directory paths
        
    Returns:
        Dict categorizing found assets:
        {
            "overlays": [Path, ...],
            "fonts": [Path, ...],
            "bgmusic": [Path, ...],
        }
    """
    overlays = []
    fonts = []
    bgmusic = []
    
    font_extensions = {".ttf", ".otf", ".woff", ".woff2"}
    
    for asset_dir in asset_dirs:
        if not asset_dir.exists():
            continue
            
        # Look in subdirectories
        overlay_dir = asset_dir / "overlays"
        if overlay_dir.exists():
            for ext in VIDEO_EXTENSIONS:
                overlays.extend(overlay_dir.glob(f"*{ext}"))
        
        font_dir = asset_dir / "fonts"
        if font_dir.exists():
            for ext in font_extensions:
                fonts.extend(font_dir.glob(f"*{ext}"))
        
        bgmusic_dir = asset_dir / "bgmusic"
        if bgmusic_dir.exists():
            for ext in AUDIO_EXTENSIONS:
                bgmusic.extend(bgmusic_dir.glob(f"*{ext}"))
        
        # Also check root asset directory for direct files
        if asset_dir.is_dir():
            for item in asset_dir.iterdir():
                if item.is_file():
                    suffix = item.suffix.lower()
                    if suffix in VIDEO_EXTENSIONS:
                        overlays.append(item)
                    elif suffix in font_extensions:
                        fonts.append(item)
                    elif suffix in AUDIO_EXTENSIONS:
                        bgmusic.append(item)
    
    # Sort all lists
    overlays.sort()
    fonts.sort()
    bgmusic.sort()
    
    return {
        "overlays": overlays,
        "fonts": fonts,
        "bgmusic": bgmusic,
    }


def format_media_summary(media_info: Dict, project_name: str = "") -> str:
    """
    Format media scan results for display
    
    Args:
        media_info: Media info from scan_project_media
        project_name: Optional project name for header
        
    Returns:
        Formatted string summary
    """
    lines = []
    
    if project_name:
        lines.append(f"📁 {project_name}")
        lines.append("-" * (len(project_name) + 4))
    
    lines.append(f"🖼️  Images: {len(media_info['images'])}")
    lines.append(f"🎬 Videos: {len(media_info['videos'])}")
    lines.append(f"🎵 Audio: {len(media_info['audio'])}")
    
    if media_info['main_audio']:
        lines.append(f"🎼 Main Audio: {media_info['main_audio'].name}")
    
    size_mb = media_info['total_size'] / (1024 * 1024)
    if size_mb >= 1024:
        size_str = f"{size_mb/1024:.1f} GB"
    else:
        size_str = f"{size_mb:.1f} MB"
    
    lines.append(f"💾 Total Size: {size_str}")
    
    return "\n".join(lines)