# videostove_cli/cli.py
from __future__ import annotations
import argparse, sys, json
from pathlib import Path
from typing import List, Dict, Any, Optional

def _load_yaml(p: Path) -> Dict[str, Any]:
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def _load_preset_settings(preset_path: Path) -> (str, Dict[str, Any]):
    import json as _json
    data = _json.loads(Path(preset_path).read_text(encoding="utf-8"))
    name = (data.get("metadata") or {}).get("preset_name")
    inner = data.get("preset") or {}
    if not name and isinstance(inner, dict) and inner:
        name = next(iter(inner.keys()))
    cfg = inner.get(name, inner if isinstance(inner, dict) else data)
    return name or "default", cfg

def _ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def cmd_render_batch(args: argparse.Namespace) -> int:
    from videostove_cli.headless_bridge import render_with_run_main
    job_path = Path(args.job)
    assets_root = Path(args.assets_root)
    projects_root = Path(args.projects_root)
    output_root = Path(args.output_root)

    job = _load_yaml(job_path)
    batch = job.get("batch") or {}

    # resolve assets
    def norm(p: Optional[str], base: Path) -> Optional[Path]:
        if not p: return None
        p = str(p)
        if p == "null": return None
        if p.startswith("/"): return Path(p)
        return base / p

    preset_path = norm(batch.get("preset_file"), assets_root / "presets")
    overlay_path = norm(batch.get("overlay_video"), assets_root / "overlays")
    font_path    = norm(batch.get("font_file"), assets_root / "fonts")
    bgm_path     = norm(batch.get("bg_music"), assets_root / "bgmusic")

    if not preset_path or not preset_path.exists():
        print("❌ Preset file not found:", preset_path, file=sys.stderr)
        return 2

    preset_name, preset_cfg = _load_preset_settings(preset_path)

    # projects (support list[str] or list[dict{name,...}])
    raw_projects = batch.get("projects") or []
    proj_names: List[str] = []
    for item in raw_projects:
        if isinstance(item, str):
            proj_names.append(item)
        elif isinstance(item, dict) and "name" in item:
            proj_names.append(str(item["name"]))

    if not proj_names:
        print("❌ No projects in job", file=sys.stderr)
        return 2

    # rules (montage/slideshow)
    mode = (preset_cfg.get("project_type") or "").lower().strip()
    if mode not in {"montage","slideshow"}:
        # default to montage if absent
        mode = "montage"

    ok_any = False
    for name in proj_names:
        input_dir = projects_root / name
        if not input_dir.exists():
            print(f"❌ Missing local project folder: {input_dir}", file=sys.stderr)
            continue

        # scan inputs
        imgs = list(input_dir.glob("*.jpg")) + list(input_dir.glob("*.jpeg")) + list(input_dir.glob("*.png"))
        vids = list(input_dir.glob("*.mp4")) + list(input_dir.glob("*.mov")) + list(input_dir.glob("*.mkv"))
        auds = list(input_dir.glob("*.mp3")) + list(input_dir.glob("*.wav")) + list(input_dir.glob("*.m4a"))

        def has_img(): return len(imgs) > 0
        def has_vid(): return len(vids) > 0
        def has_aud(): return len(auds) > 0

        eligible = False
        if mode == "slideshow":
            # images + audio; no videos allowed
            eligible = has_img() and has_aud() and not has_vid()
        else:  # montage
            # images + videos + audio
            eligible = has_img() and has_vid() and has_aud()

        if not eligible:
            print(f"⚠️  Skipping {name} (mode={mode} imgs={len(imgs)} vids={len(vids)} auds={len(auds)})")
            continue

        out_name = f"{name}__{preset_name}.mp4"
        out_path = output_root / out_name
        _ensure_dir(out_path)

        print(f"🎥 Rendering project: {name}")
        try:
            final = render_with_run_main(
                input_dir=input_dir,
                output_path=out_path,
                preset_cfg=preset_cfg,
                overlay_path=overlay_path,
                font_path=font_path,
                bgm_path=bgm_path,
            )
            print(f"✅ Done: {final}")
            ok_any = True
        except Exception as e:
            print(f"❌ Render failed for {name}: {e}", file=sys.stderr)

    return 0 if ok_any else 1

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="videostove")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("render-batch", help="Render from a batch job.yaml (pure CLI)")
    b.add_argument("--job", required=True, help="Path to job YAML in /workspace/jobs")
    b.add_argument("--assets-root", default="/workspace/assets")
    b.add_argument("--projects-root", default="/workspace/projects")
    b.add_argument("--output-root", default="/workspace/output")
    b.set_defaults(func=cmd_render_batch)

    args = p.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())