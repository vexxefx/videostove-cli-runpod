#!/bin/bash
set -e

# --- Args ---
JOB_FILE=$1        # e.g. batch__preset_science.yaml
DRIVE_FOLDER=$2    # e.g. VideoStove_Test

if [ -z "$JOB_FILE" ] || [ -z "$DRIVE_FOLDER" ]; then
  echo "Usage: ./start.sh <job.yaml> <DriveFolderName>"
  exit 1
fi

echo "▶️ Starting job: $JOB_FILE from Drive folder: $DRIVE_FOLDER"

# --- Rclone Config ---
mkdir -p /root/.config/rclone
if [ -z "$RCLONE_CONF_B64" ]; then
  echo "❌ RCLONE_CONF_B64 not set!"
  exit 1
fi
echo "$RCLONE_CONF_B64" | base64 -d > /root/.config/rclone/rclone.conf
echo "✅ rclone config loaded"

# --- Pull global assets + jobs ---
echo "⬇️ Pulling assets & jobs from gdrive:$DRIVE_FOLDER ..."
rclone copy gdrive:$DRIVE_FOLDER/assets /workspace/assets -P
rclone copy gdrive:$DRIVE_FOLDER/jobs /workspace/jobs -P

# --- Locate YAML ---
JOB_PATH=/workspace/jobs/$JOB_FILE
if [ ! -f "$JOB_PATH" ]; then
  echo "❌ Job file not found: $JOB_PATH"
  exit 1
fi
echo "✅ Using job file: $JOB_PATH"

# --- Parse global options ---
PRESET=$(yq '.batch.preset_file' $JOB_PATH)
OVERLAY=$(yq '.batch.overlay_video' $JOB_PATH)
FONT=$(yq '.batch.font_file' $JOB_PATH)
BGM=$(yq '.batch.bg_music' $JOB_PATH)

echo "🎬 Preset:  $PRESET"
echo "🎬 Overlay: $OVERLAY"
echo "🎬 Font:    $FONT"
echo "🎬 BGM:     $BGM"

# --- Process projects ---
PROJECT_COUNT=$(yq '.batch.projects | length' $JOB_PATH)
echo "📂 Found $PROJECT_COUNT projects in $JOB_FILE"

for i in $(seq 0 $((PROJECT_COUNT-1))); do
  NAME=$(yq ".batch.projects[$i].name" $JOB_PATH)
  OUTPUT=$(yq ".batch.projects[$i].output" $JOB_PATH)

  echo "➡️ Processing project: $NAME"

  # Pull project data from Drive
  rclone copy gdrive:$DRIVE_FOLDER/projects/$NAME /workspace/projects/$NAME -P

  # Run your renderer (replace with your actual CLI call)
  python3 /app/videostove_cli.py render $JOB_PATH --project $NAME

  # Upload result back to Drive/output
  echo "⬆️ Uploading output for $NAME ..."
  rclone copy $OUTPUT gdrive:$DRIVE_FOLDER/output -P

  echo "✅ Finished $NAME"
done

echo "🎉 All projects complete!"
