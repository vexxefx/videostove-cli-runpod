#!/usr/bin/env bash
set -euo pipefail

JOB_FILE="${1:-}"
DRIVE_FOLDER="${2:-}"

if [[ -z "$JOB_FILE" || -z "$DRIVE_FOLDER" ]]; then
  echo "Usage: /app/start.sh <job.yaml> <DriveFolder>"
  exit 1
fi

echo "▶️ Starting VideoStove with $JOB_FILE on Drive folder $DRIVE_FOLDER"

# ---------- rclone config ----------
mkdir -p /root/.config/rclone
: "${RCLONE_CONF_B64:?RCLONE_CONF_B64 env var is required}"
echo "$RCLONE_CONF_B64" | base64 -d > /root/.config/rclone/rclone.conf

# ---------- workspace layout ----------
ROOT=/workspace
JOBS_DIR="$ROOT/jobs"
ASSETS_DIR="$ROOT/assets"
PROJECTS_DIR="$ROOT/projects"
OUTPUT_DIR="$ROOT/output"
mkdir -p "$JOBS_DIR" "$ASSETS_DIR"/{presets,overlays,fonts,bgmusic} "$PROJECTS_DIR" "$OUTPUT_DIR"

# ---------- job file ----------
if [[ ! -f "$JOBS_DIR/$JOB_FILE" ]]; then
  echo "⬇️ Pulling job file from Drive: gdrive:$DRIVE_FOLDER/jobs/$JOB_FILE"
  rclone copyto "gdrive:$DRIVE_FOLDER/jobs/$JOB_FILE" "$JOBS_DIR/$JOB_FILE" -P
fi
JOB_PATH="$JOBS_DIR/$JOB_FILE"

# ---------- parse yaml for assets & projects ----------
PRESET=$(yq -r '.batch.preset_file // ""' "$JOB_PATH")
OVERLAY=$(yq -r '.batch.overlay_video // ""' "$JOB_PATH")
FONT=$(yq -r '.batch.font_file // ""' "$JOB_PATH")
BGM=$(yq -r '.batch.bg_music // ""' "$JOB_PATH")
mapfile -t PROJECTS < <(yq -r '.batch.projects[].name' "$JOB_PATH")

pull_asset () {
  local path="$1" subdir="$2"
  [[ -z "$path" || "$path" == "null" ]] && return 0
  local fname; fname="$(basename "$path")"
  echo "⬇️ Pulling $subdir asset: $fname"
  rclone copyto "gdrive:$DRIVE_FOLDER/assets/$subdir/$fname" "$ASSETS_DIR/$subdir/$fname" -P || true
}
pull_asset "$PRESET"  "presets"
pull_asset "$OVERLAY" "overlays"
pull_asset "$FONT"    "fonts"
pull_asset "$BGM"     "bgmusic"

for p in "${PROJECTS[@]}"; do
  echo "⬇️ Pulling project: $p"
  rclone copy "gdrive:$DRIVE_FOLDER/projects/$p" "$PROJECTS_DIR/$p" -P --create-empty-src-dirs
done

# ---------- render ----------
echo "🎥 Rendering via CLI (render-batch)…"
set -x
python3 -m videostove_cli.cli render-batch \
  --job "$JOB_PATH" \
  --assets-root "$ASSETS_DIR" \
  --projects-root "$PROJECTS_DIR" \
  --output-root "$OUTPUT_DIR"
set +x

# ---------- upload ----------
echo "⬆️ Uploading outputs (.mp4 found under /workspace)…"
if [[ -d "$OUTPUT_DIR" ]]; then
  rclone copy "$OUTPUT_DIR" "gdrive:$DRIVE_FOLDER/output" -P || true
else
  rclone copy "$ROOT" "gdrive:$DRIVE_FOLDER/output" --include="*.mp4" -P || true
fi

echo "🎉 All done!"