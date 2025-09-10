# videostove_cli/headless_bridge.py - FIXED VERSION
from __future__ import annotations
import importlib.util, sys, os
from pathlib import Path
from typing import Optional, Dict, Any
import glob
import gc
import signal
import threading

SEARCH_CANDIDATES = (
    "/app/run_main.py",
    "/workspace/run_main.py", 
    "run_main.py",
)

class RunMainMissing(Exception):
    pass

def load_run_main():
    for p in SEARCH_CANDIDATES:
        if Path(p).exists():
            spec = importlib.util.spec_from_file_location("run_main", p)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["run_main"] = mod
            spec.loader.exec_module(mod)
            # sanity
            if not hasattr(mod, "CONFIG"):
                mod.CONFIG = {}
            needed = ["build_visual_chain", "mix_and_export", "AutoCaptioner"]
            missing = [n for n in needed if not hasattr(mod, n)]
            if missing:
                raise RunMainMissing(f"run_main.py missing symbols: {missing}")
            return mod
    raise ImportError("run_main.py not found")

def find_main_audio(input_dir: Path) -> Optional[str]:
    """Find the main audio file in input directory"""
    audio_patterns = ['*.mp3', '*.wav', '*.m4a', '*.aac', '*.flac', '*.ogg']
    audio_files = []
    
    for pattern in audio_patterns:
        audio_files.extend(glob.glob(str(input_dir / pattern)))
    
    if not audio_files:
        return None
    
    # Sort and return first audio file (primary audio)
    audio_files.sort()
    return audio_files[0]

def find_overlay_files() -> Optional[str]:
    """Find overlay files in common locations"""
    overlay_search_paths = [
        "/workspace/assets/overlays",
        "/app/assets/overlays", 
        "./assets/overlays",
        "./overlays",
        "/workspace/overlays"
    ]
    
    overlay_extensions = ['*.mp4', '*.mov', '*.avi', '*.webm', '*.mkv']
    
    for search_path in overlay_search_paths:
        if Path(search_path).exists():
            for ext in overlay_extensions:
                overlay_files = list(Path(search_path).glob(ext))
                if overlay_files:
                    # Return first found overlay file
                    return str(overlay_files[0])
    return None

def map_preset_to_config(cfg: Dict[str, Any],
                         overlay_path: Optional[Path],
                         font_path: Optional[Path],
                         bgm_path: Optional[Path]) -> Dict[str, Any]:
    m: Dict[str, Any] = {}

    # core
    m["use_gpu"]              = bool(cfg.get("use_gpu", False))
    m["crf"]                  = int(cfg.get("crf", 22))
    m["ffmpeg_preset"]        = cfg.get("preset", "fast")
    m["videos_as_intro_only"] = bool(cfg.get("videos_as_intro_only", True))
    m["loop_videos"]          = bool(cfg.get("loop_videos", False))

    # overlay - improved path resolution
    m["use_overlay"]   = bool(cfg.get("use_overlay", False))
    m["overlay_mode"]  = cfg.get("overlay_mode", "screen_blend")
    m["overlay_opacity"]= float(cfg.get("overlay_opacity", 0.5))
    
    # Try to resolve overlay path: passed path -> auto-discover -> None
    resolved_overlay_path = None
    if overlay_path and overlay_path.exists():
        resolved_overlay_path = str(overlay_path)
    elif m["use_overlay"]:
        # Auto-discover overlay file if overlay is enabled but no path provided
        discovered_overlay = find_overlay_files()
        if discovered_overlay:
            resolved_overlay_path = discovered_overlay
            print(f"🎭 Auto-discovered overlay: {discovered_overlay}")
    
    m["overlay_path"] = resolved_overlay_path

    # audio
    m["use_bg_music"]  = bool(cfg.get("use_bg_music", False))
    m["bg_vol"]        = float(cfg.get("bg_vol", 0.15))
    m["main_audio_vol"]= float(cfg.get("main_audio_vol", 1.0))
    m["bgm_path"]      = str(bgm_path) if bgm_path else None

    # captions
    m["captions_enabled"]        = bool(cfg.get("captions_enabled", False))
    m["caption_type"]            = cfg.get("caption_type", "single")
    m["whisper_model"]           = cfg.get("whisper_model", "tiny")
    m["use_faster_whisper"]      = bool(cfg.get("use_faster_whisper", True))
    m["live_timing_enabled"]     = bool(cfg.get("live_timing_enabled", False))
    m["karaoke_effect_enabled"]  = bool(cfg.get("karaoke_effect_enabled", False))
    m["max_chars_per_line"]      = int(cfg.get("max_chars_per_line", 45))

    # caption style
    for k in [
        "font_family","font_size","font_weight","text_color",
        "outline_color","outline_width","border_enabled",
        "border_color","border_width","shadow_enabled","shadow_blur",
        "line_spacing","vertical_position","horizontal_position",
        "margin_vertical","margin_horizontal","use_caption_background",
        "background_color","background_opacity"
    ]:
        if k in cfg: m[k] = cfg[k]
    m["font_path"] = str(font_path) if font_path else None

    # zoom / motion
    zoom_direction = cfg.get("extended_zoom_direction", "in_out")
    # Auto-enable extended zoom if in_out direction is specified or explicitly enabled
    extended_zoom_enabled = bool(cfg.get("extended_zoom_enabled", False)) or zoom_direction == "in_out"
    
    m["extended_zoom_enabled"]   = extended_zoom_enabled
    m["extended_zoom_direction"] = zoom_direction
    m["extended_zoom_amount"]    = float(cfg.get("extended_zoom_amount", 30))
    m["single_image_zoom"]       = bool(cfg.get("single_image_zoom", False))

    # fades/crossfades
    m["use_crossfade"]       = bool(cfg.get("use_crossfade", False))
    m["crossfade_duration"]  = float(cfg.get("crossfade_duration", 0.6))
    m["use_fade_in"]         = bool(cfg.get("use_fade_in", False))
    m["use_fade_out"]        = bool(cfg.get("use_fade_out", False))

    return m

