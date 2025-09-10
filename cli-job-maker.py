#!/usr/bin/env python3
import json
import yaml
import subprocess
from pathlib import Path

ROOT = Path.cwd() / "tmp_projects"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VID_EXTS = {".mp4", ".mov", ".avi", ".mkv"}
AUD_EXTS = {".mp3", ".wav", ".aac", ".flac"}

def rclone_lsjson(path):
    result = subprocess.run(
        ["rclone", "lsjson", f"gdrive:{path}"],
        capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)

def sync_presets(base_folder):
    remote_path = f"gdrive:{base_folder}/assets/presets"
    local_path = ROOT / "assets" / "presets"
    local_path.mkdir(parents=True, exist_ok=True)
    print(f"Pulling presets from {remote_path}")
    subprocess.run(["rclone", "copy", remote_path, str(local_path), "-P"], check=True)
    return local_path

def choose(title, items, allow_none=False):
    if not items:
        return None
    for i, it in enumerate(items, 1):
        print(f"[{i}] {it}")
    if allow_none:
        print("[0] None")
    n = int(input(f"Choose {title}: "))
    if allow_none and n == 0:
        return None
    return items[n-1]

def has_images(files):
    return any(Path(f).suffix.lower() in IMG_EXTS for f in files)

def has_videos(files):
    return any(Path(f).suffix.lower() in VID_EXTS for f in files)

def has_audio(files):
    return any(Path(f).suffix.lower() in AUD_EXTS for f in files)

def qualifies(files, mode: str):
    if not files:
        return False
    if mode == "slideshow":
        return has_images(files) and has_audio(files) and not has_videos(files)
    if mode == "montage":
        return has_images(files) and has_videos(files) and has_audio(files)
    return False

def upload_job(job_path, base_folder):
    remote_jobs_path = f"gdrive:{base_folder}/jobs"
    print(f"Uploading job to {remote_jobs_path}")
    subprocess.run(["rclone", "copy", str(job_path), remote_jobs_path, "-P"], check=True)

def main():
    base_folder = input("Enter your Google Drive folder (e.g. VideoStove_Test): ").strip()

    # 1. Pull presets
    preset_dir = sync_presets(base_folder)
    presets = list(preset_dir.glob("*.json"))
    if not presets:
        print("No presets found, exiting")
        return

    preset_choice = choose("preset", [p.name for p in presets])
    preset_path = preset_dir / preset_choice

    # detect mode from preset configuration
    try:
        pdata = json.loads(preset_path.read_text(encoding="utf-8"))
        # Get the preset name (first key in preset object)
        preset_name = list(pdata["preset"].keys())[0]
        preset_config = pdata["preset"][preset_name]
        mode = preset_config.get("project_type", "montage")
    except Exception as e:
        print(f"Error reading preset file: {e}")
        mode = "montage"

    print(f"Using preset {preset_choice} with mode = {mode}")

    # 2. List overlays/fonts/bgms
    overlays = [f["Name"] for f in rclone_lsjson(f"{base_folder}/assets/overlays") if not f["IsDir"]]
    fonts = [f["Name"] for f in rclone_lsjson(f"{base_folder}/assets/fonts") if not f["IsDir"]]
    bgms = [f["Name"] for f in rclone_lsjson(f"{base_folder}/assets/bgmusic") if not f["IsDir"]]

    overlay_choice = choose("overlay", overlays, allow_none=True)
    font_choice = choose("font", fonts, allow_none=True)
    bgm_choice = choose("bgmusic", bgms, allow_none=True)

    # 3. List projects
    projects_meta = rclone_lsjson(f"{base_folder}/projects")
    projects = [p["Name"] for p in projects_meta if p["IsDir"]]

    project_entries = []
    for project in projects:
        try:
            files_meta = rclone_lsjson(f"{base_folder}/projects/{project}")
        except subprocess.CalledProcessError:
            print(f"Could not list {project}, skipping")
            continue

        files = [f["Name"] for f in files_meta if not f["IsDir"]]

        if not qualifies(files, mode):
            print(f"SKIP {project} does not qualify for {mode}")
            continue

        print(f"OK {project} qualifies")
        project_entries.append({
            "name": project,
            "mode": mode,
            "inputs_dir": f"/workspace/projects/{project}",
            "output": f"/workspace/output/{project}__{preset_path.stem}.mp4"
        })

    if not project_entries:
        print("No projects qualified, exiting")
        return

    # 4. Build batch job.yaml
    job = {
        "batch": {
            "preset_file": f"/workspace/assets/presets/{preset_path.name}",
            "overlay_video": f"/workspace/assets/overlays/{overlay_choice}" if overlay_choice else None,
            "font_file": f"/workspace/assets/fonts/{font_choice}" if font_choice else None,
            "bg_music": f"/workspace/assets/bgmusic/{bgm_choice}" if bgm_choice else None,
            "gpu_mode": "auto",
            "projects": project_entries
        }
    }

    out_dir = ROOT / "jobs"
    out_dir.mkdir(parents=True, exist_ok=True)
    job_path = out_dir / f"batch__{preset_path.stem}.yaml"
    with open(job_path, "w") as f:
        yaml.safe_dump(job, f, sort_keys=False)

    print(f"Created batch job {job_path}")
    
    # Upload job to Google Drive
    upload_job(job_path, base_folder)
    print(f"Job uploaded to Google Drive at {base_folder}/jobs/")

if __name__ == "__main__":
    main()