"""Configuration constants for VideoStove CLI"""

from pathlib import Path

# File extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac"}

# Directories to skip during media scan
SKIP_DIRS = {"assets", "out", "outputs", "__pycache__", ".git", ".vscode"}

# Default paths
DEFAULT_ROOT = Path("/workspace/videostove_root")
DEFAULT_RCLONE_CONFIG = Path("/workspace/.config/rclone/rclone.conf")

# Render modes
RENDER_MODES = {"slideshow", "montage", "videos_only"}

# Preset keys that affect rendering
PRESET_KEYS = {
    "project_type", "image_duration", "main_audio_vol", "bg_vol", 
    "crossfade_duration", "use_crossfade", "use_overlay", "use_bg_music",
    "use_gpu", "use_fade_in", "use_fade_out", "overlay_opacity", "crf", 
    "preset", "videos_as_intro_only", "overlay_mode", "extended_zoom_enabled",
    "extended_zoom_direction", "extended_zoom_amount", "single_image_zoom",
    "captions_enabled", "caption_style", "animation_style", "loop_videos",
    "use_videos", "auto_clear_console"
}