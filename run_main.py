#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoStove - GPU-Accelerated Clean Python Backend
Complete GPU acceleration with AMD VCE/NVIDIA NVENC and detailed progress tracking.
Efficient universal pipeline for both image-only and mixed-media projects.
FIXED: No more accidental deletion or duplication of exported videos!
NEW: Videos as intro only - clean video intros followed by image slideshows!
"""

import os
import sys
import io

# Fix Windows console encoding issues
if sys.platform == "win32":
    try:
        # Try to set UTF-8 encoding for stdout
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        # Fallback: replace problematic characters
        pass
import shutil
import subprocess
import threading
import json
import queue
import tempfile
import time
import glob
import datetime
import math
from pathlib import Path
# Conditional webview import for headless/CLI compatibility
try:
    import webview
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False
    webview = None
try:
    import tkinter as tk
    from tkinter import filedialog
    HAS_TKINTER = True
except ImportError:
    print("⚠️  tkinter not available - file dialogs will use fallback method")
    HAS_TKINTER = False

# Default Configuration (for reset on startup)
DEFAULT_CONFIG = {
    "image_duration": 8.0,
    "main_audio_vol": 1.0,
    "bg_vol": 0.15,
    "crossfade_duration": 0.6,
    "use_crossfade": True,          # New option to enable/disable crossfades
    "use_overlay": False,
    "use_bg_music": True,
    "use_gpu": True,                # GPU acceleration enabled
    "use_fade_in": True,
    "use_fade_out": True,
    "overlay_opacity": 0.5,
    "crf": 22,
    "preset": "fast",
    
    # NEW: Video intro behavior
    "videos_as_intro_only": True,   # Use videos as intro, then images (no video looping when images present)
    "project_type": "montage",       # NEW: "slideshow", "montage", or "videos_only"
    "overlay_mode": "simple",        # NEW: "simple" or "screen_blend"
    "extended_zoom_enabled": False,  # NEW: For 1-5 images
    "extended_zoom_direction": "in", # NEW: "in" or "out"
    "extended_zoom_amount": 30,      # NEW: 0-50%
    "single_image_zoom": False,      # NEW: Special zoom for single image
    
    # Caption Settings
    "captions_enabled": False,
    "caption_style": "Custom",
    "caption_type": "single",
    "whisper_model": "base",
    "font_size": 24,
    "font_family": "Arial",
    "font_weight": "bold",
    "text_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "border_color": "#FFFFFF",
    "border_width": 2,
    "border_enabled": False,
    "single_line_mode": False,
    "background_color": "#000000",
    "background_opacity": 0.0,
    "use_caption_background": False,  # Explicit flag for background
    "vertical_position": "bottom",
    "horizontal_position": "center",
    "margin_vertical": 25,
    "margin_horizontal": 20,
    "preset_vertical_position": "bottom",
    "preset_horizontal_position": "center", 
    "preset_margin_vertical": 50,
    "preset_margin_horizontal": 20,
    "caption_animation": "normal",
    "shadow_enabled": True,
    "shadow_blur": 2,
    "line_spacing": 1.2,
    "word_by_word_enabled": False,    # Word-by-Word Mode (1-3 words)
    "live_timing_enabled": False,     # Live Timing Mode (single line)
    "karaoke_effect_enabled": False,  # Karaoke Effect (word-by-word timing)
    "use_faster_whisper": False,      # Use faster-whisper for all transcription (4-6x faster)
    "loop_videos": True,              # Loop videos if no images available
    "use_videos": True,               # Enable/disable video detection
    "max_chars_per_line": 45,         # Maximum characters per caption line
    "animation_style": "Sequential Motion", # Default animation style
    "auto_clear_console": False       # Auto-clear console when it gets too long
}

# Global Configuration (starts as copy of defaults)
CONFIG = DEFAULT_CONFIG.copy()

MOTION_DIRECTIONS = ["right", "left", "down", "up"]

def pick_motion_direction(animation_style: str, i: int, total_images: int) -> str:
    """Pick motion direction for image i based on animation style."""
    style = (animation_style or "Sequential Motion").strip()
    if style in ("Zoom In Only", "Zoom In"):
        return "zoom_in"
    if style in ("Zoom Out Only", "Zoom Out"):
        return "zoom_out"
    if style in ("Pan Only", "Pan"):
        return "right"
    if style in ("No Animation", "None"):
        return "no_motion"
    if style in ("Random Motion", "Random"):
        import random
        return random.choice(MOTION_DIRECTIONS + ["zoom_in", "zoom_out"])

    # Default: Sequential Motion
    if total_images <= 1 or i == 0:
        return "zoom_in"            # first image
    if i == total_images - 1:
        return "zoom_out"           # last image
    # Middle images rotate through pan directions
    return MOTION_DIRECTIONS[(i - 1) % len(MOTION_DIRECTIONS)]

# ===================================================================
# UTILITY FUNCTIONS
# ===================================================================

def format_path_for_ffmpeg(file_path):
    """Format file path for FFmpeg compatibility on Windows.
    Handles spaces, special characters, and path separators properly."""
    # Convert to absolute path and normalize
    abs_path = os.path.abspath(file_path)
    
    # On Windows, replace backslashes with forward slashes for FFmpeg
    if os.name == 'nt':  # Windows
        abs_path = abs_path.replace('\\', '/')
        # Handle drive letters (C: -> C:/ NOT /C:)
        # FFmpeg on Windows prefers C:/path format
        if len(abs_path) > 1 and abs_path[1] == ':':
            # Keep it as C:/path format, don't add leading slash
            pass
    
    return abs_path

def create_concat_file(file_list, concat_path):
    """Create a properly formatted concat file for FFmpeg with error checking."""
    try:
        print(f"📝 Creating concat file: {concat_path}")
        print(f"📝 Input files count: {len(file_list)}")
        
        with open(concat_path, 'w', encoding='utf-8') as f:
            for i, file_path in enumerate(file_list):
                print(f"📝   File {i+1}: {file_path}")
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"Input file not found: {file_path}")
                
                # Format path for FFmpeg compatibility
                formatted_path = format_path_for_ffmpeg(file_path)
                print(f"📝   Formatted: {formatted_path}")
                f.write(f"file '{formatted_path}'\n")
        
        # Verify the concat file was created and is readable
        if not os.path.exists(concat_path):
            raise RuntimeError(f"Failed to create concat file: {concat_path}")
        
        # Verify file size is reasonable
        file_size = os.path.getsize(concat_path)
        if file_size == 0:
            raise RuntimeError(f"Concat file is empty: {concat_path}")
        
        print(f"✅ Concat file created successfully: {concat_path} ({file_size} bytes)")
        
        # Debug: Show concat file contents
        with open(concat_path, 'r', encoding='utf-8') as f:
            contents = f.read().strip()
            print(f"📝 Concat file contents:\n{contents}")
        
        # Debug: Show what the FFmpeg command would look like
        test_cmd = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_path, '-c', 'copy', 'test_output.mp4']
        print(f"📝 Example FFmpeg command: {' '.join(test_cmd)}")
        
        return True
    except Exception as e:
        print(f"❌ Error creating concat file {concat_path}: {e}")
        return False

def get_media_duration(file_path):
    """Get duration of any media file using ffprobe.
    CPU-optimized: ffprobe metadata extraction is more efficient on CPU."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    cmd = [
        'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', file_path
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        duration = float(result.stdout.strip())
        if duration <= 0:
            raise ValueError(f"Invalid duration: {duration}")
        return duration
    except Exception as e:
        raise RuntimeError(f"Failed to get duration for {file_path}: {e}")