def render_with_run_main(
    input_dir: Path,
    output_path: Path,
    preset_cfg: Dict[str, Any],
    overlay_path: Optional[Path],
    font_path: Optional[Path],
    bgm_path: Optional[Path],
) -> Path:
    os.environ["HEADLESS"] = "1"
    rm = load_run_main()
    rm.CONFIG.update(map_preset_to_config(preset_cfg, overlay_path, font_path, bgm_path))

    # visuals
    tmp_visual = rm.build_visual_chain(
        inputs={"root": str(input_dir)},
        preset_cfg=preset_cfg,
    )

    # FIXED: Find main audio file in input directory
    main_audio_file = find_main_audio(input_dir)
    if not main_audio_file:
        print(f"Warning: No audio file found in {input_dir}")

    # audio + export
    final_path = rm.mix_and_export(
        video_in=tmp_visual,
        main_audio=main_audio_file,  # FIXED: Pass actual audio file path
        bgm=rm.CONFIG.get("bgm_path"),
        levels={"main": rm.CONFIG.get("main_audio_vol", 1.0),
                "bg":   rm.CONFIG.get("bg_vol", 0.15)},
        enc={"use_gpu": rm.CONFIG.get("use_gpu", False),
             "crf":     rm.CONFIG.get("crf", 22),
             "preset":  rm.CONFIG.get("ffmpeg_preset", "fast")},
        out_path=str(output_path),
    )

    # captions
    if rm.CONFIG.get("captions_enabled", False):
        cap = rm.AutoCaptioner(model_size=rm.CONFIG.get("whisper_model","tiny"))
        caption_result = cap.add_captions_to_video(str(final_path))
        # FIXED: Handle caption result properly
        if caption_result and isinstance(caption_result, str):
            final_path = caption_result
        # If caption_result is True/False, keep original final_path
        
        # Clean up Whisper model to prevent hanging
        try:
            if hasattr(cap, 'model') and cap.model is not None:
                del cap.model
                cap.model = None
                cap.model_loaded = False
        except:
            pass

    # Force cleanup of any GPU contexts and processes
    try:
        # Clean up any remaining subprocess handles
        try:
            # Force garbage collection of subprocess objects
            gc.collect()
            
            # Kill any remaining child processes
            try:
                children = os.waitpid(-1, os.WNOHANG)
            except:
                pass
        except:
            pass
        
        # Clean up CUDA context if torch is loaded
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except:
            pass
            
        # Final garbage collection
        gc.collect()
        
    except:
        pass

    return Path(final_path)