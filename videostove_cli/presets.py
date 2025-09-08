"""
Preset loading, parsing, and mode detection
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import PRESET_KEYS, RENDER_MODES


class PresetError(Exception):
    """Exception raised for preset-related errors"""
    pass


def load_preset_file(preset_path: Path) -> Dict:
    """
    Load a preset JSON file
    
    Args:
        preset_path: Path to preset file
        
    Returns:
        Raw preset data dictionary
        
    Raises:
        PresetError: If loading fails
    """
    try:
        with open(preset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        raise PresetError(f"Preset file not found: {preset_path}")
    except json.JSONDecodeError as e:
        raise PresetError(f"Invalid JSON in preset file {preset_path}: {e}")
    except Exception as e:
        raise PresetError(f"Failed to load preset file {preset_path}: {e}")


def extract_preset_profiles(preset_data: Dict) -> Dict[str, Dict]:
    """
    Extract preset profiles from loaded data
    
    Handles different preset formats:
    - Export format: {"preset": {"name": {...}}}  
    - Direct format: {"name": {...}}
    - Single config format: {"project_type": "...", ...}
    
    Args:
        preset_data: Raw preset data
        
    Returns:
        Dict mapping profile names to configurations
        
    Raises:
        PresetError: If no valid profiles found
    """
    profiles = {}
    
    # Format 1: Export format with "preset" wrapper
    if "preset" in preset_data and isinstance(preset_data["preset"], dict):
        profiles = preset_data["preset"]
    
    # Format 2: Direct profile collection
    elif all(isinstance(v, dict) for v in preset_data.values() if not k.startswith("metadata")):
        # Filter out metadata keys
        profiles = {k: v for k, v in preset_data.items() if not k.startswith("metadata")}
    
    # Format 3: Single configuration (detect by presence of preset keys)
    elif any(key in preset_data for key in PRESET_KEYS):
        # Use filename or "default" as profile name
        profiles = {"default": preset_data}
    
    if not profiles:
        raise PresetError("No valid preset profiles found in data")
    
    return profiles


def find_preset_files(search_paths: List[Path]) -> List[Tuple[str, Path]]:
    """
    Find all preset JSON files in the given paths
    
    Args:
        search_paths: List of directories to search
        
    Returns:
        List of (name, path) tuples for found presets
    """
    presets = []
    
    for search_path in search_paths:
        if not search_path.exists():
            continue
            
        # Look for JSON files
        for json_file in search_path.glob("*.json"):
            try:
                # Try to load to verify it's a valid preset
                data = load_preset_file(json_file)
                profiles = extract_preset_profiles(data)
                
                # Add each profile as a separate preset option
                if len(profiles) == 1:
                    # Single profile - use filename
                    name = json_file.stem
                    presets.append((name, json_file))
                else:
                    # Multiple profiles - use filename:profile format
                    for profile_name in profiles.keys():
                        name = f"{json_file.stem}:{profile_name}"
                        presets.append((name, json_file))
                        
            except PresetError:
                # Skip invalid preset files
                continue
    
    return sorted(presets)


def load_preset_config(preset_path: Path, profile_name: Optional[str] = None) -> Dict:
    """
    Load a specific preset configuration
    
    Args:
        preset_path: Path to preset file
        profile_name: Specific profile name (for multi-profile presets)
        
    Returns:
        Configuration dictionary
        
    Raises:
        PresetError: If loading or profile selection fails
    """
    data = load_preset_file(preset_path)
    profiles = extract_preset_profiles(data)
    
    # Select profile
    if profile_name:
        if profile_name not in profiles:
            available = ", ".join(profiles.keys())
            raise PresetError(f"Profile '{profile_name}' not found. Available: {available}")
        config = profiles[profile_name]
    else:
        if len(profiles) == 1:
            config = next(iter(profiles.values()))
        else:
            available = ", ".join(profiles.keys())
            raise PresetError(f"Multiple profiles found, specify one: {available}")
    
    return config


def detect_mode(config: Dict, project_path: Optional[Path] = None) -> str:
    """
    Detect render mode from preset configuration and optional project scan
    
    Args:
        config: Preset configuration dictionary
        project_path: Optional project path for fallback heuristic
        
    Returns:
        Render mode: "slideshow", "montage", or "videos_only"
    """
    # Method 1: Direct from config
    project_type = config.get("project_type", "").lower().strip()
    
    if project_type in RENDER_MODES:
        return project_type
    
    # Handle common variations
    mode_mapping = {
        "slide": "slideshow",
        "slides": "slideshow", 
        "photos": "slideshow",
        "images": "slideshow",
        "video": "montage",
        "videos": "videos_only",
        "movie": "montage",
        "clip": "montage",
    }
    
    for key, mode in mode_mapping.items():
        if key in project_type:
            return mode
    
    # Method 2: Fallback heuristic using project scan
    if project_path and project_path.exists():
        from .media_scan import scan_project_media
        
        try:
            media_info = scan_project_media(project_path)
            video_count = len(media_info["videos"])
            
            if video_count > 0:
                return "montage"
            else:
                return "slideshow"
                
        except Exception:
            # Scan failed, use default
            pass
    
    # Default fallback
    return "montage"


def get_preset_summary(config: Dict) -> Dict:
    """
    Extract key settings for display in readouts
    
    Args:
        config: Preset configuration
        
    Returns:
        Dict with key settings for display
    """
    summary = {}
    
    # Key settings to show
    key_settings = {
        "project_type": "Mode",
        "image_duration": "Image Duration (s)",
        "use_crossfade": "Crossfade",
        "crossfade_duration": "Crossfade Duration (s)",
        "use_overlay": "Overlay Enabled",
        "overlay_mode": "Overlay Mode",
        "use_bg_music": "Background Music",
        "animation_style": "Animation Style",
        "crf": "Quality (CRF)",
        "preset": "Encoding Preset",
        "use_gpu": "GPU Acceleration",
        "extended_zoom_enabled": "Extended Zoom",
        "captions_enabled": "Captions",
    }
    
    for config_key, display_name in key_settings.items():
        if config_key in config:
            value = config[config_key]
            
            # Format boolean values
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            
            summary[display_name] = value
    
    return summary


def validate_preset_config(config: Dict) -> List[str]:
    """
    Validate preset configuration and return list of issues
    
    Args:
        config: Preset configuration
        
    Returns:
        List of validation error messages (empty if valid)
    """
    issues = []
    
    # Check required fields
    required_fields = ["project_type"]
    for field in required_fields:
        if field not in config:
            issues.append(f"Missing required field: {field}")
    
    # Validate numeric ranges
    numeric_validations = {
        "image_duration": (0.1, 3600.0),
        "crossfade_duration": (0.0, 60.0),
        "main_audio_vol": (0.0, 10.0),
        "bg_vol": (0.0, 10.0),
        "overlay_opacity": (0.0, 1.0),
        "crf": (0, 51),
    }
    
    for field, (min_val, max_val) in numeric_validations.items():
        if field in config:
            value = config[field]
            if not isinstance(value, (int, float)):
                issues.append(f"{field} must be a number")
            elif not (min_val <= value <= max_val):
                issues.append(f"{field} must be between {min_val} and {max_val}")
    
    # Validate choice fields
    choice_validations = {
        "project_type": RENDER_MODES,
        "overlay_mode": {"simple", "screen_blend"},
        "preset": {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"},
    }
    
    for field, valid_choices in choice_validations.items():
        if field in config:
            value = str(config[field]).lower()
            if value not in valid_choices:
                issues.append(f"{field} must be one of: {', '.join(valid_choices)}")
    
    return issues