def has_audio_stream(file_path):
    """Check if a media file has audio streams using ffprobe."""
    if not os.path.exists(file_path):
        return False
    
    cmd = [
        'ffprobe', '-v', 'quiet', '-show_streams', '-select_streams', 'a',
        '-of', 'csv=p=0', file_path
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        return len(result.stdout.strip()) > 0
    except Exception:
        return False

# ===================================================================
# GPU DETECTION SYSTEM
# ===================================================================

def detect_gpu_acceleration():
    """Detect available GPU acceleration with detailed testing."""
    print("📍 STATUS: Testing GPU acceleration capabilities...")
    print("📍 GPU TEST: Running FFmpeg encoder detection...")
    
    try:
        cmd = ['ffmpeg', '-hide_banner', '-encoders']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        
        print("📍 GPU TEST: Analyzing available hardware encoders...")
        gpu_options = []
        
        # Check for AMD VCE
        if 'h264_amf' in result.stdout:
            gpu_options.append('AMD VCE (h264_amf)')
            print("📍 GPU FOUND: ✅ AMD VCE hardware encoder detected")
        else:
            print("📍 GPU CHECK: ❌ AMD VCE encoder not found")
        
        # Check for NVIDIA NVENC
        if 'h264_nvenc' in result.stdout:
            gpu_options.append('NVIDIA NVENC (h264_nvenc)')
            print("📍 GPU FOUND: ✅ NVIDIA NVENC hardware encoder detected")
        else:
            print("📍 GPU CHECK: ❌ NVIDIA NVENC encoder not found")
        
        # Check for Intel QuickSync
        if 'h264_qsv' in result.stdout:
            gpu_options.append('Intel QuickSync (h264_qsv)')
            print("📍 GPU FOUND: ✅ Intel QuickSync hardware encoder detected")
        else:
            print("📍 GPU CHECK: ❌ Intel QuickSync encoder not found")
        
        if gpu_options:
            print(f"📍 GPU TEST RESULT: Hardware acceleration available")
            print(f"✅ GPU encoders found: {', '.join(gpu_options)}")
            CONFIG["gpu_encoders"] = gpu_options
            return gpu_options
        else:
            print("📍 GPU TEST RESULT: No hardware encoders detected")
            print("📍 STATUS: Will use CPU encoding (reliable but slower)")
            CONFIG["gpu_encoders"] = []
            return []
            
    except subprocess.TimeoutExpired:
        print("📍 GPU TEST ERROR: FFmpeg detection timed out")
        print("⚠️ GPU detection timeout - will use CPU encoding")
        return []
    except Exception as e:
        print(f"📍 GPU TEST ERROR: {e}")
        print(f"⚠️ Could not detect GPU support: {e}")
        return []

def get_gpu_encoder_settings():
    """Get optimal GPU encoder settings based on detected hardware and user preference."""
    gpu_options = CONFIG.get("gpu_encoders", [])
    gpu_mode = CONFIG.get("gpu_mode", "auto")
    use_gpu = CONFIG.get("use_gpu", True)
    
    print(f"🎮 GPU Selection Mode: {gpu_mode.upper()}")
    print(f"🎮 Available GPU Encoders: {gpu_options}")
    print(f"🎮 Use GPU Setting: {use_gpu}")
    
    # Force CPU mode when use_gpu is False
    if not use_gpu or gpu_mode == "cpu":
        print("🎮 Using CPU encoding (libx264)")
        return ['-c:v', 'libx264', '-preset', 'fast', '-crf', '22']
    
    # Manual GPU selection modes - no fallbacks
    if gpu_mode == "nvidia":
        print("🎮 Force NVIDIA: Using NVENC hardware encoder")
        return ['-c:v', 'h264_nvenc', '-preset', 'fast', '-b:v', '8M']
    
    elif gpu_mode == "amd":
        print("🎮 Force AMD: Using VCE hardware encoder")
        return ['-c:v', 'h264_amf', '-quality', 'speed', '-rc', 'cbr', '-b:v', '8M']
    
    elif gpu_mode == "intel":
        print("🎮 Force Intel: Using QuickSync hardware encoder")
        return ['-c:v', 'h264_qsv', '-preset', 'fast', '-b:v', '8M']
    
    # Auto mode - detect best available, no CPU fallback
    elif gpu_mode == "auto" or gpu_mode is None:
        # AMD VCE (preferred for compatibility)
        if any('AMD VCE' in gpu for gpu in gpu_options):
            print("🎮 Auto-detect: Selected AMD VCE")
            return ['-c:v', 'h264_amf', '-quality', 'speed', '-rc', 'cbr', '-b:v', '8M']
        
        # NVIDIA NVENC
        elif any('NVIDIA' in gpu for gpu in gpu_options):
            print("🎮 Auto-detect: Selected NVIDIA NVENC")
            return ['-c:v', 'h264_nvenc', '-preset', 'fast', '-b:v', '8M']
        
        # Intel QuickSync
        elif any('Intel' in gpu for gpu in gpu_options):
            print("🎮 Auto-detect: Selected Intel QuickSync")
            return ['-c:v', 'h264_qsv', '-preset', 'fast', '-b:v', '8M']
    
    # No fallback - use first available GPU or nothing
    print("🎮 GPU-only mode: No limits, no fallbacks")
    return ['-c:v', 'h264_nvenc', '-preset', 'fast', '-b:v', '8M']

def get_gpu_stream_copy_settings():
    """Get GPU-optimized stream copy settings for maximum performance."""
    gpu_options = CONFIG.get("gpu_encoders", [])
    gpu_mode = CONFIG.get("gpu_mode", "auto")
    
    # Always use stream copy with GPU decode acceleration - no fallbacks
    base_settings = ['-c', 'copy']  # Stream copy for both video and audio
    
    # Force GPU decode acceleration based on mode
    if gpu_mode == "nvidia":
        print("🚀 GPU Stream Copy: Using NVIDIA hardware decode acceleration")
        return ['-hwaccel', 'nvdec'] + base_settings
        
    elif gpu_mode == "amd":
        print("🚀 GPU Stream Copy: Using AMD hardware decode acceleration") 
        return ['-hwaccel', 'dxva2'] + base_settings
        
    elif gpu_mode == "intel":
        print("🚀 GPU Stream Copy: Using Intel hardware decode acceleration")
        return ['-hwaccel', 'qsv'] + base_settings
        
    elif gpu_mode == "cpu":
        print("🚀 GPU Stream Copy: CPU mode - pure stream copy")
        return base_settings
    
    # Auto mode - use best available GPU decode without fallback
    elif gpu_mode == "auto":
        if any('AMD VCE' in gpu for gpu in gpu_options):
            print("🚀 GPU Stream Copy: Auto-detected AMD hardware decode")
            return ['-hwaccel', 'dxva2'] + base_settings
            
        elif any('NVIDIA' in gpu for gpu in gpu_options):
            print("🚀 GPU Stream Copy: Auto-detected NVIDIA hardware decode")
            return ['-hwaccel', 'nvdec'] + base_settings
            
        elif any('Intel' in gpu for gpu in gpu_options):
            print("🚀 GPU Stream Copy: Auto-detected Intel hardware decode")
            return ['-hwaccel', 'qsv'] + base_settings
        else:
            print("🚀 GPU Stream Copy: No hardware acceleration detected - using CPU mode")
            return base_settings
    
    # No limits mode - fallback to CPU if no GPU detected
    if gpu_options:
        # Use the first available GPU
        if any('AMD VCE' in gpu for gpu in gpu_options):
            print("🚀 GPU Stream Copy: Using AMD hardware decode")
            return ['-hwaccel', 'dxva2'] + base_settings
        elif any('NVIDIA' in gpu for gpu in gpu_options):
            print("🚀 GPU Stream Copy: Using NVIDIA hardware decode")
            return ['-hwaccel', 'nvdec'] + base_settings
        elif any('Intel' in gpu for gpu in gpu_options):
            print("🚀 GPU Stream Copy: Using Intel hardware decode")
            return ['-hwaccel', 'qsv'] + base_settings
    
    print("🚀 GPU Stream Copy: No GPU detected - using CPU mode")
    return base_settings

def build_concat_stream_copy_cmd(concat_file, output, duration=None):
    """Build FFmpeg command for concatenating files using stream copy - no hardware decode for concat."""
    cmd = ['ffmpeg', '-y']
    
    # For concat operations, don't use hardware decode as it causes issues
    # Instead, use stream copy which is very fast
    cmd.extend(['-f', 'concat', '-safe', '0', '-i', concat_file])
    
    # Add duration only if explicitly specified
    if duration:
        cmd.extend(['-t', str(duration)])
        print(f"🚀 Concat Stream Copy: Duration set to {duration}s")
    
    # Use stream copy for maximum performance
    cmd.extend(['-c', 'copy'])
    print(f"🚀 Concat Stream Copy: Pure stream copy mode - maximum performance")
    
    cmd.append(output)
    return cmd

def build_concat_fallback_cmd(file_list, output, duration=None):
    """Build FFmpeg command using filter_complex concatenation as fallback when concat demuxer fails."""
    cmd = ['ffmpeg', '-y']
    
    # Add all input files
    for file_path in file_list:
        cmd.extend(['-i', file_path])
    
    # Build filter_complex for concatenation
    if len(file_list) == 1:
        # Single file, just copy
        cmd.extend(['-c', 'copy'])
    else:
        # Multiple files, use concat filter
        filter_inputs = ''.join([f'[{i}:v:0][{i}:a:0]' for i in range(len(file_list))])
        filter_complex = f'{filter_inputs}concat=n={len(file_list)}:v=1:a=1[outv][outa]'
        cmd.extend(['-filter_complex', filter_complex, '-map', '[outv]', '-map', '[outa]'])
        # Use GPU encoding for the final output
        gpu_settings = get_gpu_encoder_settings()
        cmd.extend(gpu_settings)
    
    # Add duration only if explicitly specified
    if duration:
        cmd.extend(['-t', str(duration)])
        print(f"🚀 Concat Fallback: Duration set to {duration}s")
    
    cmd.append(output)
    print(f"🔄 Concat Fallback: Using filter_complex concatenation")
    return cmd

def build_gpu_stream_copy_cmd(inputs, output, duration=None, extra_args=None):
    """Build GPU-optimized FFmpeg command for stream copying operations - no limits."""
    cmd = ['ffmpeg', '-y']
    
    # Check if this is a concat operation (indicated by -f concat in extra_args)
    is_concat_op = extra_args and '-f' in extra_args and 'concat' in extra_args
    
    if is_concat_op:
        # For concat operations, use the specialized concat function
        print("🔄 Detected concat operation - using concat-optimized stream copy")
        return build_concat_stream_copy_cmd(inputs, output, duration)
    
    # Add GPU decode acceleration for non-concat operations
    gpu_settings = get_gpu_stream_copy_settings()
    hwaccel_args = [arg for arg in gpu_settings if arg.startswith('-hwaccel')]
    if hwaccel_args:
        cmd.extend(hwaccel_args[:2])  # Add -hwaccel and its value
        print(f"🚀 GPU Stream Copy: Hardware decode acceleration: {' '.join(hwaccel_args[:2])}")
    
    # Add extra arguments first
    if extra_args:
        cmd.extend(extra_args)
    
    # Add inputs
    if isinstance(inputs, list):
        for inp in inputs:
            cmd.extend(['-i', inp])
    else:
        cmd.extend(['-i', inputs])
    
    # Add duration only if explicitly specified (no automatic limits)
    if duration:
        cmd.extend(['-t', str(duration)])
        print(f"🚀 GPU Stream Copy: Duration set to {duration}s")
    
    # Add stream copy settings
    copy_settings = [arg for arg in gpu_settings if not arg.startswith('-hwaccel')]
    cmd.extend(copy_settings)
    print(f"🚀 GPU Stream Copy: Maximum performance mode - no limits")
    
    cmd.append(output)
    return cmd

def run_gpu_optimized_ffmpeg(self, cmd_args, description):
    """Enhanced FFmpeg runner with GPU optimization logging."""
    # Check if this is a GPU-accelerated operation
    is_gpu_op = any('-hwaccel' in str(arg) for arg in cmd_args)
    is_stream_copy = any('-c' in str(arg) and 'copy' in str(arg) for arg in cmd_args)
    
    if is_gpu_op and is_stream_copy:
        print(f"⚡ {description} (GPU-Accelerated Stream Copy)")
    elif is_stream_copy:
        print(f"🚀 {description} (Stream Copy)")
    elif is_gpu_op:
        print(f"🎮 {description} (GPU-Accelerated)")
    else:
        print(f"🖥️ {description} (CPU)")
    
    return self.run_ffmpeg(cmd_args, description)

# ===================================================================
# CORE VIDEO CREATION ENGINE WITH GPU ACCELERATION
# ===================================================================

class VideoCreator:
    def __init__(self, update_callback=None):
        self.update_callback = update_callback or print
        self.gpu_options = detect_gpu_acceleration()
        
    def log(self, message):
        """Thread-safe logging"""
        if self.update_callback:
            self.update_callback(message)
        print(message)
    
    def find_media_files(self, directory):
        """ENHANCED: Discover both images AND videos in directory.
        CPU-optimized: File I/O and sorting operations perform better on CPU."""
        try:
            all_files = os.listdir(directory)
        except (PermissionError, FileNotFoundError):
            return [], [], None, None, None
        
        # Find images
        image_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp')
        image_files = []
        for file in all_files:
            if file.lower().endswith(image_extensions) and os.path.isfile(os.path.join(directory, file)):
                image_files.append(os.path.join(directory, file))
        
        # ENHANCED: Find videos
        video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.wmv', '.flv')
        video_files = []
        for file in all_files:
            if file.lower().endswith(video_extensions) and os.path.isfile(os.path.join(directory, file)):
                # Skip overlay videos (they have specific keywords)
                overlay_keywords = ['overlay', 'effect', 'particle', 'fx']
                if not any(keyword in file.lower() for keyword in overlay_keywords):
                    video_files.append(os.path.join(directory, file))
        
        # Sort both naturally
        try:
            import natsort
            image_files = natsort.natsorted(image_files)
            video_files = natsort.natsorted(video_files)
        except ImportError:
            image_files = sorted(image_files)
            video_files = sorted(video_files)
        
        # Find audio files
        audio_patterns = ['*.mp3', '*.wav', '*.m4a', '*.aac']
        audio_files = []
        for pattern in audio_patterns:
            audio_files.extend(glob.glob(os.path.join(directory, pattern)))
        audio_files = [f for f in audio_files if os.path.isfile(f)]
        
        main_audio = audio_files[0] if audio_files else None
        
        # Find background music
        bg_music = None
        if CONFIG["use_bg_music"] and len(audio_files) > 1:
            bg_keywords = ['bg', 'background', 'music', 'ambient']
            for audio in audio_files[1:]:
                if any(keyword in os.path.basename(audio).lower() for keyword in bg_keywords):
                    bg_music = audio
                    break
            if not bg_music:
                bg_music = audio_files[1]
        
        # Find overlay video (separate from main videos)
        overlay_video = None
        if CONFIG["use_overlay"]:
            overlay_keywords = ['overlay', 'effect', 'particle', 'fx']
            for file in all_files:
                if file.lower().endswith(video_extensions):
                    if any(keyword in file.lower() for keyword in overlay_keywords):
                        overlay_video = os.path.join(directory, file)
                        break
        
        return image_files, video_files, main_audio, bg_music, overlay_video
    
    def run_ffmpeg(self, command, description, timeout=None, show_output=True):
        """Execute FFmpeg with error handling and process tracking."""
        self.log(f"🔄 {description}...")
        
        # Print the full command for debugging
        if show_output:
            print(f"\n💻 FFmpeg Command: {' '.join(command)}\n")
        
        startupinfo = None
        if os.name == 'nt' and not show_output:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        process = None
        try:
            # Start process and track it
            if show_output:
                # Show FFmpeg output in real-time
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1
                )
                
                # Track this process for force kill
                if hasattr(self.update_callback, '__self__'):
                    api = self.update_callback.__self__
                    if hasattr(api, 'active_processes'):
                        api.active_processes.append(process)
                
                # Stream output in real-time
                for line in process.stdout:
                    print(f"  {line.rstrip()}")
                    
                    # Check for common FFmpeg progress indicators
                    if 'time=' in line or 'frame=' in line:
                        # You can still parse progress here if needed
                        pass
                
                # Wait for completion
                process.wait()
                return_code = process.returncode
                
            else:
                # Original quiet mode
                process = subprocess.Popen(
                    command,
                    startupinfo=startupinfo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                # Track this process for force kill
                if hasattr(self.update_callback, '__self__'):
                    api = self.update_callback.__self__
                    if hasattr(api, 'active_processes'):
                        api.active_processes.append(process)
                
                # Wait for completion with timeout
                stdout, stderr = process.communicate(timeout=timeout)
                return_code = process.returncode
            
            if return_code == 0:
                self.log(f"✅ {description} - Success")
                return True
            else:
                self.log(f"❌ {description} - Failed (return code: {return_code})")
                if not show_output and 'stderr' in locals():
                    error_lines = stderr.strip().split('\n')
                    relevant_errors = [line for line in error_lines if any(keyword in line.lower() 
                                                                         for keyword in ['error', 'failed', 'invalid', 'not found'])]
                    if relevant_errors:
                        self.log(f"  Error: {relevant_errors[-1]}")
                return False
        
        except subprocess.TimeoutExpired:
            if process:
                process.kill()
                process.wait()
            self.log(f"❌ {description} - Timeout after {timeout}s")
            return False
        
        except Exception as e:
            if process:
                try:
                    process.kill()
                    process.wait()
                except:
                    pass
            self.log(f"❌ {description} - Error: {e}")
            return False
        
        finally:
            # Remove from tracked processes
            if process and hasattr(self.update_callback, '__self__'):
                api = self.update_callback.__self__
                if hasattr(api, 'active_processes') and process in api.active_processes:
                    api.active_processes.remove(process)
    
    def create_motion_clip(self, image_path, output_path, direction, duration, is_first=False, is_last=False, total_images=None):
        """Create motion clip with extended zoom support for few images."""
        self.log(f"🚀 DEBUG: create_motion_clip called with duration={duration}s, direction={direction}")
        
        # FORCE USE OF CONFIGURED DURATION - ignore any overrides
        duration = CONFIG.get("image_duration", 8.0)
        self.log(f"🚀 OVERRIDE: Forcing duration to CONFIG image_duration = {duration}s")
        
        if not os.path.exists(image_path):
            self.log(f"❌ Cannot read image: {image_path}")
            return False
            
        # Safety check: fix empty directions
        if not direction or direction.strip() == "":
            self.log(f"⚠️ Empty direction received, defaulting to 'right' pan")
            direction = "right"
            
        # Comprehensive logging at start of render
        self.log(f"🎬 RENDER START: {os.path.basename(image_path)}")
        self.log(f"   Motion: {direction} | Duration: {duration}s")
        
        extended_zoom = CONFIG.get("extended_zoom_enabled", False)
        if extended_zoom:
            zoom_dir = CONFIG.get("extended_zoom_direction", "in")
            zoom_amt = CONFIG.get("extended_zoom_amount", 30)
            self.log(f"   Extended Zoom: {zoom_dir} by {zoom_amt}%")
        
        
        captions_enabled = CONFIG.get("captions_enabled", False)
        caption_style = CONFIG.get("caption_style", "Custom")
        self.log(f"   Captions: {'Enabled' if captions_enabled else 'Disabled'} ({caption_style})")
        self.log(f"🚀 DEBUG: CONFIG captions_enabled = {captions_enabled}")
        self.log(f"   SAR normalization: Enabled | Format: yuv420p")
        total_images = 0
        if hasattr(self.update_callback, '__self__'):
            api_instance = self.update_callback.__self__
            if hasattr(api_instance, 'image_files'):
                total_images = len(api_instance.image_files)

        video_filter = ""
        self.log(f"🚀 DEBUG: extended_zoom={extended_zoom}")
        if extended_zoom:
            self.log(f"🚀 DEBUG: Original duration: {duration}s")
            # Keep the configured duration, don't extend it unnecessarily
            duration = CONFIG.get("image_duration", 8.0)
            self.log(f"🚀 DEBUG: Using configured image_duration: {duration}s")
            
            # Debug: Show exactly what config values are being used
            config_zoom_amount = CONFIG.get("extended_zoom_amount", 30)
            config_zoom_direction = CONFIG.get("extended_zoom_direction", "in")
            config_image_duration = CONFIG.get("image_duration", 8.0)
            
            self.log(f"🚀 DEBUG: CONFIG VALUES:")
            self.log(f"   - extended_zoom_amount: {config_zoom_amount}%")
            self.log(f"   - extended_zoom_direction: {config_zoom_direction}")
            self.log(f"   - image_duration: {config_image_duration}s")
            self.log(f"   - Using duration: {duration}s")
            
            zoom_amount = config_zoom_amount / 100.0
            # For extended zoom, prioritize the config setting over the passed direction
            zoom_direction = config_zoom_direction
            
            self.log(f"🔍 Extended zoom mode: {zoom_direction} by {zoom_amount*100}% for {duration}s")
            self.log(f"🚀 DEBUG: zoom_direction={zoom_direction}, total_images={total_images}")
            
            total_frames = int(duration * 25)
            max_zoom = 1.0 + zoom_amount
            
            # Use smooth zoom logic like normal zoom but with configurable amount
            if zoom_direction == "in" or zoom_direction == "zoom_in":
                self.log(f"🚀 DEBUG: Using ZOOM IN branch")
                # Start at 1.0, zoom to max_zoom - smooth zoom
                zoom_rate = zoom_amount / total_frames
                zoom_expression = f"'min(zoom+{zoom_rate},{max_zoom})'"
                self.log(f"🚀 DEBUG: zoom_rate={zoom_rate}, zoom_expression={zoom_expression}")
            elif zoom_direction == "out" or zoom_direction == "zoom_out":
                self.log(f"🚀 DEBUG: Using ZOOM OUT branch")
                # Start at max_zoom, zoom to 1.0 - smooth zoom reversed
                zoom_rate = zoom_amount / total_frames
                zoom_expression = f"'max(zoom-{zoom_rate},1.0)'"
                self.log(f"🚀 DEBUG: zoom_rate={zoom_rate}, zoom_expression={zoom_expression}")
            elif zoom_direction == "in_out":
                self.log(f"🚀 DEBUG: Using ZOOM IN_OUT branch")
                # Use frame-based calculation instead of time-based to avoid expression complexity
                mid_frame = total_frames / 2.0
                zoom_in_rate = zoom_amount / mid_frame  # Rate for first half
                zoom_out_rate = zoom_amount / mid_frame  # Rate for second half
                max_zoom_val = 1.0 + zoom_amount
                # Simple frame-based expression that's more reliable
                zoom_expression = f"'if(lt(on,{mid_frame}),min(1+{zoom_in_rate}*on,{max_zoom_val}),max({max_zoom_val}-{zoom_out_rate}*(on-{mid_frame}),1))'"
                self.log(f"🚀 DEBUG: mid_frame={mid_frame}, max_zoom={max_zoom_val}")
                self.log(f"🚀 DEBUG: zoom_in_rate={zoom_in_rate}, zoom_out_rate={zoom_out_rate}")
                self.log(f"🚀 DEBUG: zoom_expression={zoom_expression}")
            else:
                self.log(f"🚀 DEBUG: Using DEFAULT branch for direction: {zoom_direction}")
                # Default to zoom in if direction is not recognized
                zoom_rate = zoom_amount / total_frames
                zoom_expression = f"'min(zoom+{zoom_rate},{max_zoom})'"
                self.log(f"🚀 DEBUG: zoom_rate={zoom_rate}, zoom_expression={zoom_expression}")
            
            # Use same format as normal zoom with proper centering and smooth zoom pipeline
            video_filter = (
                f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,scale=3840:2160,"
                f"zoompan=z={zoom_expression}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:fps=25:s=3840x2160,scale=1920:1080,"
                f"setsar=1,format=yuv420p"
            )
        else:
            # Regular motion logic...
            if direction == "no_motion":
                # No animation - just scale and center
                video_filter = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,format=yuv420p"
            elif direction == "zoom_in":
                # Start at 1.0, zoom to 1.2 over duration, centered - smooth zoom
                total_frames = int(duration * 25)
                video_filter = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,scale=3840:2160,zoompan=z='min(zoom+0.0015,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:fps=25:s=3840x2160,scale=1920:1080,setsar=1,format=yuv420p"
            elif direction == "zoom_out":
                # Start at 1.2, zoom to 1.0 over duration, centered - smooth zoom reversed
                total_frames = int(duration * 25)
                video_filter = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,scale=3840:2160,zoompan=z='max(zoom-0.0015,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:fps=25:s=3840x2160,scale=1920:1080,setsar=1,format=yuv420p"
            else:
                # Pan/motion directions
                self.log(f"🎥 Applying pan motion: '{direction}' (length={len(direction)})")
                scale_filter = "scale=2304:-1"
                # Normalize direction to handle any whitespace issues
                direction = direction.strip().lower()
                if direction == "right":
                    crop_filter = f"crop=1920:1080:x='(iw-ow)*t/{duration}':y='(ih-oh)/2'"
                elif direction == "left": 
                    crop_filter = f"crop=1920:1080:x='(iw-ow)*(1-t/{duration})':y='(ih-oh)/2'"
                elif direction == "down": 
                    crop_filter = f"crop=1920:1080:x='(iw-ow)/2':y='(ih-oh)*t/{duration}'"
                elif direction == "up": 
                    crop_filter = f"crop=1920:1080:x='(iw-ow)/2':y='(ih-oh)*(1-t/{duration})'"
                else:
                    # Default to right pan if direction is unknown
                    self.log(f"⚠️ Unknown direction '{direction}' (repr={repr(direction)}), defaulting to right pan")
                    crop_filter = f"crop=1920:1080:x='(iw-ow)*t/{duration}':y='(ih-oh)/2'"
                
                video_filter = f"{scale_filter},{crop_filter},setsar=1,format=yuv420p"

        if CONFIG["use_fade_in"] and is_first:
            video_filter += ",fade=t=in:st=0:d=0.5"
        if CONFIG["use_fade_out"] and is_last:
            video_filter += f",fade=t=out:st={duration-0.5}:d=0.5"
        
        cmd = [
            'ffmpeg', '-y', '-loop', '1', '-i', image_path,
            '-vf', video_filter,
            '-t', str(duration), '-r', '25'
        ]
        
        # Use GPU encoding for video creation from images (where GPU excels)
        gpu_encoder_settings = get_gpu_encoder_settings()
        cmd.extend(gpu_encoder_settings)
        cmd.extend(['-pix_fmt', 'yuv420p', '-an', '-stats', output_path])
        
        return self.run_ffmpeg(cmd, f"Creating motion clip ({direction})")

    def apply_crossfade_transitions(self, clips, output_path):
        """Apply CPU-only crossfade transitions for consistent performance."""
        if not clips:
            return False

        if len(clips) == 1:
            shutil.copy2(clips[0], output_path)
            return True

        current_video = clips[0]
        total_clips = len(clips)
        
        self.log(f"🎞️ Starting CPU crossfade processing for {total_clips} clips...")
        self.log(f"💡 Tip: Processing {total_clips-1} crossfades may take a few minutes")

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                for i, next_clip in enumerate(clips[1:], 1):
                    # Match the format used in the log messages - no leading zeros for consistency
                    temp_output = os.path.join(temp_dir, f"crossfade_{i}.mp4")

                    try:
                        current_duration = get_media_duration(current_video)
                        crossfade_duration = CONFIG["crossfade_duration"]
                        offset = max(0, current_duration - crossfade_duration)

                        self.log(f"  CPU Crossfade {i}/{len(clips)-1}: offset={offset:.1f}s")

                        # CPU-only crossfade command with performance optimizations
                        cmd = ['ffmpeg', '-y']
                        
                        # Force no hardware acceleration for crossfades only
                        cmd.extend(['-hwaccel', 'none'])
                        
                        # Add inputs with minimal decoding
                        cmd.extend([
                            '-i', current_video, '-i', next_clip,
                            '-filter_complex',
                            f'[0:v][1:v]xfade=transition=fade:duration={crossfade_duration}:offset={offset}[v]',
                            '-map', '[v]'
                        ])

                        # Optimized CPU encoding settings for faster processing
                        cmd.extend([
                            '-c:v', 'libx264',
                            '-preset', 'ultrafast',  # Fastest preset for crossfades
                            '-crf', '25',  # Slightly lower quality for speed
                            '-pix_fmt', 'yuv420p',
                            '-threads', '0'  # Use all available CPU threads
                        ])
                        
                        cmd.append(temp_output)

                        if not self.run_ffmpeg(cmd, f"CPU crossfade {i}"):
                            return False

                        # Verify the output file exists before proceeding
                        if not os.path.exists(temp_output):
                            self.log(f"❌ Crossfade output file not created: {temp_output}")
                            return False

                        current_video = temp_output

                    except Exception as e:
                        self.log(f"❌ Crossfade {i} error: {e}")
                        return False

            except Exception as e:
                self.log(f"❌ Crossfade processing error: {e}")
                return False

            # Final copy with verification
            if os.path.exists(current_video):
                shutil.copy2(current_video, output_path)
                self.log(f"✅ All {len(clips)-1} crossfades completed successfully")
                return True
            else:
                self.log(f"❌ Final crossfaded video not found")
                return False
    
    def apply_overlay(self, master_video, overlay_video, output_path, duration):
        """Apply overlay with simple or screen blend mode."""
        if not overlay_video or not os.path.exists(overlay_video):
            shutil.copy2(master_video, output_path)
            return True
        
        overlay_mode = CONFIG.get("overlay_mode", "simple")
        overlay_opacity = CONFIG.get("overlay_opacity", 0.5)
        self.log(f"🎭 Adding {overlay_mode} overlay: {os.path.basename(overlay_video)} (opacity: {overlay_opacity})")
        self.log(f"🔧 Overlay mode DEBUG: CONFIG['overlay_mode'] = '{overlay_mode}'")
        self.log(f"🔧 Overlay opacity DEBUG: CONFIG['overlay_opacity'] = {repr(CONFIG.get('overlay_opacity'))} (type: {type(CONFIG.get('overlay_opacity'))})")
        
        # Additional debug: check if this is a screen blend
        if overlay_mode == "screen_blend":
            self.log("⚠️ SCREEN BLEND MODE DETECTED - using blend=all_mode=screen")
        else:
            self.log("✅ SIMPLE OVERLAY MODE - using standard overlay filter")
        
        # Check if GPU acceleration is available
        if CONFIG["use_gpu"] and self.gpu_options:
            self.log("🚀 Using GPU-accelerated overlay processing")
        else:
            self.log("🖥️ Using CPU for overlay processing")
        
        cmd = ['ffmpeg', '-y']
        
        # Add hardware acceleration for input if available
        if CONFIG["use_gpu"] and self.gpu_options:
            cmd.extend(['-hwaccel', 'auto'])
        
        if overlay_mode == "screen_blend":
            # Screen blend mode with alpha attenuation and RGB24 conversion
            cmd.extend([
                # FIX: Use -stream_loop for video inputs, not -loop
                '-stream_loop', '-1', '-i', master_video, '-t', str(duration),
                '-stream_loop', '-1', '-i', overlay_video,
                '-filter_complex',
                f'[1:v]scale=1920:1080,format=yuva420p,colorchannelmixer=aa={CONFIG["overlay_opacity"]},format=rgb24[ov];[0:v]format=rgb24[bg];[bg][ov]blend=all_mode=screen,format=rgb24,setsar=1,format=yuv420p[v]',
                '-map', '[v]'
            ])
        else:
            # Simple overlay mode with opacity
            cmd.extend([
                '-i', master_video, '-stream_loop', '-1', '-i', overlay_video,
                '-filter_complex',
                f'[1:v]format=yuva420p,colorchannelmixer=aa={CONFIG["overlay_opacity"]}[overlay];[0:v][overlay]overlay=format=auto,setsar=1[v]',
                '-map', '[v]'
            ])
        
        # GPU encoding settings
        cmd.extend(get_gpu_encoder_settings())
        cmd.extend(['-t', str(duration), '-an', output_path])
        
        if not self.run_ffmpeg(cmd, f"{overlay_mode.title()} overlay processing"):
            self.log("⚠️  Overlay failed, continuing without overlay")
            shutil.copy2(master_video, output_path)
        
        return True
    
    def process_video_clip(self, video_path, output_path, duration=None, apply_fade_in=False, apply_fade_out=False, apply_overlay=False, overlay_video=None):
        """Process video with optional fade and overlay effects."""
        if not os.path.exists(video_path):
            self.log(f"❌ Cannot read video: {video_path}")
            return False
        
        self.log(f"🎬 Processing video: {os.path.basename(video_path)}")
        
        # If overlay is requested, process it separately
        if apply_overlay and overlay_video and CONFIG.get("use_overlay", False):
            # First process video with fades
            temp_output = output_path + "_temp.mp4"
            
            # Build filter chain
            filters = ['scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080']
            
            if apply_fade_in and CONFIG.get("use_fade_in", True):
                filters.append('fade=t=in:st=0:d=0.5')
                self.log("  Adding fade-in effect")
            
            if apply_fade_out and CONFIG.get("use_fade_out", True):
                try:
                    vid_duration = get_media_duration(video_path) if not duration else duration
                    fade_start = vid_duration - 0.5
                    filters.append(f'fade=t=out:st={fade_start}:d=0.5')
                    self.log("  Adding fade-out effect")
                except:
                    pass
            
            # Process video with fades
            cmd = [
                'ffmpeg', '-y', '-i', video_path,
                '-vf', ','.join(filters),
                '-r', '25',  # Force 25 fps to match slideshow framerate
                '-c:v', 'libx264', 
                '-preset', 'ultrafast',
                '-crf', '25',
                '-pix_fmt', 'yuv420p',
                '-an'
            ]
            
            if duration:
                cmd.extend(['-t', str(duration)])
            
            cmd.append(temp_output)
            
            if not self.run_ffmpeg(cmd, "Processing video with fades"):
                return False
            
            # Apply overlay to the faded video
            video_duration = get_media_duration(temp_output)
            if self.apply_overlay(temp_output, overlay_video, output_path, video_duration):
                os.remove(temp_output)  # Clean up temp file
                return True
            else:
                os.remove(temp_output)
                return False
        else:
            # Process without overlay
            filters = ['scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080']
            
            if apply_fade_in and CONFIG.get("use_fade_in", True):
                filters.append('fade=t=in:st=0:d=0.5')
                self.log("  Adding fade-in effect")
            
            if apply_fade_out and CONFIG.get("use_fade_out", True):
                try:
                    vid_duration = get_media_duration(video_path) if not duration else duration
                    fade_start = vid_duration - 0.5
                    filters.append(f'fade=t=out:st={fade_start}:d=0.5')
                    self.log("  Adding fade-out effect")
                except:
                    pass
            
            cmd = [
                'ffmpeg', '-y', '-i', video_path,
                '-vf', ','.join(filters),
                '-r', '25',  # Force 25 fps to match slideshow framerate
                '-c:v', 'libx264', 
                '-preset', 'ultrafast',
                '-crf', '25',
                '-pix_fmt', 'yuv420p',
                '-an'
            ]
            
            if duration:
                cmd.extend(['-t', str(duration)])
            
            cmd.append(output_path)
            
            return self.run_ffmpeg(cmd, "Processing video")

    def create_slideshow(self, image_files, video_files, main_audio, bg_music=None, overlay_video=None, output_file="slideshow.mp4"):
        """Create slideshow with mode-specific optimizations."""
        self.log("🚀 STARTING VIDEO CREATION")
        self.log("=" * 60)
        
        project_type = CONFIG.get("project_type", "montage")
        self.log(f"📍 Mode: {project_type.upper()}")
        
        if not main_audio:
            self.log("❌ Missing required audio!")
            return False

        if not image_files and not video_files:
            self.log("❌ No images or videos provided!")
            return False
        
        # Route to appropriate method based on project type
        if project_type == "slideshow":
            if not image_files:
                self.log("❌ Slideshow mode requires at least one image.")
                return False
            return self.create_slideshow_original(image_files, main_audio, bg_music, overlay_video, output_file)
        elif project_type == "videos_only":
            if not video_files:
                self.log("❌ Videos-only mode requires at least one video.")
                return False
            return self.create_videos_only(video_files, main_audio, bg_music, overlay_video, output_file)
        else:
            # Montage mode - handle mixed media
            return self.create_montage_optimized(image_files, video_files, main_audio, bg_music, overlay_video, output_file)
    
    def create_slideshow_original(self, image_files, main_audio, bg_music=None, overlay_video=None, output_file="slideshow.mp4"):
        """OPTIMIZED METHOD: Create pure image slideshow with efficient looping."""
        self.log("🖼️ SLIDESHOW MODE - Using OPTIMIZED looping generation")
        self.log("=" * 60)
        
        if not image_files:
            self.log("❌ Slideshow mode requires at least one image.")
            return False

        try:
            with tempfile.TemporaryDirectory() as work_dir:
                # === STAGE 1: PROCESS AUDIO ===
                self.log(f"\n=== STAGE 1: Audio Processing ===")
                processed_audio = os.path.join(work_dir, "audio.mp3")
                if not self.run_ffmpeg(['ffmpeg', '-y', '-i', main_audio, '-c:a', 'libmp3lame', '-b:a', '320k', '-ar', '44100', processed_audio], "Processing audio"):
                    return False
                audio_duration = get_media_duration(processed_audio)
                self.log(f"📊 Audio duration: {audio_duration:.1f}s")
                
                # === STAGE 2: CREATE IMAGE SLIDESHOW CYCLE ===
                self.log(f"\n=== STAGE 2: Creating Image Slideshow Cycle ===")
                duration_per_image = CONFIG["image_duration"]
                self.log(f"🚀 DEBUG: duration_per_image from CONFIG['image_duration'] = {duration_per_image}s")
                self.log(f"🚀 DEBUG: Current CONFIG state - image_duration: {CONFIG.get('image_duration', 'NOT_SET')}")
                
                # If you want to force it back to 8 seconds, uncomment this line:
                # CONFIG['image_duration'] = 8.0
                # duration_per_image = 8.0
                # self.log(f"🚀 DEBUG: FORCED image_duration back to 8.0s")
                self.log(f"🚀 DEBUG: extended_zoom_enabled = {CONFIG.get('extended_zoom_enabled', False)}")
                
                # Check if extended zoom is somehow modifying duration
                if CONFIG.get('extended_zoom_enabled', False) and len(image_files) <= 5:
                    self.log(f"🚀 DEBUG: Extended zoom active - checking if duration gets modified...")
                    self.log(f"🚀 DEBUG: Audio duration = {audio_duration:.1f}s")
                    self.log(f"🚀 DEBUG: Number of images = {len(image_files)}")
                    calculated_duration = audio_duration / len(image_files) if len(image_files) > 0 else duration_per_image
                    self.log(f"🚀 DEBUG: Calculated duration per image = {calculated_duration:.1f}s")
                
                single_cycle_clips = []
                animation_style = CONFIG.get("animation_style", "Sequential Motion")
                total_images = len(image_files)
                
                for i, image_file in enumerate(image_files):
                    clip_output = os.path.join(work_dir, f"image_{i:03d}.mp4")
                    # Use helper function to determine motion direction
                    direction = pick_motion_direction(animation_style, i, total_images)
                    self.log(f"🎬 Motion: {direction} (image {i+1}/{total_images})")
                    
                    # Use the configured image_duration (extended zoom will handle its own timing internally)
                    actual_duration = duration_per_image
                    self.log(f"🚀 DEBUG: Using configured image_duration: {actual_duration}s")
                    # Fades are applied later to the full-length video in this workflow
                    if self.create_motion_clip(image_file, clip_output, direction, duration=actual_duration):
                        single_cycle_clips.append(clip_output)
                    else:
                        return False
                
                slideshow_one_cycle = os.path.join(work_dir, "slideshow_one_cycle.mp4")
                if CONFIG.get("use_crossfade", True) and len(single_cycle_clips) > 1:
                    if not self.apply_crossfade_transitions(single_cycle_clips, slideshow_one_cycle): return False
                    
                    # CLEANUP: Delete motion clips immediately after master video creation (crossfade path)
                    self.log(f"🧹 Cleaning up {len(single_cycle_clips)} motion clips to free storage...")
                    for clip_file in single_cycle_clips:
                        try:
                            if os.path.exists(clip_file):
                                os.remove(clip_file)
                                self.log(f"🗑️ Deleted: {os.path.basename(clip_file)}")
                        except Exception as e:
                            self.log(f"⚠️ Could not delete {os.path.basename(clip_file)}: {e}")
                else:
                    concat_list = os.path.join(work_dir, "concat_images.txt")
                    if not create_concat_file(single_cycle_clips, concat_list):
                        self.log("❌ Failed to create concat file for image clips")
                        return False
                    # Use GPU-accelerated stream copy for concatenation
                    gpu_concat_cmd = build_gpu_stream_copy_cmd(concat_list, slideshow_one_cycle, extra_args=['-f', 'concat', '-safe', '0'])
                    if not self.run_ffmpeg(gpu_concat_cmd, "GPU Stream Copy: Concatenating image clips"):
                        # Fallback to filter_complex concatenation if concat demuxer fails
                        self.log("🔄 Concat demuxer failed, trying filter_complex fallback...")
                        fallback_cmd = build_concat_fallback_cmd(single_cycle_clips, slideshow_one_cycle)
                        if not self.run_ffmpeg(fallback_cmd, "GPU Concat Fallback: Using filter_complex"):
                            return False
                
                # CLEANUP: Delete motion clips immediately after master video creation
                self.log(f"🧹 Cleaning up {len(single_cycle_clips)} motion clips to free storage...")
                for clip_file in single_cycle_clips:
                    try:
                        if os.path.exists(clip_file):
                            os.remove(clip_file)
                            self.log(f"🗑️ Deleted: {os.path.basename(clip_file)}")
                    except Exception as e:
                        self.log(f"⚠️ Could not delete {os.path.basename(clip_file)}: {e}")
                
                # === STAGE 3: APPLY OVERLAY TO CYCLE ===
                self.log(f"\n=== STAGE 3: Applying Overlay to Cycle ===")
                if CONFIG.get("use_overlay", False) and overlay_video:
                    slideshow_with_overlay = os.path.join(work_dir, "slideshow_cycle_overlay.mp4")
                    cycle_duration = get_media_duration(slideshow_one_cycle)
                    if self.apply_overlay(slideshow_one_cycle, overlay_video, slideshow_with_overlay, cycle_duration):
                        slideshow_one_cycle = slideshow_with_overlay
                
                # === STAGE 4: LOOP CYCLE TO MATCH AUDIO ===
                self.log(f"\n=== STAGE 4: Looping Slideshow Cycle ===")
                master_video_no_audio = os.path.join(work_dir, "master_no_audio.mp4")
                
                temp_looped_video = os.path.join(work_dir, "temp_looped.mp4")
                loop_cmd = [
                    'ffmpeg', '-y', '-stream_loop', '-1', '-i', slideshow_one_cycle,
                    '-c', 'copy', '-t', str(audio_duration), temp_looped_video
                ]
                if not self.run_ffmpeg(loop_cmd, "Looping video to match audio duration"):
                    return False

                # Apply fades to the full-length looped video
                fade_filter = []
                if CONFIG["use_fade_in"]: fade_filter.append("fade=t=in:st=0:d=0.5")
                if CONFIG["use_fade_out"]: fade_filter.append(f"fade=t=out:st={audio_duration-0.5}:d=0.5")

                if fade_filter:
                    fade_cmd = [
                        'ffmpeg', '-y', '-i', temp_looped_video,
                        '-vf', ",".join(fade_filter),
                        '-c:v', 'libx264', '-preset', 'fast', '-crf', '22',
                        master_video_no_audio
                    ]
                    if not self.run_ffmpeg(fade_cmd, "Applying fade effects"): return False
                else:
                    shutil.copy2(temp_looped_video, master_video_no_audio)

                # === STAGE 5: FINAL ASSEMBLY ===
                self.log(f"\n=== STAGE 5: Final Assembly ===")
                final_audio_path = processed_audio
                if CONFIG["use_bg_music"] and bg_music:
                    mixed_audio_path = os.path.join(work_dir, "mixed_audio.mp3")
                    audio_mix_cmd = [
                        'ffmpeg', '-y', '-i', processed_audio, '-stream_loop', '-1', '-i', bg_music,
                        '-filter_complex', f'[0:a]volume={CONFIG["main_audio_vol"]}[a1];[1:a]volume={CONFIG["bg_vol"]}[a2];[a1][a2]amix=inputs=2:duration=first:dropout_transition=2',
                        '-t', str(audio_duration), '-c:a', 'libmp3lame', '-b:a', '320k', mixed_audio_path
                    ]
                    if self.run_ffmpeg(audio_mix_cmd, "Pre-mixing audio"):
                        final_audio_path = mixed_audio_path
                
                final_cmd = [
                    'ffmpeg', '-y', '-i', master_video_no_audio, '-i', final_audio_path,
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-map', '0:v:0', '-map', '1:a:0', '-t', str(audio_duration),
                    output_file
                ]
                if not self.run_ffmpeg(final_cmd, "Fast Final Assembly (Stream Copy)"):
                    return False

        except Exception as e:
            self.log(f"❌ An unexpected error occurred: {e}")
            import traceback
            self.log(traceback.format_exc())
            return False
        
        # === SUCCESS ===
        try:
            final_duration = get_media_duration(output_file)
            file_size = os.path.getsize(output_file) / (1024 * 1024)
            
            self.log(f"\n🎉 SLIDESHOW CREATION SUCCESS!")
            self.log(f"📁 Output: {output_file}")
            self.log(f"⏱️  Duration: {final_duration:.1f}s")
            self.log(f"💾 Size: {file_size:.1f} MB")
            self.log(f"📸 Structure: {len(image_files)} images (looped as needed)")
            
            return True
            
        except Exception as e:
            self.log(f"❌ Verification error: {e}")
            return False
    
    def create_videos_only(self, video_files, main_audio, bg_music=None, overlay_video=None, output_file="videos_only.mp4"):
        """NEW: Create videos-only compilation with overlays, captions, and looping."""
        self.log("🎬 VIDEOS ONLY MODE - Processing video compilation")
        self.log("=" * 60)
        
        if not video_files:
            self.log("❌ Videos-only mode requires at least one video.")
            return False

        if not main_audio:
            self.log("❌ Missing required audio!")
            return False

        try:
            with tempfile.TemporaryDirectory() as work_dir:
                self.log(f"📁 Working directory: {work_dir}")
                
                # Get audio duration to determine target length
                audio_duration = get_media_duration(main_audio)
                self.log(f"🎵 Target audio duration: {audio_duration:.2f}s")
                
                # Calculate total video duration
                total_video_duration = 0
                for video_file in video_files:
                    video_duration = get_media_duration(video_file)
                    total_video_duration += video_duration
                    self.log(f"📹 {os.path.basename(video_file)}: {video_duration:.2f}s")
                
                self.log(f"🎬 Total video content: {total_video_duration:.2f}s")
                
                # Determine if we need to loop videos
                needs_looping = total_video_duration < audio_duration
                if needs_looping:
                    loops_needed = math.ceil(audio_duration / total_video_duration)
                    self.log(f"🔄 Videos are shorter than audio - will loop {loops_needed} times")
                else:
                    self.log("✅ Videos are long enough - no looping needed")
                
                # Process each video for consistency (fade handling, etc.)
                processed_videos = []
                for i, video_file in enumerate(video_files):
                    is_first = (i == 0)
                    is_last = (i == len(video_files) - 1) and not needs_looping
                    
                    processed_video = os.path.join(work_dir, f"processed_video_{i}.mp4")
                    
                    # Apply fades only to first and last videos when not looping
                    apply_fade_in = is_first and CONFIG.get("use_fade_in", True)
                    apply_fade_out = is_last and CONFIG.get("use_fade_out", True)
                    
                    success = self.process_video_clip(
                        video_file, processed_video, 
                        apply_fade_in=apply_fade_in, 
                        apply_fade_out=apply_fade_out
                    )
                    if not success:
                        return False
                    
                    processed_videos.append(processed_video)
                
                # Concatenate all videos
                video_list_file = os.path.join(work_dir, "video_list.txt")
                
                if needs_looping:
                    # Create looped content
                    with open(video_list_file, 'w', encoding='utf-8') as f:
                        for loop in range(loops_needed):
                            for video in processed_videos:
                                f.write(f"file '{video}'\n")
                else:
                    # Just concatenate once
                    with open(video_list_file, 'w', encoding='utf-8') as f:
                        for video in processed_videos:
                            f.write(f"file '{video}'\n")
                
                # Concatenate videos
                concatenated_video = os.path.join(work_dir, "concatenated_videos.mp4")
                # Use GPU-accelerated stream copy for video concatenation
                gpu_concat_cmd = build_gpu_stream_copy_cmd(video_list_file, concatenated_video, extra_args=['-f', 'concat', '-safe', '0'])
                
                if not self.run_ffmpeg(gpu_concat_cmd, "GPU Stream Copy: Concatenating videos"):
                    return False
                
                # Trim to audio length if videos are longer
                final_video = concatenated_video
                if get_media_duration(concatenated_video) > audio_duration:
                    trimmed_video = os.path.join(work_dir, "trimmed_videos.mp4")
                    # Use GPU-accelerated stream copy for trimming
                    gpu_trim_cmd = build_gpu_stream_copy_cmd(concatenated_video, trimmed_video, duration=audio_duration)
                    if self.run_ffmpeg(gpu_trim_cmd, "GPU Stream Copy: Trimming videos to audio length"):
                        final_video = trimmed_video
                
                # Apply overlay if requested
                if CONFIG.get("use_overlay", False) and overlay_video:
                    overlaid_video = os.path.join(work_dir, "videos_with_overlay.mp4")
                    overlay_success = self.apply_overlay(final_video, overlay_video, overlaid_video, audio_duration)
                    if overlay_success:
                        final_video = overlaid_video
                
                # Apply final fade out if looping (fade out the entire compilation)
                if needs_looping and CONFIG.get("use_fade_out", True):
                    faded_video = os.path.join(work_dir, "videos_with_fadeout.mp4")
                    fade_cmd = [
                        'ffmpeg', '-y', '-i', final_video,
                        '-vf', f'fade=t=out:st={audio_duration-0.5}:d=0.5',
                        '-c:a', 'copy', faded_video
                    ]
                    if self.run_ffmpeg(fade_cmd, "🌅 Applying final fade out"):
                        final_video = faded_video
                
                # Combine with audio
                self.log("🎵 Combining videos with audio...")
                final_cmd = ['ffmpeg', '-y', '-i', final_video, '-i', main_audio]
                
                # Handle background music
                filter_complex_parts = []
                if CONFIG["use_bg_music"] and bg_music:
                    final_cmd.extend(['-stream_loop', '-1', '-i', bg_music])
                    filter_complex_parts.append(f"[1:a]volume={CONFIG['main_audio_vol']}[a_main]")
                    filter_complex_parts.append(f"[2:a]volume={CONFIG['bg_vol']}[a_bg]")
                    filter_complex_parts.append("[a_main][a_bg]amix=inputs=2:duration=first:dropout_transition=2[a_out]")
                    final_cmd.extend(['-filter_complex', ';'.join(filter_complex_parts), '-map', '0:v', '-map', '[a_out]'])
                else:
                    filter_complex_parts.append(f"[1:a]volume={CONFIG['main_audio_vol']}[a_out]")
                    final_cmd.extend(['-filter_complex', ';'.join(filter_complex_parts), '-map', '0:v', '-map', '[a_out]'])
                
                # Add encoding settings
                final_cmd.extend(['-t', str(audio_duration)])
                if CONFIG["use_gpu"] and self.gpu_options:
                    final_cmd.extend(get_gpu_encoder_settings())
                else:
                    final_cmd.extend(['-c:v', 'libx264', '-preset', CONFIG["preset"], '-crf', str(CONFIG["crf"])])
                
                final_cmd.extend(['-c:a', 'aac', '-b:a', '192k', output_file])
                
                if not self.run_ffmpeg(final_cmd, "🎬 Creating final videos-only compilation"):
                    return False
                
                self.log("✅ Videos-only compilation created successfully!")
                return True
                
        except Exception as e:
            self.log(f"❌ Videos-only creation failed: {e}")
            return False

    def create_montage_optimized(self, image_files, video_files, main_audio, bg_music=None, overlay_video=None, output_file="slideshow.mp4"):
        """OPTIMIZED: Videos as intro + efficient image slideshow with looping."""
        self.log("🚀 STARTING OPTIMIZED MEDIA CREATION")
        self.log("=" * 60)
        
        if not main_audio:
            self.log("❌ Missing required audio!")
            return False

        if not image_files and not video_files:
            self.log("❌ No images or videos provided!")
            return False

        try:
            with tempfile.TemporaryDirectory() as work_dir:
                
                # === STAGE 1: PROCESS AUDIO ===
                self.log(f"\n=== STAGE 1: Audio Processing ===")
                processed_audio = os.path.join(work_dir, "audio.mp3")
                if not self.run_ffmpeg(['ffmpeg', '-y', '-i', main_audio, '-c:a', 'libmp3lame', '-b:a', '320k', '-ar', '44100', processed_audio], "Processing audio"):
                    return False
                
                audio_duration = get_media_duration(processed_audio)
                self.log(f"📊 Audio duration: {audio_duration:.1f}s")
                
                # === STAGE 2: OPTIMIZED MEDIA PROCESSING ===
                self.log(f"\n=== STAGE 2: Optimized Media Processing ===")
                intro_clips = []
                slideshow_base = None
                total_video_duration = 0
                
                # Process intro videos (if any)
                if video_files and CONFIG.get("use_videos", True):
                    self.log(f"--- Processing {len(video_files)} intro videos ---")
                    for i, video_file in enumerate(video_files):
                        video_output = os.path.join(work_dir, f"intro_video_{i:03d}.mp4")
                        
                        try:
                            original_duration = get_media_duration(video_file)
                            self.log(f"🎬 Intro Video {i+1}/{len(video_files)}: {os.path.basename(video_file)} ({original_duration:.1f}s)")
                            total_video_duration += original_duration
                        except:
                            self.log(f"🎬 Intro Video {i+1}/{len(video_files)}: {os.path.basename(video_file)}")
                        
                        # Apply fade-in to first video, fade-out to last video (if no images)
                        is_first_video = (i == 0)
                        is_last_video = (i == len(video_files) - 1) and not image_files
                        
                        if self.process_video_clip(video_file, video_output, 
                                                 apply_fade_in=is_first_video,
                                                 apply_fade_out=is_last_video):
                            intro_clips.append(video_output)
                        else:
                            self.log(f"⚠️ Skipping failed video: {os.path.basename(video_file)}")
                
                # Calculate time remaining for images
                remaining_time = audio_duration - total_video_duration
                self.log(f"📊 Time remaining for images: {remaining_time:.1f}s")

                # OPTIMIZED: Create ONE cycle of image clips, then loop if needed
                if remaining_time > 0 and image_files:
                    self.log(f"--- Creating optimized slideshow from {len(image_files)} images ---")
                    duration_per_image = CONFIG["image_duration"]
                    total_image_duration_cycle = len(image_files) * duration_per_image
                    
                    # Create clips for ONE cycle only - use helper for proper direction selection
                    single_cycle_clips = []
                    animation_style = CONFIG.get("animation_style", "Sequential Motion")
                    total_images = len(image_files)
                    
                    for i, image_file in enumerate(image_files):
                        clip_output = os.path.join(work_dir, f"image_{i:03d}.mp4")

                        # Use helper function to determine motion direction
                        direction = pick_motion_direction(animation_style, i, total_images)
                        self.log(f"🎬 Motion: {direction} (image {i+1}/{total_images})")
                        
                        # Apply fade-in to first clip if no intro videos
                        is_first = (i == 0 and not intro_clips)
                        
                        # OPTIMIZED: Apply fade-out to last clip if:
                        # - It's the last image in the cycle
                        # - AND we won't be looping (single cycle fills the time)
                        # - OR it's the only cycle needed
                        will_loop = remaining_time > total_image_duration_cycle
                        is_last = (i == len(image_files) - 1) and not will_loop
                        
                        if is_first or is_last:
                            fade_info = []
                            if is_first: fade_info.append("fade-in")
                            if is_last: fade_info.append("fade-out")
                            self.log(f"📸 Image {i+1}/{len(image_files)}: {os.path.basename(image_file)} → {direction} ({', '.join(fade_info)})")
                        else:
                            self.log(f"📸 Image {i+1}/{len(image_files)}: {os.path.basename(image_file)} → {direction}")
                        
                        self.log(f"🚀 DEBUG: About to call create_motion_clip with duration_per_image={duration_per_image}s")
                        if self.create_motion_clip(image_file, clip_output, direction, duration_per_image, is_first, is_last):
                            single_cycle_clips.append(clip_output)
                        else:
                            self.log(f"⚠️ Failed to create motion clip for: {os.path.basename(image_file)}")
                            return False
                    
                    # Create a single slideshow from one cycle
                    if single_cycle_clips:
                        slideshow_one_cycle = os.path.join(work_dir, "slideshow_one_cycle.mp4")
                        
                        if CONFIG.get("use_crossfade", True) and len(single_cycle_clips) > 1:
                            self.log(f"🎞️ Creating slideshow with crossfades...")
                            if not self.apply_crossfade_transitions(single_cycle_clips, slideshow_one_cycle):
                                return False
                            
                            # CLEANUP: Delete motion clips immediately after master video creation (crossfade path)
                            self.log(f"🧹 Cleaning up {len(single_cycle_clips)} motion clips to free storage...")
                            for clip_file in single_cycle_clips:
                                try:
                                    if os.path.exists(clip_file):
                                        os.remove(clip_file)
                                        self.log(f"🗑️ Deleted: {os.path.basename(clip_file)}")
                                except Exception as e:
                                    self.log(f"⚠️ Could not delete {os.path.basename(clip_file)}: {e}")
                        else:
                            self.log("🚀 Creating slideshow without crossfades...")
                            concat_list = os.path.join(work_dir, "concat_images.txt")
                            if not create_concat_file(single_cycle_clips, concat_list):
                                self.log("❌ Failed to create concat file for montage slideshow clips")
                                return False
                            
                            # Use GPU-accelerated stream copy for montage slideshow concatenation
                            gpu_concat_cmd = build_gpu_stream_copy_cmd(concat_list, slideshow_one_cycle, extra_args=['-f', 'concat', '-safe', '0'])
                            if not self.run_ffmpeg(gpu_concat_cmd, "GPU Stream Copy: Concatenating montage slideshow clips"):
                                # Fallback to filter_complex concatenation if concat demuxer fails
                                self.log("🔄 Montage concat demuxer failed, trying filter_complex fallback...")
                                fallback_cmd = build_concat_fallback_cmd(single_cycle_clips, slideshow_one_cycle)
                                if not self.run_ffmpeg(fallback_cmd, "GPU Concat Fallback: Montage using filter_complex"):
                                    return False
                        
                        # CLEANUP: Delete motion clips immediately after master video creation
                        self.log(f"🧹 Cleaning up {len(single_cycle_clips)} motion clips to free storage...")
                        for clip_file in single_cycle_clips:
                            try:
                                if os.path.exists(clip_file):
                                    os.remove(clip_file)
                                    self.log(f"🗑️ Deleted: {os.path.basename(clip_file)}")
                            except Exception as e:
                                self.log(f"⚠️ Could not delete {os.path.basename(clip_file)}: {e}")
                        
                        # Store the clean cycle for intelligent overlay processing later
                        slideshow_one_cycle_clean = slideshow_one_cycle
                        
                        slideshow_base = slideshow_one_cycle
                        cycle_duration = get_media_duration(slideshow_one_cycle)
                        self.log(f"✅ Created base slideshow: {cycle_duration:.1f}s")
                        
                        # If we need more time, loop the slideshow (with overlay already applied)
                        if remaining_time > cycle_duration:
                            loops_needed = math.ceil(remaining_time / cycle_duration)
                            self.log(f"📊 Need to loop slideshow {loops_needed} times to fill {remaining_time:.1f}s")
                            
                            looped_slideshow = os.path.join(work_dir, "slideshow_looped.mp4")
                            
                            # PERFORMANCE OPTIMIZATION: Use stream_loop instead of creating multiple concat entries
                            # This reduces I/O operations and improves performance significantly
                            # Old approach: Created 80+ copies of same file in concat list
                            # New approach: Use FFmpeg stream_loop parameter for efficiency
                            loop_cmd = [
                                'ffmpeg', '-y', '-stream_loop', str(loops_needed - 1), '-i', slideshow_one_cycle,
                                '-c', 'copy', '-t', str(remaining_time), looped_slideshow
                            ]
                            if not self.run_ffmpeg(loop_cmd, f"Stream loop: Efficiently looping slideshow {loops_needed} times"):
                                return False
                            
                            slideshow_base = looped_slideshow
                
                # === STAGE 3: INTELLIGENT OVERLAY APPLICATION ===
                self.log(f"\n=== STAGE 3: Intelligent Overlay Processing ===")
                
                # Initialize overlaid components
                overlaid_intro_clips = []
                overlaid_slideshow_base = None
                
                # STEP 1: Apply overlay to intro videos if present
                if intro_clips and CONFIG.get("use_overlay", False) and overlay_video:
                    self.log(f"🎭 Applying overlay to {len(intro_clips)} intro videos...")
                    
                    for i, intro_clip in enumerate(intro_clips):
                        overlaid_intro = os.path.join(work_dir, f"intro_{i:03d}_overlaid.mp4")
                        intro_duration = get_media_duration(intro_clip)
                        
                        if self.apply_overlay(intro_clip, overlay_video, overlaid_intro, intro_duration):
                            overlaid_intro_clips.append(overlaid_intro)
                            self.log(f"✅ Overlay applied to intro video {i+1}/{len(intro_clips)}")
                        else:
                            # Fallback to original if overlay fails
                            overlaid_intro_clips.append(intro_clip)
                            self.log(f"⚠️ Overlay failed for intro {i+1}, using original")
                else:
                    # No overlay or no intro videos - use originals
                    overlaid_intro_clips = intro_clips[:]
                
                # STEP 2: Apply overlay to slideshow cycle (single cycle only)
                if slideshow_base and CONFIG.get("use_overlay", False) and overlay_video:
                    self.log(f"🎭 Applying overlay to slideshow cycle...")
                    
                    # Use the clean single cycle for overlay application (fallback to slideshow_base if not available)
                    slideshow_one_cycle = slideshow_one_cycle_clean if 'slideshow_one_cycle_clean' in locals() else slideshow_base
                    overlaid_slideshow_cycle = os.path.join(work_dir, "slideshow_cycle_overlaid.mp4")
                    cycle_duration = get_media_duration(slideshow_one_cycle)
                    
                    if self.apply_overlay(slideshow_one_cycle, overlay_video, overlaid_slideshow_cycle, cycle_duration):
                        self.log(f"✅ Overlay applied to slideshow cycle")
                        overlaid_slideshow_base = overlaid_slideshow_cycle
                    else:
                        self.log(f"⚠️ Overlay failed for slideshow, using original")
                        overlaid_slideshow_base = slideshow_base
                else:
                    # No overlay or no slideshow - use original
                    overlaid_slideshow_base = slideshow_base
                
                
                # === STAGE 4: STREAM COPY SLIDESHOW TO FILL REMAINING TIME ===
                self.log(f"\n=== STAGE 4: Stream Copy Slideshow to Fill Audio Length ===")
                master_video_no_audio = os.path.join(work_dir, "master_no_audio.mp4")
                
                # Calculate remaining time after intro videos
                remaining_time = audio_duration - total_video_duration
                
                if remaining_time <= 0:
                    # Intro videos are longer than audio, just use intro videos trimmed
                    self.log(f"✂️ Intro videos ({total_video_duration:.1f}s) >= audio ({audio_duration:.1f}s), trimming intro")
                    if overlaid_intro_clips:
                        # Combine intro videos and trim to audio length
                        if len(overlaid_intro_clips) > 1:
                            combined_intros = os.path.join(work_dir, "combined_intros_final.mp4")
                            intro_concat_list = os.path.join(work_dir, "final_intro_concat.txt")
                            if not create_concat_file(overlaid_intro_clips, intro_concat_list):
                                self.log("❌ Failed to create concat file for intro videos")
                                return False
                            
                            if not self.run_ffmpeg([
                                'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', intro_concat_list,
                                '-t', str(audio_duration),
                                '-c', 'copy', master_video_no_audio
                            ], f"Combining and trimming intro videos to {audio_duration:.1f}s"):
                                return False
                        else:
                            if not self.run_ffmpeg([
                                'ffmpeg', '-y', '-i', overlaid_intro_clips[0],
                                '-t', str(audio_duration),
                                '-c', 'copy', master_video_no_audio
                            ], f"Trimming single intro video to {audio_duration:.1f}s"):
                                return False
                    else:
                        self.log("❌ No intro videos available for trimming")
                        return False
                        
                elif not overlaid_slideshow_base:
                    # Only intro videos, no slideshow
                    self.log(f"✅ Using intro videos only ({total_video_duration:.1f}s)")
                    if len(overlaid_intro_clips) > 1:
                        # Combine multiple intro videos
                        intro_concat_list = os.path.join(work_dir, "final_intro_concat.txt")
                        with open(intro_concat_list, 'w', encoding='utf-8') as f:
                            for intro in overlaid_intro_clips:
                                f.write(f"file '{os.path.abspath(intro)}'\n")
                        
                        if not self.run_ffmpeg([
                            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', intro_concat_list,
                            '-c', 'copy', master_video_no_audio
                        ], "Combining intro videos"):
                            return False
                    else:
                        # Single intro video
                        shutil.copy2(overlaid_intro_clips[0], master_video_no_audio)
                        
                else:
                    # Standard case: intro videos + slideshow to fill remaining time
                    self.log(f"📊 Intro duration: {total_video_duration:.1f}s, Remaining time for slideshow: {remaining_time:.1f}s")
                    
                    # OPTIMIZED APPROACH: Create masters first, then simple assembly
                    self.log(f"🎯 Optimized approach: Create intro master → Create image master → Simple final assembly")
                    
                    intro_master = None
                    slideshow_master = None
                    
                    # Step 1: Create intro master (if intro videos exist)
                    if overlaid_intro_clips:
                        self.log(f"🎬 Creating intro master from {len(overlaid_intro_clips)} videos")
                        intro_master = os.path.join(work_dir, "intro_master.mp4")
                        
                        if len(overlaid_intro_clips) > 1:
                            intro_concat_list = os.path.join(work_dir, "intro_concat.txt")
                            if not create_concat_file(overlaid_intro_clips, intro_concat_list):
                                self.log("❌ Failed to create intro concat file")
                                return False
                            
                            gpu_intro_cmd = build_gpu_stream_copy_cmd(intro_concat_list, intro_master,
                                                                    extra_args=['-f', 'concat', '-safe', '0'])
                            if not self.run_ffmpeg(gpu_intro_cmd, "GPU Stream Copy: Creating intro master"):
                                return False
                        else:
                            shutil.copy2(overlaid_intro_clips[0], intro_master)
                    
                    # Step 2: Create slideshow master (loop slideshow to fill remaining time)
                    if overlaid_slideshow_base and remaining_time > 0:
                        self.log(f"🖼️ Creating slideshow master for {remaining_time:.1f}s")
                        slideshow_master = os.path.join(work_dir, "slideshow_master.mp4")
                        
                        cycle_duration = get_media_duration(overlaid_slideshow_base)
                        loops_needed = math.ceil(remaining_time / cycle_duration)
                        self.log(f"📊 Looping slideshow cycle ({cycle_duration:.1f}s) × {loops_needed} times")
                        
                        # Simple stream_loop approach - much more efficient
                        loop_cmd = [
                            'ffmpeg', '-y', '-stream_loop', str(loops_needed - 1), '-i', overlaid_slideshow_base,
                            '-c', 'copy', '-t', str(remaining_time), slideshow_master
                        ]
                        if not self.run_ffmpeg(loop_cmd, f"Stream loop: Creating slideshow master"):
                            return False
                    
                    # Step 3: Simple final assembly - just concatenate masters with fade if needed
                    components = []
                    if intro_master: components.append(intro_master)
                    if slideshow_master: components.append(slideshow_master)
                    
                    if len(components) == 1:
                        # Only one component, copy it
                        if CONFIG.get("use_fade_out"):
                            component_duration = get_media_duration(components[0])
                            fade_start = component_duration - 0.5
                            fade_cmd = [
                                'ffmpeg', '-y', '-i', components[0],
                                '-vf', f'fade=t=out:st={fade_start}:d=0.5',
                                '-c:a', 'copy', master_video_no_audio
                            ]
                            if not self.run_ffmpeg(fade_cmd, "Adding fade-out to single component"):
                                shutil.copy2(components[0], master_video_no_audio)
                        else:
                            shutil.copy2(components[0], master_video_no_audio)
                    elif len(components) > 1:
                        # Multiple components - concatenate with optional black fade
                        final_concat_list = os.path.join(work_dir, "final_concat.txt")
                        if not create_concat_file(components, final_concat_list):
                            self.log("❌ Failed to create final concat file")
                            return False
                        
                        if CONFIG.get("black_fade_transition", False):
                            # Apply black fade between intro and slideshow
                            self.log(f"🌫️ Applying black fade transition between masters")
                            intro_duration = get_media_duration(intro_master)
                            fade_duration = 0.5
                            
                            transition_cmd = [
                                'ffmpeg', '-y', '-i', intro_master, '-i', slideshow_master,
                                '-filter_complex',
                                f'[0:v]fade=t=out:st={intro_duration - fade_duration}:d={fade_duration}:color=black[intro_fade];'
                                f'[1:v]fade=t=in:st=0:d={fade_duration}:color=black[slide_fade];'
                                f'[intro_fade][slide_fade]concat=n=2:v=1:a=0[v]',
                                '-map', '[v]', '-c:v', 'libx264', '-preset', 'fast', '-crf', '22',
                                master_video_no_audio
                            ]
                            
                            if CONFIG.get("use_fade_out"):
                                # Add final fade-out
                                total_duration = get_media_duration(intro_master) + get_media_duration(slideshow_master)
                                fade_start = total_duration - 0.5
                                transition_cmd[4] += f';[v]fade=t=out:st={fade_start}:d=0.5[vfinal]'
                                transition_cmd[6] = '[vfinal]'
                            
                            if not self.run_ffmpeg(transition_cmd, "Creating final video with black fade"):
                                return False
                        else:
                            # Simple concatenation
                            concat_cmd = build_gpu_stream_copy_cmd(final_concat_list, master_video_no_audio,
                                                                 extra_args=['-f', 'concat', '-safe', '0'])
                            if not self.run_ffmpeg(concat_cmd, "GPU Stream Copy: Final assembly"):
                                return False
                            
                            if CONFIG.get("use_fade_out"):
                                # Add fade-out as separate step
                                temp_final = os.path.join(work_dir, "temp_final.mp4")
                                shutil.move(master_video_no_audio, temp_final)
                                
                                final_duration = get_media_duration(temp_final)
                                fade_start = final_duration - 0.5
                                fade_cmd = [
                                    'ffmpeg', '-y', '-i', temp_final,
                                    '-vf', f'fade=t=out:st={fade_start}:d=0.5',
                                    '-c:a', 'copy', master_video_no_audio
                                ]
                                if not self.run_ffmpeg(fade_cmd, "Adding final fade-out"):
                                    shutil.move(temp_final, master_video_no_audio)
                
                # All processing complete
                master_with_overlay = master_video_no_audio
                self.log(f"🎭 Stream copy assembly complete!")

                # === STAGE 5: FINAL ASSEMBLY (AUDIO & STREAM COPY) ===
                self.log(f"\n=== STAGE 5: Final Assembly ===")
                
                # The master video is finalized, so we can stream copy it for speed.
                final_cmd = ['ffmpeg', '-y']
                final_cmd.extend(['-i', master_with_overlay])
                final_cmd.extend(['-i', processed_audio])
                
                filter_complex_parts = []
                audio_map = "[a_main]"

                # Map inputs correctly: [0:v] is video, [1:a] is main audio
                filter_complex_parts.append(f"[1:a]volume={CONFIG['main_audio_vol']}[a_main]")

                if CONFIG["use_bg_music"] and bg_music:
                    final_cmd.extend(['-stream_loop', '-1', '-i', bg_music])
                    # BG music will be input 2, so [2:a]
                    filter_complex_parts.append(f"[2:a]volume={CONFIG['bg_vol']}[a_bg]")
                    filter_complex_parts.append("[a_main][a_bg]amix=inputs=2:duration=first:dropout_transition=2[a_out]")
                    audio_map = "[a_out]"

                if filter_complex_parts:
                    final_cmd.extend(['-filter_complex', ";".join(filter_complex_parts)])
                
                # Map the final video and audio streams
                final_cmd.extend(['-map', '0:v:0', '-map', audio_map])

                # Use fast stream copy for video, and encode audio
                final_cmd.extend(['-c:v', 'copy'])
                final_cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
                final_cmd.extend(['-t', str(audio_duration)])
                final_cmd.append(output_file)
                
                if not self.run_ffmpeg(final_cmd, "Fast Final Assembly (Stream Copy)"):
                    return False

        except Exception as e:
            self.log(f"❌ An unexpected error occurred: {e}")
            import traceback
            self.log(traceback.format_exc())
            return False
        
        # === SUCCESS ===
        try:
            final_duration = get_media_duration(output_file)
            file_size = os.path.getsize(output_file) / (1024 * 1024)
            
            self.log(f"\n🎉 OPTIMIZED VIDEO CREATION SUCCESS!")
            self.log(f"📁 Output: {output_file}")
            self.log(f"⏱️  Duration: {final_duration:.1f}s")
            self.log(f"💾 Size: {file_size:.1f} MB")
            
            # Enhanced success logging
            if video_files and image_files:
                self.log(f"🎬 Structure: {len(video_files)} intro videos + {len(image_files)} images (looped as needed)")
            elif video_files:
                self.log(f"🎬 Structure: {len(video_files)} videos only")
            else:
                self.log(f"📸 Structure: {len(image_files)} images (looped as needed)")
            
            return True
            
        except Exception as e:
            self.log(f"❌ Verification error: {e}")
            return False

# ===================================================================
# ENHANCED AUTO-CAPTIONING ENGINE WITH GPU ACCELERATION
# ===================================================================

class AutoCaptioner:
    def __init__(self, model_size="tiny", update_callback=None):
        self.update_callback = update_callback or print
        self.model = None
        self.model_size = model_size
        self.model_loaded = False
        self.gpu_options = detect_gpu_acceleration()
        self.engine_type = None  # Will be 'openai' or 'faster'
        self.faster_whisper_available = None  # Cache availability check
        
    def log(self, message):
        if self.update_callback:
            self.update_callback(message)
        print(message)
    
    def check_faster_whisper_availability(self):
        """Check if faster-whisper is available and cache the result."""
        if self.faster_whisper_available is None:
            try:
                from faster_whisper import WhisperModel
                self.faster_whisper_available = True
                self.log("✅ faster-whisper is available")
            except ImportError:
                self.faster_whisper_available = False
                self.log("⚠️ faster-whisper not available, using openai-whisper")
        return self.faster_whisper_available
    
    def should_use_faster_whisper(self):
        """Determine which engine to use based on config and availability."""
        if CONFIG.get("use_faster_whisper", False):
            if self.check_faster_whisper_availability():
                return True
            else:
                self.log("❌ faster-whisper requested but not installed. Install with: pip install faster-whisper")
                self.log("🔄 Falling back to openai-whisper")
                return False
        return False
    
    def load_model(self):
        """Load Whisper model with support for both openai-whisper and faster-whisper."""
        # Check if we need to switch engines or reload
        desired_engine = 'faster' if self.should_use_faster_whisper() else 'openai'
        
        if not self.model_loaded or self.engine_type != desired_engine:
            try:
                start_time = time.time()
                
                if desired_engine == 'faster':
                    self.log(f"Loading faster-whisper model ({self.model_size}) - Enhanced Performance")
                    from faster_whisper import WhisperModel
                    import torch
                    
                    # Always prefer GPU if available
                    if torch.cuda.is_available():
                        device = "cuda"
                        compute_type = "float16"  # Better for GPU
                        self.log(f"Using GPU for faster-whisper")
                    else:
                        device = "cpu"
                        compute_type = "int8"
                        self.log(f"Using CPU for faster-whisper (no GPU available)")
                    
                    self.model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
                    self.engine_type = 'faster'
                    
                else:  # openai-whisper
                    self.log(f"Loading openai-whisper model ({self.model_size}) - Standard")
                    import whisper
                    import torch
                    
                    # Always prefer GPU if available, regardless of model size
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                    self.log(f"Using: {device}")
                    
                    self.model = whisper.load_model(self.model_size, device=device)
                    self.engine_type = 'openai'
                
                load_time = time.time() - start_time
                self.log(f"{self.engine_type}-whisper model loaded in {load_time:.1f} seconds")
                self.model_loaded = True
                return True
                
            except ImportError as e:
                if desired_engine == 'faster':
                    self.log("faster-whisper not installed. Install with: pip install faster-whisper")
                else:
                    self.log("openai-whisper not installed. Install with: pip install openai-whisper")
                return False
            except Exception as e:
                self.log(f"Failed to load {desired_engine}-whisper model: {e}")
                return False
        else:
            # Model already loaded with correct engine
            self.log(f"{self.engine_type}-whisper model already loaded and ready")
            return True
    
    def transcribe_universal(self, audio_path, word_timestamps=False):
        """Universal transcription method that works with both engines."""
        if not self.load_model():
            raise Exception("Failed to load transcription model")
        
        if self.engine_type == 'faster':
            # faster-whisper transcription
            segments, info = self.model.transcribe(
                audio_path,
                word_timestamps=word_timestamps,
                vad_filter=True
            )
            # Convert generator to list and format for compatibility
            segments_list = []
            for segment in segments:
                segment_dict = {
                    'text': segment.text,
                    'start': segment.start,
                    'end': segment.end
                }
                # Add words if requested
                if word_timestamps and hasattr(segment, 'words') and segment.words:
                    segment_dict['words'] = [
                        {'word': w.word, 'start': w.start, 'end': w.end}
                        for w in segment.words if w.start is not None and w.end is not None
                    ]
                segments_list.append(segment_dict)
            
            return {'segments': segments_list}
            
        else:  # openai-whisper
            # Standard openai-whisper transcription
            return self.model.transcribe(audio_path, verbose=False, fp16=False, word_timestamps=word_timestamps)
    
    def add_captions_to_video(self, video_path):
        """REFACTORED: Adds captions and REPLACES the original video file safely."""
        # CHECK: Only proceed if captions are actually enabled
        captions_enabled = CONFIG.get("captions_enabled", False)
        self.log(f"🚀 DEBUG: add_captions_to_video called - captions_enabled: {captions_enabled}")
        if not captions_enabled:
            self.log("🛑 Captions are disabled - skipping captioning")
            return True  # Return True since this isn't an error, just disabled
            
        if not os.path.exists(video_path):
            self.log(f"❌ Video file not found for captioning: {video_path}")
            return False

        if not self.load_model():
            self.log("❌ Failed to load Whisper model for captioning")
            return False

        name, ext = os.path.splitext(video_path)
        temp_output_path = f"{name}_captioned_temp{ext}"
        
        # Check if karaoke effect is enabled
        karaoke_effect = CONFIG.get("karaoke_effect_enabled", False)
        
        if karaoke_effect:
            subtitle_path = f"{name}_temp.ass"
            self.log("🎤 Karaoke effect enabled - using ASS format")
        else:
            subtitle_path = f"{name}_temp.srt"
            self.log("📝 Standard captions - using SRT format")

        try:
            # Step 1: Transcribe audio
            self.log(f"📍 AUTO-CAPTIONING: Transcribing audio from {os.path.basename(video_path)}...")
            
            if karaoke_effect:
                # Extract audio and transcribe with word-level timestamps for karaoke
                audio_path = f"{name}_temp_audio.wav"
                self.log("🎵 Extracting audio for karaoke transcription...")
                
                # Extract audio using FFmpeg
                cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    self.log(f"❌ Failed to extract audio: {result.stderr}")
                    return False
                
                # Get word-level timestamps
                words = self.transcribe_with_word_timestamps(audio_path)
                
                # Clean up temporary audio file
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                
                if not words:
                    self.log("❌ No words found in karaoke transcription. Skipping captioning.")
                    return True
                
                # Generate ASS file with karaoke effect
                if not self.generate_karaoke_ass(words, subtitle_path):
                    return False
                    
            else:
                # Standard transcription for regular captions
                word_timestamps = CONFIG.get("live_timing_enabled", False)
                result = self.transcribe_universal(video_path, word_timestamps=word_timestamps)
                segments = result.get('segments', [])
                
                if not segments:
                    self.log("❌ No speech segments found in audio. Skipping captioning.")
                    return True # Not a failure, just nothing to do.

                self.log(f"✅ Found {len(segments)} speech segments")
                
                # Generate SRT file
                self.generate_srt_file(segments, subtitle_path, CONFIG.get("caption_type", "single"))
                
            if not os.path.exists(subtitle_path):
                self.log(f"❌ Failed to create subtitle file: {subtitle_path}")
                return False
            
            # Step 3: Burn subtitles to a temporary file
            if not self.burn_subtitles(video_path, subtitle_path, temp_output_path):
                 self.log(f"❌ Caption burning failed for: {os.path.basename(video_path)}")
                 return False

            # Step 4: Safely replace the original file with the captioned version
            self.log(f"✅ Replacing original video with captioned version...")
            shutil.move(temp_output_path, video_path)
            self.log(f"🎉 Captioning complete for: {os.path.basename(video_path)}")
            return True

        except Exception as e:
            self.log(f"❌ Auto-captioning error: {e}")
            import traceback
            self.log(traceback.format_exc())
            return False
        finally:
            # Clean up temporary files
            if os.path.exists(subtitle_path):
                os.remove(subtitle_path)
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)

    def generate_srt_file(self, segments, srt_path, caption_type):
        """Create an SRT file from transcription segments with proper pacing."""
        self.log(f"✍️ Creating {caption_type} captions...")
        sentences = []
        
        max_chars = CONFIG.get("max_chars_per_line", 45)  # Maximum chars per caption
        min_gap = 0.1  # Minimum gap between captions (seconds)
        
        # Handle new caption animation types
        caption_animation = CONFIG.get("caption_animation", "normal")
        word_by_word_enabled = CONFIG.get("word_by_word_enabled", False)
        live_timing_enabled = CONFIG.get("live_timing_enabled", False)
        
        # Check toggle settings first - these override any caption_animation settings
        if word_by_word_enabled:
            self.log("✍️ Word-by-word toggle enabled - using chunk mode")
            return self.generate_word_by_word_chunks_srt(segments, srt_path)
        elif live_timing_enabled:
            self.log("⏱️ Live timing toggle enabled")
            return self.generate_live_timing_srt(segments, srt_path)
        # Only check caption_animation if neither toggle is enabled
        elif caption_animation == "word_by_word":
            self.log("✍️ Caption animation word-by-word mode (no toggle override)")
            return self.generate_word_by_word_srt(segments, srt_path)
        elif caption_animation == "single_words":
            self.log("✍️ Caption animation single words mode")
            return self.generate_single_words_srt(segments, srt_path)
        
        if caption_type == "single":
            # Single line captions with proper pacing
            for segment in segments:
                text = segment['text'].strip()
                if not text or len(text) < 2:
                    continue
                
                start_time = segment['start']
                end_time = segment['end']
                
                # For short segments that fit on one line
                if len(text) <= max_chars:
                    sentences.append({
                        'start': start_time,
                        'end': end_time,
                        'text': text
                    })
                else:
                    # Split long text intelligently
                    words = text.split()
                    chunks = []
                    current_chunk = []
                    current_length = 0
                    
                    # Group words into chunks that fit the character limit
                    for word in words:
                        word_length = len(word) + (1 if current_chunk else 0)
                        
                        if current_length + word_length <= max_chars:
                            current_chunk.append(word)
                            current_length += word_length
                        else:
                            if current_chunk:
                                chunks.append(' '.join(current_chunk))
                            current_chunk = [word]
                            current_length = len(word)
                    
                    # Add the last chunk
                    if current_chunk:
                        chunks.append(' '.join(current_chunk))
                    
                    # Distribute time proportionally based on character count
                    total_chars = sum(len(chunk) for chunk in chunks)
                    segment_duration = end_time - start_time
                    
                    chunk_start = start_time
                    for i, chunk in enumerate(chunks):
                        # Calculate proportional duration
                        chunk_proportion = len(chunk) / total_chars if total_chars > 0 else 1/len(chunks)
                        chunk_duration = segment_duration * chunk_proportion
                        
                        # Respect original pacing - don't compress too much
                        min_chunk_duration = chunk_duration * 0.8
                        
                        chunk_end = chunk_start + max(chunk_duration, min_chunk_duration)
                        
                        # Don't exceed segment end
                        if i == len(chunks) - 1:
                            chunk_end = end_time
                        else:
                            chunk_end = min(chunk_end, end_time)
                        
                        sentences.append({
                            'start': chunk_start,
                            'end': chunk_end,
                            'text': chunk
                        })
                        
                        chunk_start = chunk_end
        else:
            # Multi-line captions - group segments intelligently
            current_sentence = ""
            current_start = 0
            max_chars_multi = 80  # More chars allowed for multi-line
            
            for segment in segments:
                text = segment['text'].strip()
                if text:
                    if not current_sentence:
                        current_sentence = text
                        current_start = segment['start']
                    elif len(current_sentence) + len(text) + 1 < max_chars_multi:
                        current_sentence += " " + text
                    else:
                        sentences.append({
                            'start': current_start, 
                            'end': segment['start'], 
                            'text': current_sentence
                        })
                        current_sentence = text
                        current_start = segment['start']
            
            if current_sentence:
                sentences.append({
                    'start': current_start, 
                    'end': segments[-1]['end'], 
                    'text': current_sentence
                })
        
        # Add small gaps between captions for readability
        for i in range(len(sentences) - 1):
            if sentences[i + 1]['start'] - sentences[i]['end'] < min_gap:
                gap_available = sentences[i + 1]['start'] - sentences[i]['end']
                if gap_available > 0:
                    sentences[i]['end'] = sentences[i + 1]['start'] - min_gap
        
        # Write SRT file
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, sentence in enumerate(sentences, 1):
                f.write(f"{i}\n")
                f.write(f"{self.format_srt_timestamp(sentence['start'])} --> {self.format_srt_timestamp(sentence['end'])}\n")
                # Ensure single line for single mode
                if caption_type == "single":
                    sentence['text'] = sentence['text'].replace('\n', ' ').strip()
                f.write(f"{sentence['text']}\n\n")
        
        self.log(f"✅ Created {len(sentences)} {caption_type} captions with proper pacing")

    def generate_word_by_word_srt(self, segments, srt_path):
        """Generate word-by-word captions that build up in a line (typewriter effect)."""
        self.log("✍️ Creating word-by-word (typewriter) captions...")
        captions = []
        caption_index = 1
        
        for segment in segments:
            text = segment['text'].strip()
            if not text:
                continue
                
            words = text.split()
            if not words:
                continue
                
            segment_duration = segment['end'] - segment['start']
            time_per_word = segment_duration / len(words) if len(words) > 0 else 0.5
            
            # Build up the sentence word by word
            accumulated_text = ""
            for i, word in enumerate(words):
                if i > 0:
                    accumulated_text += " "
                accumulated_text += word
                
                word_start = segment['start'] + (i * time_per_word)
                word_end = segment['start'] + ((i + 1) * time_per_word)
                
                captions.append({
                    'index': caption_index,
                    'start': word_start,
                    'end': word_end,
                    'text': accumulated_text
                })
                caption_index += 1
        
        # Write SRT file
        with open(srt_path, 'w', encoding='utf-8') as f:
            for caption in captions:
                f.write(f"{caption['index']}\n")
                f.write(f"{self.format_srt_timestamp(caption['start'])} --> {self.format_srt_timestamp(caption['end'])}\n")
                f.write(f"{caption['text']}\n\n")
        
        self.log(f"✅ Created {len(captions)} word-by-word captions")

    def generate_single_words_srt(self, segments, srt_path):
        """Generate single word captions that appear one by one."""
        self.log("✍️ Creating single word captions...")
        captions = []
        caption_index = 1
        
        for segment in segments:
            text = segment['text'].strip()
            if not text:
                continue
                
            words = text.split()
            if not words:
                continue
                
            segment_duration = segment['end'] - segment['start']
            time_per_word = segment_duration / len(words) if len(words) > 0 else 0.5
            
            # Show each word individually
            for i, word in enumerate(words):
                word_start = segment['start'] + (i * time_per_word)
                word_end = segment['start'] + ((i + 1) * time_per_word)
                
                captions.append({
                    'index': caption_index,
                    'start': word_start,
                    'end': word_end,
                    'text': word.upper()  # Make single words stand out
                })
                caption_index += 1
        
        # Write SRT file
        with open(srt_path, 'w', encoding='utf-8') as f:
            for caption in captions:
                f.write(f"{caption['index']}\n")
                f.write(f"{self.format_srt_timestamp(caption['start'])} --> {self.format_srt_timestamp(caption['end'])}\n")
                f.write(f"{caption['text']}\n\n")
        
        self.log(f"✅ Created {len(captions)} single word captions")

    def generate_word_by_word_chunks_srt(self, segments, srt_path):
        """Generate word-by-word chunks (1-3 words at a time) captions."""
        self.log("✍️ Creating word-by-word chunks (1-3 words) captions...")
        captions = []
        caption_index = 1
        
        for segment in segments:
            text = segment['text'].strip()
            if not text:
                continue
                
            words = text.split()
            if not words:
                continue
                
            segment_duration = segment['end'] - segment['start']
            
            # Group words into chunks of 1-3 words
            chunks = []
            i = 0
            while i < len(words):
                # Randomly choose 1-3 words for each chunk
                import random
                chunk_size = random.choice([1, 2, 3])
                chunk_words = words[i:i+chunk_size]
                chunks.append(' '.join(chunk_words))
                i += chunk_size
            
            if not chunks:
                continue
                
            time_per_chunk = segment_duration / len(chunks) if len(chunks) > 0 else 0.5
            
            # Show each chunk
            for i, chunk in enumerate(chunks):
                chunk_start = segment['start'] + (i * time_per_chunk)
                chunk_end = segment['start'] + ((i + 1) * time_per_chunk)
                
                captions.append({
                    'index': caption_index,
                    'start': chunk_start,
                    'end': chunk_end,
                    'text': chunk
                })
                caption_index += 1
        
        # Write SRT file
        with open(srt_path, 'w', encoding='utf-8') as f:
            for caption in captions:
                f.write(f"{caption['index']}\n")
                f.write(f"{self.format_srt_timestamp(caption['start'])} --> {self.format_srt_timestamp(caption['end'])}\n")
                f.write(f"{caption['text']}\n\n")
        
        self.log(f"✅ Created {len(captions)} word-by-word chunk captions")

    def generate_live_timing_srt(self, segments, srt_path):
        """Generate live timing captions where words appear as they're spoken (2 lines max)."""
        self.log("⏱️ Creating live timing captions - words appear as spoken...")
        captions = []
        caption_index = 1
        
        for segment in segments:
            text = segment['text'].strip()
            if not text:
                continue
            
            # Check if we have word-level timestamps
            words_data = segment.get('words', [])
            if not words_data:
                # Fallback: estimate word timing if no word-level data
                words = text.split()
                segment_duration = segment['end'] - segment['start']
                time_per_word = segment_duration / len(words) if len(words) > 0 else 0.5
                
                words_data = []
                for i, word in enumerate(words):
                    word_start = segment['start'] + (i * time_per_word)
                    word_end = segment['start'] + ((i + 1) * time_per_word)
                    words_data.append({
                        'word': word,
                        'start': word_start,
                        'end': word_end
                    })
            
            # Create progressive captions - each word adds to the previous text
            accumulated_words = []
            max_chars_per_line = 35  # Shorter lines for live timing
            
            for i, word_data in enumerate(words_data):
                word = word_data.get('word', '').strip()
                if not word:
                    continue
                    
                accumulated_words.append(word)
                current_text = ' '.join(accumulated_words)
                
                # Break into max 2 lines
                words_in_text = current_text.split()
                if len(' '.join(words_in_text)) > max_chars_per_line:
                    # Find good break point for 2 lines
                    mid_point = len(words_in_text) // 2
                    line1 = ' '.join(words_in_text[:mid_point])
                    line2 = ' '.join(words_in_text[mid_point:])
                    
                    # If second line is too long, truncate accumulated_words
                    if len(line2) > max_chars_per_line:
                        # Remove oldest words to keep within 2 lines
                        while len(' '.join(accumulated_words)) > max_chars_per_line * 2:
                            accumulated_words.pop(0)
                        
                        # Recreate text and lines
                        current_text = ' '.join(accumulated_words)
                        words_in_text = current_text.split()
                        if len(words_in_text) > 1:
                            mid_point = len(words_in_text) // 2
                            line1 = ' '.join(words_in_text[:mid_point])
                            line2 = ' '.join(words_in_text[mid_point:])
                        else:
                            line1 = current_text
                            line2 = ""
                    
                    display_text = f"{line1}\n{line2}" if line1 and line2 else current_text
                else:
                    display_text = current_text
                
                # Each caption should last until the next word appears
                word_start = word_data.get('start', segment['start'])
                if i + 1 < len(words_data):
                    # End when next word starts
                    word_end = words_data[i + 1].get('start', word_start + 0.5)
                else:
                    # Last word - end at segment end
                    word_end = segment['end']
                
                captions.append({
                    'index': caption_index,
                    'start': word_start,
                    'end': word_end,
                    'text': display_text
                })
                caption_index += 1
        
        # Write SRT file
        with open(srt_path, 'w', encoding='utf-8') as f:
            for caption in captions:
                f.write(f"{caption['index']}\n")
                f.write(f"{self.format_srt_timestamp(caption['start'])} --> {self.format_srt_timestamp(caption['end'])}\n")
                f.write(f"{caption['text']}\n\n")
        
        self.log(f"✅ Created {len(captions)} live timing captions (words appear as spoken)")

    def parse_ffmpeg_time(self, time_str):
        """Parse FFmpeg time format (HH:MM:SS.ss) to seconds"""
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                hours, minutes, seconds = parts
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        except:
            pass
        return None

    def burn_subtitles(self, video_path, subtitle_path, output_path):
        """Burns subtitles onto the video using GPU acceleration with detailed progress."""
        caption_style = CONFIG.get("caption_style", "Custom")
        karaoke_effect = CONFIG.get("karaoke_effect_enabled", False)
        
        if karaoke_effect:
            self.log(f"🎤 Burning ASS subtitles with karaoke effect...")
        else:
            self.log(f"🔥 Burning subtitles with '{caption_style}' style...")

        # Get video duration for progress tracking
        duration = get_media_duration(video_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Determine subtitle format and copy to temp directory
            _, ext = os.path.splitext(subtitle_path)
            if ext.lower() == '.ass':
                temp_subtitle_path = os.path.join(temp_dir, "captions.ass")
            else:
                temp_subtitle_path = os.path.join(temp_dir, "captions.srt")
            
            shutil.copy2(subtitle_path, temp_subtitle_path)
            
            # Fix path for FFmpeg (Windows compatibility)
            temp_subtitle_path_ffmpeg = temp_subtitle_path.replace('\\', '/').replace(':', '\\:')
            
            # Build FFmpeg command
            cmd = ['ffmpeg', '-y']
            
            # Add hardware acceleration for input if GPU available
            if CONFIG["use_gpu"] and self.gpu_options:
                self.log("📍 FFMPEG: Adding GPU hardware acceleration for input")
                cmd.extend(['-hwaccel', 'auto'])
            
            cmd.extend(['-i', video_path])
            
            # Configure subtitle filter based on style and format
            if karaoke_effect:
                # For karaoke mode, use ASS file directly without style overrides
                self.log("🎤 Using ASS subtitles with karaoke timing effects")
                cmd.extend(['-vf', f"subtitles='{temp_subtitle_path_ffmpeg}'"])
            elif caption_style == "Classic":
                self.log("⚡ Using simple caption method (fastest)")
                cmd.extend(['-vf', f"subtitles='{temp_subtitle_path_ffmpeg}'"])
            elif caption_style == "Basic":
                self.log("🎨 Using Basic preset")
                style_string = "FontName=Arial,FontSize=28,Bold=1,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=1,Shadow=1"
                cmd.extend(['-vf', f"subtitles='{temp_subtitle_path_ffmpeg}':force_style='{style_string}'"])
            elif caption_style == "Outline":
                self.log("🎨 Using Outline preset")
                style_string = "FontName=Arial,FontSize=28,Bold=1,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=2,Shadow=0"
                cmd.extend(['-vf', f"subtitles='{temp_subtitle_path_ffmpeg}':force_style='{style_string}'"])
            elif caption_style == "Boxed":
                self.log("🎨 Using Boxed preset")
                style_string = "FontName=Arial,FontSize=28,Bold=1,PrimaryColour=&HFFFFFF&,BackColour=&H80000000&,Outline=0,Shadow=0"
                cmd.extend(['-vf', f"subtitles='{temp_subtitle_path_ffmpeg}':force_style='{style_string}'"])
            elif caption_style == "Karaoke":
                self.log("🎨 Using Karaoke preset")
                style_string = "FontName=Comic Sans MS,FontSize=32,Bold=1,PrimaryColour=&H00FFFF&,OutlineColour=&H3900C7&,Outline=2,Shadow=0"
                cmd.extend(['-vf', f"subtitles='{temp_subtitle_path_ffmpeg}':force_style='{style_string}'"])
            else:
                self.log("🎨 Using styled caption method with custom settings")
                # Build style string from user's custom settings
                style_parts = []
                
                # Font settings
                style_parts.append(f"FontName={CONFIG.get('font_family', 'Arial')}")
                style_parts.append(f"FontSize={CONFIG.get('font_size', 24)}")
                
                # Color settings - convert hex to BGR format for ASS
                text_color = CONFIG.get('text_color', '#FFFFFF').replace('#', '')
                text_color_bgr = f"&H{text_color[4:6]}{text_color[2:4]}{text_color[0:2]}&"
                style_parts.append(f"PrimaryColour={text_color_bgr}")
                
                outline_color = CONFIG.get('outline_color', '#000000').replace('#', '')
                outline_color_bgr = f"&H{outline_color[4:6]}{outline_color[2:4]}{outline_color[0:2]}&"
                style_parts.append(f"OutlineColour={outline_color_bgr}")
                
                # Default transparent background
                style_parts.append("BackColour=&H80000000&")
                
                # Border style and outline width
                style_parts.append("BorderStyle=1")  # Outline only by default
                style_parts.append(f"Outline={CONFIG.get('outline_width', 2)}")
                
                # Position settings
                v_pos = CONFIG.get('vertical_position', 'bottom')
                h_pos = CONFIG.get('horizontal_position', 'center')
                
                # Calculate alignment value (1-9 based on position)
                alignment = 2  # Default bottom center
                if v_pos == 'top':
                    if h_pos == 'left': alignment = 7
                    elif h_pos == 'center': alignment = 8
                    elif h_pos == 'right': alignment = 9
                elif v_pos == 'middle':
                    if h_pos == 'left': alignment = 4
                    elif h_pos == 'center': alignment = 5
                    elif h_pos == 'right': alignment = 6
                else:  # bottom
                    if h_pos == 'left': alignment = 1
                    elif h_pos == 'center': alignment = 2
                    elif h_pos == 'right': alignment = 3
                
                style_parts.append(f"Alignment={alignment}")
                
                # Margins
                style_parts.append(f"MarginV={CONFIG.get('margin_vertical', 30)}")
                style_parts.append(f"MarginL={CONFIG.get('margin_horizontal', 20)}")
                style_parts.append(f"MarginR={CONFIG.get('margin_horizontal', 20)}")
                
                # Font weight
                if CONFIG.get('font_weight', 'normal') == 'bold':
                    style_parts.append("Bold=1")
                elif CONFIG.get('font_weight', 'normal') == 'italic':
                    style_parts.append("Italic=1")
                elif CONFIG.get('font_weight', 'normal') == 'bold italic':
                    style_parts.append("Bold=1")
                    style_parts.append("Italic=1")
                
                # Shadow settings
                if CONFIG.get('shadow_enabled', True):
                    style_parts.append(f"Shadow={CONFIG.get('shadow_blur', 2)}")
                else:
                    style_parts.append("Shadow=0")
                
                # Background box (only if explicitly enabled)
                if CONFIG.get('background_opacity', 0.0) > 0 and CONFIG.get('use_caption_background', False):
                    bg_color = CONFIG.get('background_color', '#000000').replace('#', '')
                    bg_color_bgr = f"&H{bg_color[4:6]}{bg_color[2:4]}{bg_color[0:2]}"
                    bg_alpha = hex(int(255 * (1 - CONFIG.get('background_opacity', 0.0))))[2:].upper().zfill(2)
                    style_parts.append(f"BackColour=&H{bg_alpha}{bg_color_bgr}&")
                    style_parts.append("BorderStyle=3")  # Box style with outline
                
                style_string = ",".join(style_parts)
                self.log(f"📍 Caption style: {style_string}")
                
                subtitle_filter = f"subtitles='{temp_subtitle_path_ffmpeg}':force_style='{style_string}'"
                cmd.extend(['-vf', subtitle_filter])
            
            # Configure output encoding with GPU preference
            cmd.extend(get_gpu_encoder_settings())
            cmd.extend(['-c:a', 'copy']) # Copy original audio
            cmd.append(output_path)
            
            # Execute FFmpeg with real-time progress monitoring
            return self._run_ffmpeg_with_progress(cmd, duration)

    def _run_ffmpeg_with_progress(self, cmd, duration):
        """FIXED: Execute FFmpeg with detailed real-time progress monitoring and better process handling."""
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        process = None
        try:
            start_time = time.time()
            
            self.log("📍 STATUS: Starting FFmpeg subtitle burning process...")
            
            # FIXED: Add environment variables to prevent FFmpeg conflicts
            env = os.environ.copy()
            env['FFREPORT'] = 'file=NUL:'  # Disable FFmpeg report file on Windows
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                startupinfo=startupinfo,
                encoding='utf-8',
                errors='replace',
                env=env  # FIXED: Use clean environment
            )
            
            # Track this process for force kill
            if hasattr(self.update_callback, '__self__'):
                api = self.update_callback.__self__
                if hasattr(api, 'active_processes'):
                    api.active_processes.append(process)
            
            self.log("🔥 FFmpeg processing subtitles...")
            
            last_update = time.time()
            
            # FIXED: Better output handling and error detection
            output_lines = []
            error_detected = False
            
            # Monitor progress with detailed reporting
            while True:
                # Check if cancelled
                if hasattr(self.update_callback, '__self__'):
                    api = self.update_callback.__self__
                    if hasattr(api, 'processing_cancelled') and api.processing_cancelled:
                        self.log("🛑 Cancellation detected - killing FFmpeg process...")
                        process.kill()
                        process.wait()
                        self.log("💀 FFmpeg process killed")
                        return False
                
                output = process.stdout.readline()
                
                if output == '' and process.poll() is not None:
                    self.log("📍 STATUS: FFmpeg processing completed")
                    break
                
                current_time = time.time()
                
                # FIXED: Better error detection in FFmpeg output
                if output.strip():
                    output_lines.append(output.strip())
                    
                    # Check for critical errors
                    lower_output = output.lower()
                    if any(error_term in lower_output for error_term in ['error', 'failed', 'invalid', 'permission denied', 'access denied']):
                        if 'error' in lower_output and 'no error' not in lower_output:
                            error_detected = True
                            self.log(f"⚠️ FFmpeg Error Detected: {output.strip()}")
                
                if output and 'time=' in output:
                    try:
                        # Parse current processing time
                        time_part = output.split('time=')[1].split()[0]
                        current_seconds = self.parse_ffmpeg_time(time_part)
                        
                        if current_seconds and duration and duration > 0:
                            progress = min(current_seconds / duration * 100, 100)
                            elapsed = current_time - start_time
                            
                            # Update every 2 seconds with detailed info
                            if (current_time - last_update) >= 2.0:
                                if progress > 0 and elapsed > 0:
                                    eta = (elapsed / progress * 100) - elapsed if progress > 0 else 0
                                    processing_speed = current_seconds / elapsed if elapsed > 0 else 0
                                    self.log(f"📍 SUBTITLE PROGRESS: {progress:.1f}% | {current_seconds:.1f}s/{duration:.1f}s | Speed: {processing_speed:.2f}x | ETA: {eta:.0f}s")
                                else:
                                    self.log(f"📍 SUBTITLE PROGRESS: {progress:.1f}% | {current_seconds:.1f}s/{duration:.1f}s")
                                last_update = current_time
                    except Exception as e:
                        # Don't spam with parsing errors
                        pass
                
                # Fallback progress indicator
                elif output and 'fps=' in output and (current_time - last_update) >= 3.0:
                    self.log("📍 SUBTITLE STATUS: Processing video frames... (active)")
                    last_update = current_time
            
            # Check final result
            return_code = process.poll()
            total_time = time.time() - start_time
            
            self.log(f"📍 STATUS: FFmpeg process finished with return code {return_code}")
            
            # FIXED: Better success/failure detection
            if return_code == 0 and not error_detected:
                self.log(f"📍 STATUS: Subtitle burning completed successfully!")
                self.log(f"✅ Subtitles burned in {total_time:.1f} seconds!")
                
                if duration and total_time > 0:
                    speed_ratio = duration / total_time
                    self.log(f"📍 PERFORMANCE: Processed at {speed_ratio:.2f}x realtime speed")
                    
                    if speed_ratio >= 3.0:
                        self.log("⚡ Excellent performance - very fast processing!")
                    elif speed_ratio >= 2.0:
                        self.log("✅ Good performance - efficient processing!")
                    else:
                        self.log("📊 Standard performance - reliable processing!")
                
                self.log("🎉 AUTO-CAPTIONING COMPLETE!")
                return True
            else:
                self.log(f"❌ FFmpeg subtitle error: return code {return_code}")
                
                # FIXED: Show relevant error information
                if error_detected and output_lines:
                    error_lines = [line for line in output_lines[-10:] if 'error' in line.lower()]
                    if error_lines:
                        self.log(f"📍 Last error: {error_lines[-1]}")
                
                return False
                
        except Exception as e:
            if process:
                try:
                    process.kill()
                    process.wait()
                except:
                    pass
            self.log(f"❌ FFmpeg execution error: {e}")
            return False
        
        finally:
            # FIXED: Ensure process cleanup
            if process and hasattr(self.update_callback, '__self__'):
                api = self.update_callback.__self__
                if hasattr(api, 'active_processes') and process in api.active_processes:
                    api.active_processes.remove(process)
            
            # FIXED: Force garbage collection after FFmpeg process
            try:
                import gc
                gc.collect()
            except:
                pass

    def format_srt_timestamp(self, seconds):
        """Convert seconds to SRT timestamp format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    def transcribe_with_word_timestamps(self, audio_path):
        """Transcribe audio with word-level timestamps for karaoke effect using universal method."""
        self.log(f"🎤 Transcribing for karaoke effect...")
        
        # Use universal transcription with word timestamps
        try:
            result = self.transcribe_universal(audio_path, word_timestamps=True)
            segments = result.get('segments', [])
            
            words = []
            for segment in segments:
                self.log(f"📝 Segment: {segment.get('text', '')}")
                if 'words' in segment:
                    for word_data in segment['words']:
                        if word_data.get('start') is not None and word_data.get('end') is not None:
                            words.append({
                                'text': word_data['word'].strip(),
                                'start': word_data['start'],
                                'end': word_data['end']
                            })
            
            if not words and self.engine_type == 'openai':
                self.log("⚠️ No word-level timestamps found. For better karaoke results, consider enabling 'Use Faster Whisper' in Advanced settings")
            
            self.log(f"✅ Found {len(words)} words with timestamps")
            return words
            
        except Exception as e:
            self.log(f"❌ Karaoke transcription failed: {e}")
            return []

    def format_ass_time(self, seconds):
        """Convert seconds to ASS time format H:MM:SS.CC"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def create_ass_header(self):
        """Create ASS file header with custom styling based on user settings."""
        # Get user's custom settings
        font_family = CONFIG.get("font_family", "Arial")
        font_size = CONFIG.get("font_size", 24)
        text_color = CONFIG.get("text_color", "#FFFFFF")
        outline_color = CONFIG.get("outline_color", "#000000")
        outline_width = CONFIG.get("outline_width", 2)
        font_weight = CONFIG.get("font_weight", "bold")
        margin_vertical = CONFIG.get("margin_vertical", 25)
        margin_horizontal = CONFIG.get("margin_horizontal", 20)
        vertical_position = CONFIG.get("vertical_position", "bottom")
        
        # Map vertical position to ASS alignment
        alignment_map = {"top": 8, "middle": 5, "bottom": 2}
        alignment = alignment_map.get(vertical_position, 2)
        
        # Convert hex colors to ASS format (BGR with alpha)
        def hex_to_ass_color(hex_color):
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return f"&H00{b:02X}{g:02X}{r:02X}"
            return "&H00FFFFFF"
        
        primary_color = hex_to_ass_color(text_color)
        outline_color_ass = hex_to_ass_color(outline_color)
        bold = 1 if font_weight == "bold" else 0
        
        return f"""[Script Info]
Title: VideoStove Karaoke Captions
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_family},{font_size},{primary_color},&H000000FF,{outline_color_ass},&H80000000,{bold},0,0,0,100,100,0,0,1,{outline_width},0,{alignment},{margin_horizontal},{margin_horizontal},{margin_vertical},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def generate_karaoke_ass(self, words, ass_path):
        """Generate ASS file with karaoke effect (word-by-word timing)."""
        self.log("🎬 Creating karaoke ASS file...")
        
        # Create ASS header with user's styling
        ass_content = self.create_ass_header()
        
        # Group words into sentences (max 2 lines, shorter sentences)
        current_sentence = []
        sentences = []
        
        for word in words:
            current_sentence.append(word)
            # End sentence on punctuation or every 4-5 words
            if (word['text'].endswith(('.', '!', '?')) or 
                len(current_sentence) >= 5):
                if current_sentence:
                    sentences.append(current_sentence)
                    current_sentence = []
        
        if current_sentence:
            sentences.append(current_sentence)
        
        self.log(f"📝 Created {len(sentences)} sentences for karaoke")
        
        # Create karaoke effect
        for sentence_idx, sentence_words in enumerate(sentences):
            if not sentence_words:
                continue
                
            sentence_text = " ".join(w['text'] for w in sentence_words)
            self.log(f"📝 Sentence {sentence_idx + 1}: {sentence_text}")
            
            # Create word-by-word karaoke effect
            for word_idx, word in enumerate(sentence_words):
                start_time = word['start']
                
                # End time is when next word starts, or word ends if last word
                if word_idx < len(sentence_words) - 1:
                    end_time = sentence_words[word_idx + 1]['start']
                else:
                    end_time = word['end']
                
                # Build text with karaoke coloring
                text_parts = []
                for i, w in enumerate(sentence_words):
                    if i < word_idx:
                        # Words already spoken - keep visible in highlight color
                        text_parts.append(f"{{\\c&H00FFFF&}}{w['text']}{{\\c&HFFFFFF&}}")
                    elif i == word_idx:
                        # Current word being spoken - highlight color
                        text_parts.append(f"{{\\c&H00FFFF&}}{w['text']}{{\\c&HFFFFFF&}}")
                    else:
                        # Words not yet spoken - completely transparent
                        text_parts.append(f"{{\\alpha&HFF&}}{w['text']}{{\\alpha&H00&}}")
                
                karaoke_text = " ".join(text_parts)
                
                # Create dialogue line
                dialogue = f"Dialogue: 0,{self.format_ass_time(start_time)},{self.format_ass_time(end_time)},Default,,0,0,0,,{karaoke_text}"
                ass_content += dialogue + "\n"
        
        # Write ASS file
        try:
            with open(ass_path, 'w', encoding='utf-8') as f:
                f.write(ass_content)
            self.log(f"✅ Karaoke ASS file created: {ass_path}")
            return True
        except Exception as e:
            self.log(f"❌ Failed to create ASS file: {e}")
            return False

# ===================================================================
# COMPLETE PYWEBVIEW API WITH VIDEOS AS INTRO SUPPORT
# ===================================================================

class VideoStoveAPI:
    def __init__(self):
        self.window = None
        self.console_queue = queue.Queue()
        
        # File paths
        self.image_files = []
        self.video_files = []  # NEW: Store video files separately
        self.main_audio = ""
        self.bg_music = ""
        self.overlay_video = ""
        self.output_path = ""
        self.batch_source_folder = ""
        self.batch_output_folder = ""
        self.batch_bg_music = ""
        self.batch_overlay = ""
        self.found_projects = []
        
        # Settings
        self.current_settings = CONFIG.copy()
        
        # Get tool directory
        if getattr(sys, 'frozen', False):
            tool_dir = os.path.dirname(sys.executable)
        else:
            tool_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Settings files in tool directory
        self.settings_file = os.path.join(tool_dir, "videostove_settings.json")
        self.presets_file = os.path.join(tool_dir, "custom_presets.json")
        
        # DELETE cached JSON settings on startup
        print("[STARTUP] 🔥 Deleting cached settings JSON for fresh start...")
        try:
            if os.path.exists(self.settings_file):
                os.remove(self.settings_file)
                print("[STARTUP] ✅ Deleted cached settings: videostove_settings.json")
        except Exception as e:
            print(f"[STARTUP] ⚠️ Could not delete cached settings: {e}")
        
        # Reset to defaults
        self.current_settings = DEFAULT_CONFIG.copy()
        CONFIG.clear()
        CONFIG.update(DEFAULT_CONFIG)
        print("[STARTUP] ✅ Using fresh default settings")
        
        # Force correct defaults for overlay mode
        if self.current_settings.get('overlay_mode') != 'simple':
            self.current_settings['overlay_mode'] = 'simple'
            CONFIG['overlay_mode'] = 'simple'
        
        # Processing state
        self.is_processing = False
        self.processing_thread = None
        self.processing_cancelled = False
        self.current_mode = "single"
        
        # Process lock to ensure sequential operations
        self.process_lock = threading.Lock()
        
        # Track active subprocesses for force kill
        self.active_processes = []
        
        # Initialize GPU detection
        self.gpu_options = detect_gpu_acceleration()
    
    def set_window(self, window):
        """Set window reference and initialize UI"""
        self.window = window
        self.process_console_queue()
        # Note: Don't call update_progress here - window isn't started yet
    
    def initialize_ui(self):
        """Initialize UI after webview has started - called from JavaScript"""
        self.update_progress(0, "Ready")
        return "UI initialized"
    
    def add_console_message(self, message):
        """Add message to console queue"""
        self.console_queue.put(message)
    
    def process_console_queue(self):
        """Process console messages"""
        try:
            while True:
                message = self.console_queue.get_nowait()
                if self.window:
                    safe_message = json.dumps(message)
                    self.window.evaluate_js(f'addConsoleMessage({safe_message})')
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Console error: {e}")
        
        if self.window:
            threading.Timer(0.1, self.process_console_queue).start()
    
    def update_progress(self, percent, label="Processing..."):
        """Update progress bar in UI"""
        if self.window:
            safe_label = json.dumps(label)
            self.window.evaluate_js(f'''
                document.getElementById('main-progress').style.width = '{percent}%';
                document.getElementById('progress-label').textContent = {safe_label};
            ''')
    
    def show_toast(self, message, toast_type="info"):
        """Show toast notification"""
        if self.window:
            safe_message = json.dumps(message)
            self.window.evaluate_js(f'showToast({safe_message}, "{toast_type}")')
    
    # === FIXED WINDOWS FILE CACHE HELPERS ===
    def clear_windows_file_cache(self, filepath):
        """Force Windows to clear file cache aggressively"""
        try:
            directory = os.path.dirname(filepath)
            
            # Method 1: Touch the directory to force cache refresh
            os.utime(directory, None)
            
            # Method 2: Windows-specific cache clear
            if os.name == 'nt':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                
                # Clear file attributes
                kernel32.SetFileAttributesW(filepath, 0x80)  # FILE_ATTRIBUTE_NORMAL
                
                # Flush file buffers for the directory
                try:
                    # Open directory handle
                    GENERIC_WRITE = 0x40000000
                    FILE_SHARE_WRITE = 0x00000002
                    OPEN_EXISTING = 3
                    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
                    
                    dir_handle = kernel32.CreateFileW(
                        directory,
                        GENERIC_WRITE,
                        FILE_SHARE_WRITE,
                        None,
                        OPEN_EXISTING,
                        FILE_FLAG_BACKUP_SEMANTICS,
                        None
                    )
                    
                    if dir_handle != -1:
                        kernel32.FlushFileBuffers(dir_handle)
                        kernel32.CloseHandle(dir_handle)
                except:
                    pass
                
                # Method 3: Clear Windows thumbnail cache for this file
                try:
                    import subprocess
                    # Delete thumbnail cache entries
                    subprocess.run(['attrib', '-h', filepath], capture_output=True, shell=True)
                    subprocess.run(['compact', '/u', filepath], capture_output=True, shell=True)
                except:
                    pass
                
        except:
            pass  # Non-critical, continue if it fails
    
    def clean_existing_files(self, base_path):
        """FIXED: Clean up existing video files to prevent caching issues - SAFE VERSION"""
        # Get directory and ensure it exists
        directory = os.path.dirname(base_path)
        filename = os.path.basename(base_path)
        name, ext = os.path.splitext(filename)
        
        # First, try to clear any system locks on the directory
        if os.name == 'nt':
            try:
                # Force Windows to release any handles
                import subprocess
                subprocess.run(['takeown', '/f', directory], capture_output=True, shell=True)
                time.sleep(0.2)
            except:
                pass
        
        # FIXED: Only remove the EXACT file we're about to create, not similar ones
        if os.path.exists(base_path):
            for attempt in range(3):
                try:
                    # First try to unlock the file
                    if os.name == 'nt':
                        subprocess.run(['del', '/f', base_path], capture_output=True, shell=True)
                    else:
                        os.remove(base_path)
                    time.sleep(0.2)
                    self.add_console_message(f"🗑️ Removed existing: {filename}")
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(0.5)
                        continue
                    self.add_console_message(f"⚠️ Could not remove {filename}: {e}")
                    # Last resort: rename with timestamp
                    try:
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup = os.path.join(directory, f"{name}_old_{timestamp}{ext}")
                        os.rename(base_path, backup)
                        self.add_console_message(f"📁 Renamed to: {os.path.basename(backup)}")
                    except:
                        # If even rename fails, generate unique name
                        import random
                        random_suffix = random.randint(1000, 9999)
                        self.output_path = os.path.join(directory, f"{name}_{random_suffix}{ext}")
                        self.add_console_message(f"🔄 Using alternative name: {name}_{random_suffix}{ext}")
        
        # FIXED: Only clean up temp files and direct captions for THIS specific file
        # Don't use wildcard patterns that could match other exported videos!
        specific_cleanup_files = [
            os.path.join(directory, f"{name}_captions.srt"),  # Only the SRT for this file
            os.path.join(directory, f"{name}.mp4.old"),       # Only old version of this file
            os.path.join(directory, f"~${name}{ext}")         # Only temp file for this file
        ]
        
        for file_path in specific_cleanup_files:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    time.sleep(0.05)
                    self.add_console_message(f"🗑️ Cleaned: {os.path.basename(file_path)}")
                except:
                    pass
        
        # Clear Windows caches for the specific file only
        self.clear_windows_file_cache(base_path)
        
        # Force directory refresh (but don't delete other files!)
        if os.name == 'nt':
            try:
                # Refresh Windows Explorer for this directory
                import subprocess
                subprocess.run(['attrib', '-s', '-h', directory], capture_output=True, shell=True)
                # Force directory listing to refresh cache
                subprocess.run(['dir', directory], capture_output=True, shell=True)
            except:
                pass
    
    # === PROCESS CONTROL METHODS ===
    def cancel_processing(self):
        """Cancel ongoing processing"""
        try:
            self.processing_cancelled = True
            self.add_console_message("⏹️ Cancellation requested...")
            
            # If processing thread exists, signal it to stop
            if self.processing_thread and self.processing_thread.is_alive():
                self.add_console_message("🛑 Stopping current operation...")
                # The processing worker will check self.processing_cancelled
            
            # Reset UI state
            if self.window:
                self.window.evaluate_js('''
                    const generateBtn = document.getElementById("generate-btn");
                    const cancelBtn = document.getElementById("cancel-btn");
                    if (generateBtn) {
                        generateBtn.style.display = "block";
                        generateBtn.textContent = "🎬 Generate Video";
                        generateBtn.disabled = false;
                    }
                    if (cancelBtn) {
                        cancelBtn.style.display = "none";
                    }
                ''')
            
            self.is_processing = False
            self.add_console_message("✅ Process cancellation completed")
            return {"success": True}
            
        except Exception as e:
            self.add_console_message(f"❌ Error during cancellation: {e}")
            return {"success": False, "error": str(e)}

    def reset_processing_state(self):
        """Reset processing state and UI"""
        self.is_processing = False
        self.processing_cancelled = False
        
        if self.window:
            self.window.evaluate_js('''
                const generateBtn = document.getElementById("generate-btn");
                const cancelBtn = document.getElementById("cancel-btn");
                const progressLabel = document.getElementById("progress-label");
                const progressFill = document.getElementById("main-progress");
                
                if (generateBtn) {
                    generateBtn.style.display = "block";
                    generateBtn.textContent = "🎬 Generate Video";
                    generateBtn.disabled = false;
                }
                if (cancelBtn) {
                    cancelBtn.style.display = "none";
                }
                if (progressLabel) {
                    progressLabel.textContent = "Ready";
                }
                if (progressFill) {
                    progressFill.style.width = "0%";
                }
            ''')

    # === DEPENDENCY CHECK ===
    def check_dependencies(self):
        """Check if required dependencies are available"""
        ffmpeg_available = False
        whisper_available = False
        
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            ffmpeg_available = True
        except:
            pass
        
        try:
            import whisper
            whisper_available = True
        except ImportError:
            pass
        
        return {
            "ffmpeg": ffmpeg_available,
            "whisper": whisper_available,
            "gpu": len(self.gpu_options) > 0,
            "gpu_encoders": self.gpu_options
        }
    
    # === MODE MANAGEMENT ===
    def set_mode(self, mode):
        """Set current processing mode"""
        self.current_mode = mode
        self.add_console_message(f"🔄 Switched to {mode} mode")
    
    # === NATIVE WINDOWS FILE DIALOG HELPER ===
    def _get_native_file_dialog(self):
        """Create hidden tkinter root for native Windows file dialogs"""
        root = tk.Tk()
        root.withdraw()  # Hide the tkinter window
        root.wm_attributes('-topmost', 1)  # Keep dialog on top
        return root
    
    # === FILE SELECTION METHODS WITH NATIVE WINDOWS EXPLORER ===
    def select_images(self):
        """ENHANCED: Select images and videos for single project."""
        try:
            root = self._get_native_file_dialog()
            
            # Single mode: Select multiple media files directly
            if self.current_mode == "single":
                selected_files = filedialog.askopenfilenames(
                    parent=root,
                    title="Select image and video files",
                    filetypes=[
                        ("Media Files", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif *.mp4 *.mov *.avi *.mkv *.webm"),
                        ("Image Files", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif"),
                        ("Video Files", "*.mp4 *.mov *.avi *.mkv *.webm"),
                        ("All Files", "*.*")
                    ]
                )
                
                root.destroy()
                
                if selected_files:
                    # Separate images and videos
                    image_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp', '.gif')
                    video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.wmv', '.flv')
                    
                    images = []
                    videos = []
                    
                    for file in selected_files:
                        if file.lower().endswith(image_extensions):
                            images.append(file)
                        elif file.lower().endswith(video_extensions):
                            # Skip overlay videos
                            overlay_keywords = ['overlay', 'effect', 'particle', 'fx']
                            if not any(keyword in os.path.basename(file).lower() for keyword in overlay_keywords):
                                videos.append(file)
                    
                    # Sort files naturally
                    try:
                        import natsort
                        self.image_files = natsort.natsorted(images)
                        self.video_files = natsort.natsorted(videos)
                    except ImportError:
                        self.image_files = sorted(images)
                        self.video_files = sorted(videos)
                    
                    # NEW: Enhanced status display for intro mode
                    if self.video_files and self.image_files and CONFIG.get("videos_as_intro_only", True):
                        status_text = f"✅ {len(self.video_files)} intro videos + {len(self.image_files)} slideshow images"
                    else:
                        status_text = f"✅ {len(self.image_files)} images"
                        if len(self.video_files) > 0:
                            status_text += f", {len(self.video_files)} videos"
                        status_text += " selected"
                    
                    self.window.evaluate_js(f'''
                        document.getElementById('images-status').textContent = '{status_text}';
                        document.getElementById('images-status').style.color = '#23a55a';
                    ''')
                    
                    # NEW: Enhanced console message for intro mode
                    if self.video_files and self.image_files and CONFIG.get("videos_as_intro_only", True):
                        self.add_console_message(f"🎬 Selected {len(self.video_files)} intro videos + {len(self.image_files)} slideshow images")
                        self.add_console_message(f"📍 Mode: Videos as intro only - clean video intros followed by image slideshow")
                    else:
                        self.add_console_message(f"📸 Selected {len(self.image_files)} images, {len(self.video_files)} videos")
                    
                    self.update_project_info()
                else:
                    self.add_console_message(f"❌ No media files selected.")
            
            else:
                # Batch mode: Select folder containing media
                folder_path = filedialog.askdirectory(
                    parent=root,
                    title="Select folder containing images and videos",
                    mustexist=True
                )
                
                root.destroy()
                
                if folder_path:
                    image_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp', '.gif')
                    video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.wmv', '.flv')
                    
                    found_images = []
                    found_videos = []
                    
                    for file in os.listdir(folder_path):
                        file_path = os.path.join(folder_path, file)
                        if file.lower().endswith(image_extensions):
                            found_images.append(file_path)
                        elif file.lower().endswith(video_extensions):
                            # Skip overlay videos
                            overlay_keywords = ['overlay', 'effect', 'particle', 'fx']
                            if not any(keyword in file.lower() for keyword in overlay_keywords):
                                found_videos.append(file_path)

                    if found_images or found_videos:
                        try:
                            import natsort
                            self.image_files = natsort.natsorted(found_images)
                            self.video_files = natsort.natsorted(found_videos)
                        except ImportError:
                            self.image_files = sorted(found_images)
                            self.video_files = sorted(found_videos)
                        
                        folder_name = os.path.basename(folder_path)
                        # NEW: Enhanced batch status for intro mode
                        if self.video_files and self.image_files and CONFIG.get("videos_as_intro_only", True):
                            status_text = f"✅ {len(self.video_files)} intro videos + {len(self.image_files)} images from \"{folder_name}\""
                        else:
                            status_text = f"✅ {len(self.image_files)} images"
                            if len(self.video_files) > 0:
                                status_text += f", {len(self.video_files)} videos"
                            status_text += f' from "{folder_name}"'
                        
                        self.window.evaluate_js(f'''
                            document.getElementById('images-status').textContent = '{status_text}';
                            document.getElementById('images-status').style.color = '#23a55a';
                        ''')
                        
                        # NEW: Enhanced batch console message
                        if self.video_files and self.image_files and CONFIG.get("videos_as_intro_only", True):
                            self.add_console_message(f"🎬 Selected {len(self.video_files)} intro videos + {len(self.image_files)} slideshow images from: {folder_name}")
                        else:
                            self.add_console_message(f"📸 Selected {len(self.image_files)} images, {len(self.video_files)} videos from folder: {folder_name}")
                        
                        self.update_project_info()
                    else:
                        self.add_console_message(f"❌ No image or video files found in the selected folder.")
                
        except Exception as e:
            self.add_console_message(f"❌ Error selecting media: {e}")
    
    def select_videos(self):
        """Select videos for montage mode intro."""
        print(f"[DEBUG] Python API: select_videos() called")
        try:
            root = self._get_native_file_dialog()
            
            selected_files = filedialog.askopenfilenames(
                parent=root,
                title="Select intro videos",
                filetypes=[
                    ("Video Files", "*.mp4 *.mov *.avi *.mkv *.webm *.wmv *.flv"),
                    ("All Files", "*.*")
                ]
            )
            
            root.destroy()
            
            if selected_files:
                # Filter out overlay videos
                videos = []
                for file in selected_files:
                    overlay_keywords = ['overlay', 'effect', 'particle', 'fx']
                    if not any(keyword in os.path.basename(file).lower() for keyword in overlay_keywords):
                        videos.append(file)
                
                if videos:
                    try:
                        import natsort
                        self.video_files = natsort.natsorted(videos)
                    except ImportError:
                        self.video_files = sorted(videos)
                    
                    # Update UI status
                    videos_count = len(self.video_files)
                    video_text = f"{videos_count} video" + ("s" if videos_count != 1 else "")
                    status_text = f"✅ {video_text} selected"
                    
                    self.window.evaluate_js(f'''
                        document.getElementById('videos-status').textContent = '{status_text}';
                        document.getElementById('videos-status').style.color = '#23a55a';
                    ''')
                    self.add_console_message(f"🎬 Selected {videos_count} intro videos for montage")
                else:
                    self.add_console_message("❌ No valid video files selected (overlay files excluded)")
            
        except Exception as e:
            self.add_console_message(f"❌ Error selecting videos: {e}")
    
    def select_montage_images(self):
        """Select images for montage mode slideshow fill."""
        print(f"[DEBUG] Python API: select_montage_images() called")
        try:
            root = self._get_native_file_dialog()
            
            selected_files = filedialog.askopenfilenames(
                parent=root,
                title="Select slideshow images",
                filetypes=[
                    ("Image Files", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif"),
                    ("All Files", "*.*")
                ]
            )
            
            root.destroy()
            
            if selected_files:
                try:
                    import natsort
                    self.image_files = natsort.natsorted(selected_files)
                except ImportError:
                    self.image_files = sorted(selected_files)
                
                # Update UI status
                images_count = len(self.image_files)
                image_text = f"{images_count} image" + ("s" if images_count != 1 else "")
                status_text = f"✅ {image_text} selected"
                
                self.window.evaluate_js(f'''
                    document.getElementById('montage-images-status').textContent = '{status_text}';
                    document.getElementById('montage-images-status').style.color = '#23a55a';
                ''')
                self.add_console_message(f"🖼️ Selected {images_count} images for slideshow fill")
            
        except Exception as e:
            self.add_console_message(f"❌ Error selecting images: {e}")
    
    def select_images_only(self):
        """Select only images for slideshow mode."""
        try:
            root = self._get_native_file_dialog()
            
            selected_files = filedialog.askopenfilenames(
                parent=root,
                title="Select images only",
                filetypes=[
                    ("Image Files", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif"),
                    ("All Files", "*.*")
                ]
            )
            
            root.destroy()
            
            if selected_files:
                # Only store images
                try:
                    import natsort
                    self.image_files = natsort.natsorted(selected_files)
                except ImportError:
                    self.image_files = sorted(selected_files)
                
                # Clear videos for slideshow mode
                self.video_files = []
                
                status_text = f"✅ {len(self.image_files)} images selected"
                
                self.window.evaluate_js(f'''
                    document.getElementById('images-status').textContent = '{status_text}';
                    document.getElementById('images-status').style.color = '#23a55a';
                ''')
                
                self.add_console_message(f"📸 Selected {len(self.image_files)} images for slideshow")
                self.update_project_info()
            else:
                self.add_console_message(f"❌ No images selected.")
                
        except Exception as e:
            self.add_console_message(f"❌ Error selecting images: {e}")
    
    def clear_videos(self):
        """Clear video selection when switching to slideshow mode."""
        try:
            self.video_files = []
            self.window.evaluate_js('''
                document.getElementById('videos-status').textContent = 'No videos selected';
                document.getElementById('videos-status').style.color = 'rgba(255, 255, 255, 0.4)';
            ''')
            self.add_console_message("🗑️ Video selection cleared")
            self.update_project_info()
        except Exception as e:
            self.add_console_message(f"❌ Error clearing videos: {e}")

    def clear_images(self):
        """Clear image selection when switching to videos-only mode."""
        try:
            self.image_files = []
            self.window.evaluate_js('''
                document.getElementById('images-status').textContent = 'Images disabled in Videos Only mode';
                document.getElementById('images-status').style.color = 'rgba(255, 255, 255, 0.4)';
            ''')
            self.add_console_message("🗑️ Image selection cleared")
            self.update_project_info()
        except Exception as e:
            self.add_console_message(f"❌ Error clearing images: {e}")
    
    def select_audio(self):
        """Select audio for single project."""
        try:
            root = self._get_native_file_dialog()
            
            # Single mode: Select a single audio file directly
            if self.current_mode == "single":
                selected_file = filedialog.askopenfilename(
                    parent=root,
                    title="Select main audio file",
                    filetypes=[
                        ("Audio Files", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma"),
                        ("MP3 Files", "*.mp3"),
                        ("WAV Files", "*.wav"),
                        ("All Files", "*.*")
                    ]
                )
                
                root.destroy()
                
                if selected_file:
                    self.main_audio = selected_file
                    filename = os.path.basename(self.main_audio)
                    display_name = filename[:30] + "..." if len(filename) > 30 else filename
                    
                    self.window.evaluate_js(f'''
                        document.getElementById('audio-status').textContent = '✅ {display_name}';
                        document.getElementById('audio-status').style.color = '#23a55a';
                    ''')
                    self.add_console_message(f"🎵 Main audio selected: {filename}")
                    self.update_project_info()
                else:
                    self.add_console_message(f"❌ No audio file selected.")
            
            else:
                # Batch mode: Select folder containing audio
                folder_path = filedialog.askdirectory(
                    parent=root,
                    title="Select folder containing audio file",
                    mustexist=True
                )
                
                root.destroy()
                
                if folder_path:
                    audio_extensions = ('.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.wma')
                    
                    found_audio = None
                    for file in os.listdir(folder_path):
                        if file.lower().endswith(audio_extensions):
                            found_audio = os.path.join(folder_path, file)
                            break

                    if found_audio:
                        self.main_audio = found_audio
                        filename = os.path.basename(self.main_audio)
                        display_name = filename[:30] + "..." if len(filename) > 30 else filename
                        
                        self.window.evaluate_js(f'''
                            document.getElementById('audio-status').textContent = '✅ {display_name}';
                            document.getElementById('audio-status').style.color = '#23a55a';
                        ''')
                        self.add_console_message(f"🎵 Main audio found: {filename}")
                        self.update_project_info()
                    else:
                        self.add_console_message(f"❌ No supported audio files found in the selected folder.")
                
        except Exception as e:
            self.add_console_message(f"❌ Error selecting audio: {e}")

    def select_output(self):
        """Select output file location using native Windows explorer"""
        try:
            root = self._get_native_file_dialog()
            
            # Native Windows save dialog
            output_path = filedialog.asksaveasfilename(
                parent=root,
                title="Save video as...",
                defaultextension=".mp4",
                filetypes=[
                    ("MP4 Videos", "*.mp4"),
                    ("All Files", "*.*")
                ]
            )
            
            root.destroy()
            
            if output_path:
                if not output_path.lower().endswith('.mp4'):
                    output_path += '.mp4'
                    
                self.output_path = output_path
                filename = os.path.basename(self.output_path)
                
                self.window.evaluate_js(f'''
                    document.getElementById('output-status').textContent = '✅ {filename}';
                    document.getElementById('output-status').style.color = '#23a55a';
                ''')
                self.add_console_message(f"💾 Output: {filename}")
                self.update_project_info()
                
        except Exception as e:
            self.add_console_message(f"❌ Error setting output: {e}")
    
    def select_bg_music(self):
        """Select background music file using native Windows explorer"""
        try:
            root = self._get_native_file_dialog()
            
            # Native Windows file dialog
            selected_file = filedialog.askopenfilename(
                parent=root,
                title="Select background music file",
                filetypes=[
                    ("Audio Files", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma"),
                    ("MP3 Files", "*.mp3"),
                    ("WAV Files", "*.wav"),
                    ("All Files", "*.*")
                ]
            )
            
            root.destroy()
            
            if selected_file:
                self.bg_music = selected_file
                filename = os.path.basename(self.bg_music)
                display_name = filename[:30] + "..." if len(filename) > 30 else filename
                
                self.window.evaluate_js(f'''
                    document.getElementById('bg-status').textContent = '✅ {display_name}';
                    document.getElementById('bg-status').style.color = '#23a55a';
                ''')
                self.add_console_message(f"🎶 Background music: {filename}")
                
        except Exception as e:
            self.add_console_message(f"❌ Error selecting background music: {e}")
    
    def select_overlay(self):
        """Select overlay video file using native Windows explorer"""
        try:
            root = self._get_native_file_dialog()
            
            # Native Windows file dialog
            selected_file = filedialog.askopenfilename(
                parent=root,
                title="Select overlay video file",
                filetypes=[
                    ("Video Files", "*.mp4 *.mov *.avi *.mkv *.webm *.wmv *.flv"),
                    ("MP4 Files", "*.mp4"),
                    ("All Files", "*.*")
                ]
            )
            
            root.destroy()
            
            if selected_file:
                self.overlay_video = selected_file
                filename = os.path.basename(self.overlay_video)
                display_name = filename[:30] + "..." if len(filename) > 30 else filename
                
                self.window.evaluate_js(f'''
                    document.getElementById('overlay-status').textContent = '✅ {display_name}';
                    document.getElementById('overlay-status').style.color = '#23a55a';
                ''')
                self.add_console_message(f"🎭 Video overlay: {filename}")
                
        except Exception as e:
            self.add_console_message(f"❌ Error selecting overlay: {e}")
    
    def select_batch_source(self):
        """Select batch source folder using native Windows explorer"""
        try:
            root = self._get_native_file_dialog()
            
            # Native Windows folder dialog
            folder_path = filedialog.askdirectory(
                parent=root,
                title="Select source folder for batch processing",
                mustexist=True
            )
            
            root.destroy()
            
            if folder_path:
                self.batch_source_folder = folder_path
                folder_name = os.path.basename(self.batch_source_folder)
                
                self.window.evaluate_js(f'''
                    document.getElementById('batch-source-status').textContent = '✅ {folder_name}';
                    document.getElementById('batch-source-status').style.color = '#23a55a';
                ''')
                self.add_console_message(f"📂 Source folder: {folder_name}")
                self.scan_batch_projects()
                
        except Exception as e:
            self.add_console_message(f"❌ Error selecting source folder: {e}")
    
    def select_batch_output(self):
        """Select batch output folder using native Windows explorer"""
        try:
            root = self._get_native_file_dialog()
            
            # Native Windows folder dialog
            folder_path = filedialog.askdirectory(
                parent=root,
                title="Select output folder for batch processing",
                mustexist=True
            )
            
            root.destroy()
            
            if folder_path:
                self.batch_output_folder = folder_path
                folder_name = os.path.basename(self.batch_output_folder)
                
                self.window.evaluate_js(f'''
                    document.getElementById('batch-output-status').textContent = '✅ {folder_name}';
                    document.getElementById('batch-output-status').style.color = '#23a55a';
                ''')
                self.add_console_message(f"📁 Output folder: {folder_name}")
                
        except Exception as e:
            self.add_console_message(f"❌ Error selecting output folder: {e}")
    
    def select_batch_bg_music(self):
        """Select global background music for batch using native Windows explorer"""
        try:
            root = self._get_native_file_dialog()
            
            # Native Windows file dialog
            selected_file = filedialog.askopenfilename(
                parent=root,
                title="Select global background music for batch",
                filetypes=[
                    ("Audio Files", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"),
                    ("MP3 Files", "*.mp3"),
                    ("WAV Files", "*.wav"),
                    ("All Files", "*.*")
                ]
            )
            
            root.destroy()

            if selected_file:
                self.batch_bg_music = selected_file
                filename = os.path.basename(self.batch_bg_music)
                display_name = filename[:25] + "..." if len(filename) > 25 else filename
                
                self.window.evaluate_js(f'''
                    document.getElementById('batch-bg-status').textContent = '✅ {display_name}';
                    document.getElementById('batch-bg-status').style.color = '#23a55a';
                ''')
                self.add_console_message(f"🎶 Global background music: {filename}")

        except Exception as e:
            self.add_console_message(f"❌ Error selecting global background music: {e}")
    
    def select_batch_overlay(self):
        """Select global overlay video for batch using native Windows explorer"""
        try:
            root = self._get_native_file_dialog()
            
            # Native Windows file dialog
            selected_file = filedialog.askopenfilename(
                parent=root,
                title="Select global overlay video for batch",
                filetypes=[
                    ("Video Files", "*.mp4 *.mov *.avi *.mkv *.webm"),
                    ("MP4 Files", "*.mp4"),
                    ("All Files", "*.*")
                ]
            )
            
            root.destroy()

            if selected_file:
                self.batch_overlay = selected_file
                filename = os.path.basename(self.batch_overlay)
                display_name = filename[:25] + "..." if len(filename) > 25 else filename
                
                self.window.evaluate_js(f'''
                    document.getElementById('batch-overlay-status').textContent = '✅ {display_name}';
                    document.getElementById('batch-overlay-status').style.color = '#23a55a';
                ''')
                self.add_console_message(f"🎭 Global overlay video: {filename}")

        except Exception as e:
            self.add_console_message(f"❌ Error selecting global overlay: {e}")
    
    def scan_batch_projects(self):
        """Scan source folder for valid projects and display their names and file counts."""
        if not self.batch_source_folder:
            return
        
        self.found_projects = []
        projects_data = []
        
        try:
            for item in os.listdir(self.batch_source_folder):
                item_path = os.path.join(self.batch_source_folder, item)
                if os.path.isdir(item_path):
                    try:
                        files = os.listdir(item_path)
                        
                        image_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp')
                        audio_extensions = ('.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg')
                        video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm')

                        has_images = any(f.lower().endswith(image_extensions) for f in files)
                        has_audio = any(f.lower().endswith(audio_extensions) for f in files)
                        video_files = [f for f in files if f.lower().endswith(video_extensions)]
                        filtered_videos = [f for f in video_files if not any(keyword in f.lower() for keyword in ['overlay', 'effect', 'particle', 'fx'])]
                        excluded_videos = [f for f in video_files if any(keyword in f.lower() for keyword in ['overlay', 'effect', 'particle', 'fx'])]
                        has_videos = len(filtered_videos) > 0
                        
                        # Debug logging
                        self.add_console_message(f"📁 Scanning: {item}")
                        self.add_console_message(f"   Files: {len(files)} total")
                        self.add_console_message(f"   Images: {has_images} ({sum(1 for f in files if f.lower().endswith(image_extensions))} files)")
                        self.add_console_message(f"   Audio: {has_audio} ({sum(1 for f in files if f.lower().endswith(audio_extensions))} files)")
                        self.add_console_message(f"   Videos: {has_videos} ({len(filtered_videos)} valid, {len(excluded_videos)} excluded)")
                        if excluded_videos:
                            self.add_console_message(f"   Excluded videos: {excluded_videos}")
                        
                        # Project is valid if it has audio and at least one of: images or videos
                        if has_audio and (has_images or has_videos):
                            image_count = sum(1 for f in files if f.lower().endswith(image_extensions))
                            audio_count = sum(1 for f in files if f.lower().endswith(audio_extensions))
                            video_count = len(filtered_videos)

                            self.found_projects.append(item_path)
                            
                            projects_data.append({
                                'name': item,
                                'image_count': image_count,
                                'video_count': video_count,
                                'audio_count': audio_count
                            })
                            
                    except Exception:
                        continue
                    
            project_count = len(self.found_projects)
            if project_count > 0:
                self.window.evaluate_js(f'''
                    document.getElementById('projects-status').textContent = '✅ Found {project_count} valid projects';
                    document.getElementById('projects-status').style.color = '#23a55a';
                ''')
                js_array = json.dumps(projects_data)
                self.window.evaluate_js(f'displayProjectList({js_array})')
                self.add_console_message(f"✅ Found {project_count} valid projects.")
            else:
                self.window.evaluate_js(f'''
                    document.getElementById('projects-status').textContent = '❌ No valid projects found';
                    document.getElementById('projects-status').style.color = '#f23f43';
                    displayProjectList([]);
                ''')
                self.add_console_message("❌ No valid projects found")
                
        except Exception as e:
            self.add_console_message(f"❌ Error scanning projects: {e}")
    
    def update_project_info(self):
        """NEW: Enhanced project information display with videos as intro support"""
        total_media = len(self.image_files) + len(getattr(self, 'video_files', []))
        
        if total_media > 0 and self.main_audio and self.output_path:
            # Calculate estimated duration
            video_count = len(getattr(self, 'video_files', []))
            image_count = len(self.image_files)
            image_duration = image_count * self.current_settings.get("image_duration", 8.0)
            
            # NEW: Enhanced info message based on project type
            project_type = CONFIG.get("project_type", "montage")
            
            if project_type == "videos_only":
                info_msg = f"🎬 Videos Only project ready - {video_count} videos for compilation"
            elif project_type == "slideshow":
                info_msg = f"🖼️ Slideshow project ready - {image_count} images, ~{image_duration:.1f}s video"
            elif video_count > 0 and image_count > 0 and CONFIG.get("videos_as_intro_only", True):
                info_msg = f"📊 Video Montage project ready - {video_count} intro videos + {image_count} slideshow images"
            elif video_count > 0:
                info_msg = f"📊 Project ready - {video_count} videos"
                if image_count > 0:
                    info_msg += f" + {image_count} images"
            else:
                info_msg = f"📊 Project ready - {image_count} images, ~{image_duration:.1f}s video"
            
            self.add_console_message(info_msg)
    
    # === SETTINGS MANAGEMENT ===
    def update_setting(self, name, value):
        """Update setting with validation and error handling"""
        print(f"[DEBUG] Python API: update_setting({name}, {value})")
        print(f"[DEBUG] Value type: {type(value)}")
        
        if name not in DEFAULT_CONFIG:
            print(f"[WARNING] Unknown setting: {name}")
            return
        
        self.current_settings[name] = value
        CONFIG[name] = value
        self.save_settings()
        
        print(f"[DEBUG] CONFIG[{name}] after update: {CONFIG[name]}")
        
        # Special logging for important settings
        if name == "captions_enabled":
            self.add_console_message(f"📝 Captions: {'enabled' if value else 'disabled'}")
        elif name == "project_type":
            self.add_console_message(f"🎬 Project type: {value}")
        elif name == "extended_zoom_enabled":
            status = "enabled" if value else "disabled"
            self.add_console_message(f"🔍 Extended zoom: {status}")
    
    def get_settings(self):
        """Get current settings"""
        return self.current_settings.copy()
    
    def save_settings(self):
        """Save settings to tool directory"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.current_settings, f, indent=2)
            print("💾 Settings saved: videostove_settings.json")
        except Exception as e:
            print(f"❌ Failed to save settings: {e}")

    def load_settings(self):
        """Load settings from tool directory"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                
                # Validate and load settings
                for key, value in saved.items():
                    if key in DEFAULT_CONFIG:
                        self.current_settings[key] = value
                        CONFIG[key] = value
                    else:
                        print(f"[WARNING] Ignoring unknown setting: {key}")
                
                print(f"📁 Loaded {len(saved)} cached settings")
                self.add_console_message(f"📁 Loaded {len(saved)} saved settings")
            else:
                print("📁 No cached settings found, using defaults")
                self.add_console_message("📁 Using default settings")
        except Exception as e:
            print(f"❌ Failed to load settings: {e}")
            self.add_console_message(f"⚠️ Failed to load cached settings: {e}")
            # Fall back to defaults
            self.current_settings = DEFAULT_CONFIG.copy()
            CONFIG.update(DEFAULT_CONFIG)

    # === CUSTOM PRESET SYSTEM ===
    def _get_all_presets(self):
        """Helper to load all custom presets from file with error handling"""
        try:
            if not os.path.exists(self.presets_file):
                print("[DEBUG] No presets file found, returning empty dict")
                return {}
            
            with open(self.presets_file, 'r', encoding='utf-8') as f:
                presets = json.load(f)
                
            if not isinstance(presets, dict):
                print("[WARNING] Invalid presets file format, returning empty dict")
                return {}
                
            print(f"[DEBUG] Loaded {len(presets)} presets from file")
            return presets
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON in presets file: {e}")
            return {}
        except Exception as e:
            print(f"[ERROR] Failed to load presets file: {e}")
            return {}

    def get_custom_presets(self):
        """Return a list of saved custom preset names with error handling"""
        try:
            presets = self._get_all_presets()
            preset_list = list(presets.keys())
            print(f"[DEBUG] Retrieved {len(preset_list)} custom presets")
            return preset_list
        except Exception as e:
            print(f"[ERROR] Failed to get custom presets: {e}")
            return []

    def save_custom_preset(self, name):
        """Save the current settings as a named preset with validation"""
        try:
            if not name or not isinstance(name, str) or not name.strip():
                return {"success": False, "error": "Invalid preset name"}
            
            name = name.strip()
            if len(name) > 50:
                return {"success": False, "error": "Preset name too long (max 50 characters)"}
            
            # Get all existing presets
            presets = self._get_all_presets()
            
            # Save current settings (make a deep copy to avoid reference issues)
            preset_data = {}
            for key, value in self.current_settings.items():
                preset_data[key] = value
            
            presets[name] = preset_data
            
            # Atomic save to file to prevent corruption
            os.makedirs(os.path.dirname(self.presets_file), exist_ok=True)
            temp_file = self.presets_file + '.tmp'
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(presets, f, indent=2)
                f.flush()  # Force write to disk
                os.fsync(f.fileno())  # Force sync to disk
            
            # Atomic rename - this is atomic on most filesystems
            if os.name == 'nt':  # Windows
                if os.path.exists(self.presets_file):
                    os.remove(self.presets_file)
            os.rename(temp_file, self.presets_file)
                
            self.add_console_message(f"💾 Preset '{name}' saved successfully.")
            print(f"[DEBUG] Saved preset '{name}' with {len(preset_data)} settings")
            return {"success": True, "presets": list(presets.keys())}
            
        except Exception as e:
            error_msg = f"Failed to save preset '{name}': {e}"
            self.add_console_message(f"❌ {error_msg}")
            print(f"[ERROR] {error_msg}")
            return {"success": False, "error": str(e)}

    def load_custom_preset(self, name):
        """Load a named preset and apply its settings with validation"""
        try:
            if not name or not isinstance(name, str):
                return {"success": False, "error": "Invalid preset name"}
            
            presets = self._get_all_presets()
            if name not in presets:
                return {"success": False, "error": f"Preset '{name}' not found"}
            
            preset_data = presets[name]
            if not isinstance(preset_data, dict):
                return {"success": False, "error": f"Invalid preset data for '{name}'"}
            
            # Validate and apply settings
            valid_settings = {}
            for key, value in preset_data.items():
                if key in DEFAULT_CONFIG:
                    valid_settings[key] = value
                else:
                    print(f"[WARNING] Ignoring unknown setting in preset '{name}': {key}")
            
            # Update current settings
            self.current_settings.update(valid_settings)
            CONFIG.update(valid_settings)
            
            # Save the updated settings
            self.save_settings()
            
            self.add_console_message(f"📋 Loaded preset: '{name}' ({len(valid_settings)} settings)")
            print(f"[DEBUG] Loaded preset '{name}' with {len(valid_settings)} settings")
            return {"success": True, "settings": valid_settings}
            
        except Exception as e:
            error_msg = f"Failed to load preset '{name}': {e}"
            self.add_console_message(f"❌ {error_msg}")
            print(f"[ERROR] {error_msg}")
            return {"success": False, "error": str(e)}

    def delete_custom_preset(self, name):
        """Delete a named preset with validation"""
        try:
            if not name or not isinstance(name, str):
                return {"success": False, "error": "Invalid preset name"}
            
            presets = self._get_all_presets()
            if name not in presets:
                return {"success": False, "error": f"Preset '{name}' not found"}
            
            # Remove the preset
            del presets[name]
            
            # Save updated presets
            with open(self.presets_file, 'w', encoding='utf-8') as f:
                json.dump(presets, f, indent=2)
                
            self.add_console_message(f"🗑️ Deleted preset: '{name}'")
            print(f"[DEBUG] Deleted preset '{name}'")
            return {"success": True, "presets": list(presets.keys())}
            
        except Exception as e:
            error_msg = f"Failed to delete preset '{name}': {e}"
            self.add_console_message(f"❌ {error_msg}")
            print(f"[ERROR] {error_msg}")
            return {"success": False, "error": str(e)}

    def export_all_presets(self):
        """Export each saved custom preset to separate JSON files"""
        try:
            # Get all presets
            all_presets = self._get_all_presets()
            
            if not all_presets:
                return {"success": False, "error": "No presets to export"}
            
            # Save to exports directory (create if doesn't exist)
            tool_dir = os.path.dirname(self.settings_file)
            exports_dir = os.path.join(tool_dir, "exports")
            os.makedirs(exports_dir, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            exported_files = []
            
            # Export each preset to its own file
            for preset_name, preset_data in all_presets.items():
                # Create export data structure for single preset
                export_data = {
                    "metadata": {
                        "export_type": "videostove_preset",
                        "export_date": datetime.datetime.now().isoformat(),
                        "videostove_version": "1.0",
                        "preset_name": preset_name
                    },
                    "preset": {
                        preset_name: preset_data
                    }
                }
                
                # Generate safe filename for this preset
                safe_name = "".join(c for c in preset_name if c.isalnum() or c in ('_', '-')).strip()
                filename = f"preset_{safe_name}_{timestamp}.json"
                export_path = os.path.join(exports_dir, filename)
                
                # Write export file
                with open(export_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                
                exported_files.append({
                    "preset_name": preset_name,
                    "filename": filename,
                    "file_path": export_path
                })
                
                self.add_console_message(f"✅ Exported preset '{preset_name}' → {filename}")
            
            self.add_console_message(f"🎉 Successfully exported {len(all_presets)} presets to separate files")
            self.add_console_message(f"📁 Location: {exports_dir}")
            
            return {
                "success": True, 
                "exported_files": exported_files,
                "export_count": len(all_presets),
                "exports_dir": exports_dir
            }
            
        except Exception as e:
            error_msg = f"Failed to export presets: {e}"
            self.add_console_message(f"❌ ERROR: {error_msg}")
            return {"success": False, "error": error_msg}

    def import_presets_from_file(self):
        """Import presets from a selected JSON file"""
        try:
            if not HAS_TKINTER:
                return {"success": False, "error": "File dialog not available"}
            
            root = self._get_native_file_dialog()
            
            selected_file = filedialog.askopenfilename(
                parent=root,
                title="Select VideoStove Presets File",
                filetypes=[
                    ("JSON Preset Files", "*.json"),
                    ("All Files", "*.*")
                ]
            )
            
            root.destroy()
            
            if not selected_file:
                return {"success": False, "error": "No file selected"}
            
            return self.import_presets_from_path(selected_file)
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def import_presets_from_path(self, file_path):
        """Import presets from a specific file path"""
        try:
            # Read and validate import file
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Validate structure
            if not isinstance(import_data, dict):
                return {"success": False, "error": "Invalid file format"}
            
            if "presets" not in import_data:
                return {"success": False, "error": "No presets found in file"}
            
            presets_to_import = import_data["presets"]
            if not isinstance(presets_to_import, dict):
                return {"success": False, "error": "Invalid presets format"}
            
            # Get existing presets
            existing_presets = self._get_all_presets()
            
            # Merge presets (imported presets will overwrite existing ones with same name)
            imported_count = 0
            overwritten_count = 0
            
            for preset_name, preset_data in presets_to_import.items():
                if preset_name in existing_presets:
                    overwritten_count += 1
                else:
                    imported_count += 1
                
                existing_presets[preset_name] = preset_data
            
            # Save merged presets
            with open(self.presets_file, 'w', encoding='utf-8') as f:
                json.dump(existing_presets, f, indent=2)
            
            # Log results
            total_imported = imported_count + overwritten_count
            self.add_console_message(f"Presets imported successfully from: {os.path.basename(file_path)}")
            self.add_console_message(f"New presets: {imported_count}, Updated presets: {overwritten_count}")
            self.add_console_message(f"Total presets imported: {total_imported}")
            
            return {
                "success": True,
                "imported_count": imported_count,
                "overwritten_count": overwritten_count,
                "total_count": total_imported
            }
            
        except Exception as e:
            error_msg = f"Failed to import presets: {e}"
            self.add_console_message(f"ERROR: {error_msg}")
            return {"success": False, "error": error_msg}

    # === FIXED GPU-ACCELERATED VIDEO GENERATION ===
    def generate_video(self):
        """Start video generation process - FIXED VERSION"""
        print(f"[DEBUG] Python API: generate_video() called")
        print(f"[DEBUG] Current mode: {self.current_mode}")
        print(f"[DEBUG] Is processing: {self.is_processing}")
        print(f"[DEBUG] Image files: {len(self.image_files)} files")
        print(f"[DEBUG] Video files: {len(self.video_files)} files")
        print(f"[DEBUG] Main audio: {self.main_audio}")
        print(f"[DEBUG] Output path: {self.output_path}")
        
        if self.is_processing:
            print(f"[DEBUG] ERROR: Processing already in progress")
            return {"error": "Processing already in progress"}

        print(f"[DEBUG] Validating inputs for {self.current_mode} mode...")
        # Validate inputs
        if self.current_mode == "single":
            validation_result = self.validate_single_inputs()
            print(f"[DEBUG] Single mode validation result: {validation_result}")
            if not validation_result:
                print(f"[DEBUG] ERROR: Invalid inputs for single project")
                return {"error": "Invalid inputs for single project"}
        else:
            validation_result = self.validate_batch_inputs()
            print(f"[DEBUG] Batch mode validation result: {validation_result}")
            if not validation_result:
                print(f"[DEBUG] ERROR: Invalid inputs for batch processing")
                return {"error": "Invalid inputs for batch processing"}

        # --- FIX: Take a snapshot of settings at the moment of generation ---
        settings_snapshot = self.current_settings.copy()
        
        # Reset cancellation flag and start processing
        self.processing_cancelled = False
        self.is_processing = True
        
        # Update UI to show cancel button
        if self.window:
            self.window.evaluate_js('''
                const generateBtn = document.getElementById("generate-btn");
                const cancelBtn = document.getElementById("cancel-btn");
                if (generateBtn) generateBtn.style.display = "none";
                if (cancelBtn) cancelBtn.style.display = "block";
            ''')
        
        # --- FIX: Pass the settings snapshot to the worker thread ---
        if self.current_mode == "single":
            self.processing_thread = threading.Thread(target=self.single_generation_worker, args=(settings_snapshot,), daemon=True)
        else:
            self.processing_thread = threading.Thread(target=self.batch_generation_worker, args=(settings_snapshot,), daemon=True)
        
        self.processing_thread.start()
        return {"success": True}
    
    def validate_single_inputs(self):
        """ENHANCED: Validate single project inputs with mixed media support"""
        print(f"[DEBUG] Validating single inputs...")
        
        total_media = len(self.image_files) + len(getattr(self, 'video_files', []))
        print(f"[DEBUG] Total media files: {total_media} (images: {len(self.image_files)}, videos: {len(getattr(self, 'video_files', []))})")
        
        if total_media == 0:
            print(f"[DEBUG] VALIDATION FAILED: No media files")
            self.add_console_message("❌ No media files selected (need images or videos)")
            return False
        
        print(f"[DEBUG] Main audio: '{self.main_audio}'")
        if not self.main_audio:
            print(f"[DEBUG] VALIDATION FAILED: No main audio")
            self.add_console_message("❌ No main audio selected")
            return False
        
        print(f"[DEBUG] Output path: '{self.output_path}'")
        if not self.output_path:
            print(f"[DEBUG] VALIDATION FAILED: No output path")
            self.add_console_message("❌ No output location set")
            return False
        
        print(f"[DEBUG] VALIDATION PASSED: All inputs valid")
        return True
    
    def validate_batch_inputs(self):
        """Validate batch processing inputs"""
        if not self.found_projects:
            self.add_console_message("❌ No valid projects found")
            return False
        
        if not self.batch_output_folder:
            self.add_console_message("❌ No output folder selected")
            return False
        
        return True
    
    def single_generation_worker(self, current_settings):
        """NEW: Background single project generation with videos as intro support"""
        try:
            self.update_progress(0, "Processing...")
            
            # --- FIX: Use the settings snapshot passed to this worker ---
            CONFIG.update(current_settings)
            
            # DEBUG: Log overlay mode from settings snapshot  
            self.add_console_message(f"🔧 Single processing started with overlay_mode: {current_settings.get('overlay_mode', 'NOT_SET')}")
            
            # UI-Backend synchronization should now be handled properly by improved slider logic
            
            self.add_console_message(f"🔧 CONFIG overlay_mode after update: {CONFIG.get('overlay_mode', 'NOT_SET')}")

            # NEW: Enhanced intro mode logging
            if self.video_files and self.image_files and CONFIG.get("videos_as_intro_only", True):
                self.add_console_message("🎬 Starting Videos as Intro generation")
                self.add_console_message(f"📍 Structure: {len(self.video_files)} intro videos → {len(self.image_files)} slideshow images")
            else:
                self.add_console_message("🎬 Starting mixed media generation")
            
            if self.processing_cancelled:
                self.add_console_message("❌ Process cancelled before starting")
                return
            
            self.clean_existing_files(self.output_path)
            
            creator = VideoCreator(update_callback=self.add_console_message)
            
            bg_music = self.bg_music if current_settings.get("use_bg_music", True) and self.bg_music else None
            overlay_video = self.overlay_video if current_settings.get("use_overlay", False) and self.overlay_video else None
            
            self.update_progress(10, "Creating slideshow...")
            
            if self.processing_cancelled:
                self.add_console_message("❌ Process cancelled during setup")
                return
            
            success = creator.create_slideshow(
                image_files=self.image_files,
                video_files=getattr(self, 'video_files', []),
                main_audio=self.main_audio,
                bg_music=bg_music,
                overlay_video=overlay_video,
                output_file=self.output_path
            )
            
            if self.processing_cancelled:
                self.add_console_message("❌ Process cancelled during video creation")
                return
            
            if not success:
                self.add_console_message("❌ Failed to create video")
                self.show_toast("Failed to create video", "error")
                return
            
            self.update_progress(80, "Video created successfully")
            
            # --- FIX: Check for captions using current CONFIG (not snapshot) AND whisper availability ---
            dependencies = self.check_dependencies()
            if CONFIG.get("captions_enabled", False) and dependencies.get("whisper", False):
                if self.processing_cancelled:
                    self.add_console_message("❌ Process cancelled before captioning")
                    return
                
                self.update_progress(85, "Adding captions...")
                self.add_console_message("📝 Starting auto-captioning...")
                
                model_size = CONFIG.get("whisper_model", "base")
                
                captioner = AutoCaptioner(model_size=model_size, update_callback=self.add_console_message)
                captioner.add_captions_to_video(self.output_path)
            elif CONFIG.get("captions_enabled", False):
                self.add_console_message("⚠️ Captions enabled but Whisper not available - skipping caption generation")
            
            if self.processing_cancelled:
                self.add_console_message("❌ Process cancelled during finalization")
                return
            
            self.update_progress(100, "Complete!")
            
            if self.video_files and self.image_files and CONFIG.get("videos_as_intro_only", True):
                self.add_console_message("🎉 Videos as Intro project completed successfully!")
                result_msg = f"Videos as Intro generated! {len(self.video_files)} intro videos + {len(self.image_files)} images"
            else:
                self.add_console_message("🎉 Single project completed successfully!")
                result_msg = "Video generated successfully!"
            
            if CONFIG.get("captions_enabled", False):
                result_msg += " Captions were added to the video."
            
            if self.gpu_options:
                result_msg += f" GPU: {', '.join(self.gpu_options)}"
            
            self.show_toast(result_msg, "success")
            
        except Exception as e:
            if not self.processing_cancelled:
                self.add_console_message(f"❌ Generation error: {e}")
                self.show_toast(f"Generation failed: {e}", "error")
        finally:
            self.reset_processing_state()
    
    def batch_generation_worker(self, current_settings):
        """NEW: Background batch processing with videos as intro support"""
        try:
            self.update_progress(0, "Processing batch...")
            self.add_console_message("🎬 Starting batch processing with Videos as Intro support")
            
            if self.processing_cancelled:
                self.add_console_message("❌ Batch process cancelled before starting")
                return
            
            # --- FIX: Use the settings snapshot passed to this worker ---
            CONFIG.update(current_settings)
            
            creator = VideoCreator(update_callback=self.add_console_message)
            
            # --- FIX: Check for captions using the snapshot ---
            captioner = None
            dependencies = self.check_dependencies()
            if CONFIG.get("captions_enabled", False) and dependencies.get("whisper", False):
                model_size = CONFIG.get("whisper_model", "base")
                captioner = AutoCaptioner(model_size=model_size, update_callback=self.add_console_message)
                self.add_console_message("📝 Whisper available - captions will be added to batch videos")
            elif CONFIG.get("captions_enabled", False):
                self.add_console_message("⚠️ Captions enabled but Whisper not available - skipping caption generation")
            
            total_projects = len(self.found_projects)
            successful = 0
            failed = 0
            
            for i, project_folder in enumerate(self.found_projects):
                if self.processing_cancelled:
                    self.add_console_message(f"❌ Batch process cancelled after {successful} projects")
                    break
                
                project_number = i + 1
                progress = (i / total_projects) * 100
                project_name = os.path.basename(project_folder)
                
                self.add_console_message("\n" + "="*60)
                self.add_console_message(f"📦 PROJECT {project_number}/{total_projects}: {project_name}")
                self.add_console_message("="*60)
                
                self.update_progress(progress, f"Processing {project_name} ({project_number}/{total_projects})...")
                self.add_console_message(f"📁 Processing project: {project_name}")

                image_files, video_files, main_audio, local_bg_music, local_overlay = creator.find_media_files(project_folder)
                
                if (not image_files and not video_files) or not main_audio:
                    self.add_console_message(f"⚠️ Skipping {project_name}: Missing required files (needs audio and images/videos)")
                    failed += 1
                    continue
                
                if video_files and image_files and CONFIG.get("videos_as_intro_only", True):
                    self.add_console_message(f"🎬 Project structure: {len(video_files)} intro videos + {len(image_files)} slideshow images")
                
                if self.processing_cancelled:
                    self.add_console_message(f"❌ Batch process cancelled during {project_name}")
                    break
                
                bg_music_final = None
                if current_settings.get("use_bg_music", True):
                    bg_music_final = local_bg_music or self.batch_bg_music or None
                
                overlay_final = None
                if current_settings.get("use_overlay", False):
                    overlay_final = local_overlay or self.batch_overlay or None
                
                output_file = os.path.join(self.batch_output_folder, f"{project_name}.mp4")
                self.clean_existing_files(output_file)
                
                self.add_console_message(f"🎬 Creating video for {project_name}...")
                success = creator.create_slideshow(
                    image_files=image_files,
                    video_files=video_files,
                    main_audio=main_audio,
                    bg_music=bg_music_final,
                    overlay_video=overlay_final,
                    output_file=output_file
                )
                
                if not success:
                    self.add_console_message(f"❌ Failed to create video for {project_name}")
                    failed += 1
                    continue
                
                if not os.path.exists(output_file):
                    self.add_console_message(f"❌ Output file not found for {project_name}")
                    failed += 1
                    continue
                
                self.add_console_message(f"✅ Video created successfully for {project_name}")
                
                if self.processing_cancelled:
                    self.add_console_message(f"❌ Batch process cancelled before captioning {project_name}")
                    break
                
                # Auto-captioning if enabled (checks if captioner object was created AND captions are still enabled)
                if captioner and CONFIG.get("captions_enabled", False):
                    self.add_console_message(f"📝 Adding captions to {project_name}...")
                    caption_success = captioner.add_captions_to_video(output_file)
                    if not caption_success:
                        self.add_console_message(f"⚠️ Caption generation failed for {project_name}, but video was created successfully")
                    else:
                        self.add_console_message(f"✅ Captions added successfully to {project_name}")
                
                successful += 1
                self.add_console_message(f"✅ Completed {project_name}")
                
                next_progress = ((i + 1) / total_projects) * 100
                if i + 1 < total_projects:
                    self.update_progress(next_progress, f"Completed {project_name}, preparing next...")
            
            # Final results
            if not self.processing_cancelled:
                self.update_progress(100, "Batch processing complete!")
                self.add_console_message("🎉 Batch processing with Videos as Intro completed!")
                self.add_console_message(f"📊 Results: {successful} successful, {failed} failed")
                
                result_msg = f"Batch completed! {successful}/{total_projects} successful"
                if CONFIG.get("captions_enabled", False):
                    result_msg += " (with captions)"
                
                if self.gpu_options:
                    result_msg += f" GPU: {', '.join(self.gpu_options)}"
                
                toast_type = "success" if successful > 0 else "warning"
                self.show_toast(result_msg, toast_type)
            
        except Exception as e:
            if not self.processing_cancelled:
                self.add_console_message(f"❌ Batch processing error: {e}")
                self.show_toast(f"Batch processing failed: {e}", "error")
        finally:
            self.reset_processing_state()
    
    def apply_settings_to_config(self):
        """Apply current settings to global CONFIG"""
        CONFIG.update(self.current_settings)
        
        # Map quality preset to codec settings
        quality = self.current_settings.get("quality_preset", "High Quality")
        if quality == "Draft (Fast)":
            CONFIG["crf"] = 28
            CONFIG["preset"] = "ultrafast"
        elif quality == "Standard":
            CONFIG["crf"] = 23
            CONFIG["preset"] = "fast"
        elif quality == "High Quality":
            CONFIG["crf"] = 20
            CONFIG["preset"] = "medium"
        elif quality == "Ultra High":
            CONFIG["crf"] = 18
            CONFIG["preset"] = "slow"

# ===================================================================
# MAIN ENTRY POINT WITH VIDEOS AS INTRO SUPPORT
# ===================================================================

def main():
    """Main entry point - WITH VIDEOS AS INTRO FEATURE"""
    try:
        print("🌊 VideoStove - Videos as Intro Edition")
    except UnicodeEncodeError:
        print("VideoStove - Videos as Intro Edition")
    
    # Check for headless mode (CLI/Docker usage)
    if os.environ.get('HEADLESS') or not HAS_WEBVIEW:
        if os.environ.get('HEADLESS'):
            print("🐳 Running in headless mode (Docker/CLI)")
        elif not HAS_WEBVIEW:
            print("⚠️ Webview not available - running in headless mode")
        print("💡 Use the videostove_cli package for CLI operations")
        return
    
    # Check dependencies
    if not shutil.which("ffmpeg"):
        print("❌ FFmpeg is required but not found in PATH.")
        return

    # Initialize GPU detection
    gpu_options = detect_gpu_acceleration()
    
    try:
        import whisper
        print("✅ Whisper available - Auto-captioning enabled")
    except ImportError:
        print("⚠️ Whisper not found - Auto-captioning disabled")

    # Get UI directory path
    if getattr(sys, 'frozen', False):
        # The application is frozen
        ui_dir = os.path.join(sys._MEIPASS, 'ui')
    else:
        # The application is not frozen
        ui_dir = os.path.join(os.path.dirname(__file__), 'ui')

    index_path = os.path.join(ui_dir, 'index.html')
    
    # Check if UI files exist
    if not os.path.exists(index_path):
        print(f"❌ UI files not found at {ui_dir}")
        print("Please ensure the ui/ directory exists with index.html, styles.css, and script.js")
        return
    
    # Create API instance
    api = VideoStoveAPI()
    
    # Show processing mode status
    if gpu_options:
        print(f"🚀 GPU acceleration enabled: {', '.join(gpu_options)} (final assembly)")
        print("🖥️ CPU crossfades enabled for consistent performance")
        print("⚡ Hybrid processing: CPU crossfades + GPU final assembly")
    else:
        print("🖥️ Full CPU processing mode (no compatible GPU found)")
        print("✅ CPU crossfades enabled for consistent performance")
    
    print("🚀 Starting VideoStove interface...")
    
    # Create and start the VideoStove interface
    try:
        # Create window with local HTML file
        window = webview.create_window(
            'VideoStove - Videos as Intro Edition', 
            url=index_path,
            js_api=api, 
            width=1400, 
            height=900,
            resizable=True, 
            background_color='#0a0a0a'
        )
        
        api.set_window(window)
        webview.start(debug=False)
        
    except Exception as e:
        print(f"❌ Failed to start VideoStove interface: {e}")
        print("\n🔧 Solutions:")
        print("1. Make sure you have pywebview installed: pip install pywebview")
        print("2. Try fallback mode with embedded HTML")
        
        # Fallback: Ask user if they want to try embedded HTML
        try:
            response = input("\nTry fallback mode with embedded HTML? (y/n): ").lower()
            if response == 'y':
                run_fallback_mode(api)
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")

def run_fallback_mode(api_instance):
    """Fallback mode with embedded HTML - WITH VIDEOS AS INTRO SUPPORT"""
    print("🔄 Starting Videos as Intro fallback mode...")
    
    # Read HTML content
    if getattr(sys, 'frozen', False):
        ui_dir = os.path.join(sys._MEIPASS, 'ui')
    else:
        ui_dir = os.path.join(os.path.dirname(__file__), 'ui')
    
    try:
        with open(os.path.join(ui_dir, 'index.html'), 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        with open(os.path.join(ui_dir, 'styles.css'), 'r', encoding='utf-8') as f:
            css_content = f.read()
            
        with open(os.path.join(ui_dir, 'script.js'), 'r', encoding='utf-8') as f:
            js_content = f.read()
        
        # Embed CSS and JS into HTML
        embedded_html = html_content.replace(
            '<link rel="stylesheet" href="styles.css">',
            f'<style>{css_content}</style>'
        ).replace(
            '<script src="script.js"></script>',
            f'<script>{js_content}</script>'
        )
        
        # Create window with embedded HTML
        window = webview.create_window(
            'VideoStove - Videos as Intro Edition', 
            html=embedded_html,
            js_api=api_instance, 
            width=1400, 
            height=900,
            resizable=True, 
            background_color='#0a0a0a'
        )
        
        api_instance.set_window(window)
        webview.start(debug=False)
        
    except Exception as e:
        print(f"❌ Fallback mode failed: {e}")
        print("Please try using Python 3.11 or 3.12 instead of 3.13")


# CLI Bridge Functions
def build_visual_chain(inputs, preset_cfg):
    """
    Bridge function for CLI: Create video from images/videos
    
    Args:
        inputs: dict with 'root' key pointing to input directory
        preset_cfg: preset configuration dict
    
    Returns:
        Path to created video file
    """
    import tempfile
    import os
    
    input_dir = inputs.get('root')
    if not input_dir or not os.path.exists(input_dir):
        raise ValueError(f"Invalid input directory: {input_dir}")
    
    # Create temporary output file
    temp_dir = tempfile.gettempdir()
    temp_video = os.path.join(temp_dir, f"visual_chain_{os.getpid()}.mp4")
    
    # Create VideoCreator instance
    creator = VideoCreator()
    
    # Find media files in the directory
    image_files, video_files, main_audio, bg_music, overlay_video = creator.find_media_files(input_dir)
    
    if not image_files and not video_files:
        raise ValueError(f"No images or videos found in {input_dir}")
    
    # Check for overlay configuration and override with CONFIG overlay path if specified
    final_overlay_video = overlay_video  # Start with what was found in directory
    if CONFIG.get("use_overlay", False):
        overlay_path = CONFIG.get("overlay_path")
        if overlay_path and os.path.exists(overlay_path):
            final_overlay_video = overlay_path
            creator.log(f"🎭 Using overlay from CONFIG: {overlay_path}")
        elif overlay_video:
            creator.log(f"🎭 Using overlay found in directory: {overlay_video}")
        elif CONFIG.get("use_overlay"):
            creator.log("⚠️ Overlay enabled but no overlay file found")
    else:
        final_overlay_video = None  # Overlay disabled
    
    # For visual chain, we only create the video part (no audio mixing)
    # Use a dummy audio file or create silent audio if needed
    if not main_audio:
        # Create silent audio track
        silent_audio = os.path.join(temp_dir, f"silent_{os.getpid()}.mp3")
        duration = len(image_files) * CONFIG.get("image_duration", 8.0) if image_files else 60
        cmd = [
            'ffmpeg', '-y', '-f', 'lavfi', '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
            '-t', str(duration), '-c:a', 'libmp3lame', silent_audio
        ]
        import subprocess
        subprocess.run(cmd, capture_output=True)
        main_audio = silent_audio
    
    # Create the slideshow/video
    success = creator.create_slideshow(
        image_files=image_files,
        video_files=video_files,
        main_audio=main_audio,
        bg_music=None,  # No background music in visual chain
        overlay_video=final_overlay_video,  # Pass overlay video if configured
        output_file=temp_video
    )
    
    if not success or not os.path.exists(temp_video):
        raise RuntimeError("Failed to create visual chain")
    
    return temp_video


def mix_and_export(video_in, main_audio, bgm, levels, enc, out_path):
    """
    Bridge function for CLI: Mix video with audio and export
    OPTIMIZED VERSION: Uses stream copy and efficient audio filtering to prevent 992% CPU usage
    
    Args:
        video_in: Path to input video
        main_audio: Path to main audio (can be None for auto-detect)
        bgm: Path to background music (can be None)
        levels: Dict with 'main' and 'bg' volume levels
        enc: Dict with encoding settings ('use_gpu', 'crf', 'preset')
        out_path: Output file path
    
    Returns:
        Path to final video file
    """
    import subprocess
    import tempfile
    import os
    
    if not os.path.exists(video_in):
        raise ValueError(f"Input video not found: {video_in}")
    
    # Update CONFIG with encoding settings
    CONFIG.update({
        'use_gpu': enc.get('use_gpu', False),
        'crf': enc.get('crf', 22),
        'preset': enc.get('preset', 'fast'),
        'main_audio_vol': levels.get('main', 1.0),
        'bg_vol': levels.get('bg', 0.15)
    })
    
    # Build FFmpeg command
    cmd = ['ffmpeg', '-y', '-i', video_in]
    
    # Handle audio inputs and determine approach
    has_main_audio = main_audio and os.path.exists(main_audio)
    has_bgm = bgm and os.path.exists(bgm)
    
    if not has_main_audio and not has_bgm:
        # No audio, copy video only
        cmd.extend(['-c:v', 'copy', '-an', out_path])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")
        return out_path
    
    # PERFORMANCE OPTIMIZATION: Use direct audio filters instead of filter_complex
    # This prevents the 992% CPU usage issue by avoiding complex filter graph processing
    
    if has_main_audio and not has_bgm:
        # Single audio source - use efficient direct audio filter
        cmd.extend(['-i', main_audio])
        cmd.extend(['-map', '0:v:0', '-map', '1:a:0'])
        cmd.extend(['-c:v', 'copy'])  # Stream copy for video - maximum performance
        cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
        
        # Use direct audio filter instead of filter_complex for simple volume adjustment
        main_vol = levels.get('main', 1.0)
        if main_vol != 1.0:
            cmd.extend(['-filter:a', f'volume={main_vol}'])
    
    elif has_bgm and not has_main_audio:
        # BGM only - use efficient direct approach
        cmd.extend(['-stream_loop', '-1', '-i', bgm])
        cmd.extend(['-map', '0:v:0', '-map', '1:a:0'])
        cmd.extend(['-c:v', 'copy'])  # Stream copy for video - maximum performance
        cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
        
        # Use direct audio filter for BGM volume
        bg_vol = levels.get('bg', 0.15)
        if bg_vol != 1.0:
            cmd.extend(['-filter:a', f'volume={bg_vol}'])
    
    elif has_main_audio and has_bgm:
        # Multiple audio sources - need mixing but still optimize
        cmd.extend(['-i', main_audio])
        cmd.extend(['-stream_loop', '-1', '-i', bgm])
        
        # Use filter_complex only when absolutely necessary (multiple audio mixing)
        main_vol = levels.get('main', 1.0)
        bg_vol = levels.get('bg', 0.15)
        
        filter_complex = f"[1:a]volume={main_vol}[a_main];[2:a]volume={bg_vol}[a_bg];[a_main][a_bg]amix=inputs=2:duration=first[a_out]"
        cmd.extend(['-filter_complex', filter_complex])
        cmd.extend(['-map', '0:v:0', '-map', '[a_out]'])
        cmd.extend(['-c:v', 'copy'])  # Stream copy for video - maximum performance
        cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
    
    # Ensure output ends when shortest stream ends (prevents pause at end)
    cmd.extend(['-shortest'])
    
    # Output
    cmd.append(out_path)
    
    # Execute FFmpeg
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mixing failed: {result.stderr}")
    
    if not os.path.exists(out_path):
        raise RuntimeError(f"Output file not created: {out_path}")
    
    return out_path


# Make sure AutoCaptioner is available at module level
# (it's already defined in your run_main.py, so this just ensures it's accessible)
__all__ = ['CONFIG', 'build_visual_chain', 'mix_and_export', 'AutoCaptioner']


if __name__ == '__main__':
    main()