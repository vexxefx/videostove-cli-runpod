#!/bin/bash
set -e

JOB_FILE=$1

if [ -z "$JOB_FILE" ]; then
  echo "Usage: ./start.sh path/to/batch.yaml"
  exit 1
fi

echo "▶️ Starting VideoStove job with file: $JOB_FILE"

# 1. Setup rclone config from env var
mkdir -p /root/.config/rclone
if [ -z "$RCLONE_CONF_B64" ]; then
  echo "❌ RCLONE_CONF_B64 not set!"
  exit 1
fi
echo "$RCLONE_CONF_B64" | base64 -d > /root/.config/rclone/rclone.conf
echo "✅ rclone config loaded"

# 2. Pull global assets
echo "⬇️ Pulling global assets..."
rclone copy gdrive:VideoStove_Test/assets /workspace/assets -P

# 3. Read global options from job file
PRESET=$(yq '.batch.preset_file' $JOB_FILE)
OVERLAY=$(yq '.batch.overlay_video' $JOB_FILE)
FONT=$(yq '.batch.font_file' $JOB_FILE)
BGM=$(yq '.batch.bg_music' $JOB_FILE)

echo "🎬 Preset: $PRESET"
echo "🎬 Overlay: $OVERLAY"
echo "🎬 Font: $FONT"
echo "🎬 BGM: $BGM"

# 4. Process projects
PROJECT_COUNT=$(yq '.batch.projects | length' $JOB_FILE)
echo "📂 Found $PROJECT_COUNT projects in batch file"

for i in $(seq 0 $((PROJECT_COUNT-1))); do
  NAME=$(yq ".batch.projects[$i].name" $JOB_FILE)
  INPUTS=$(yq ".batch.projects[$i].inputs_dir" $JOB_FILE)
  OUTPUT=$(yq ".batch.projects[$i].output" $JOB_FILE)

  echo "➡️ Processing project: $NAME"

  # Pull project data
  rclone copy gdrive:VideoStove_Test/projects/$NAME /workspace/projects/$NAME -P

  # Run VideoStove CLI (replace with your actual CLI command if needed)
  python3 videostove_cli.py render $JOB_FILE --project $NAME

  # Upload result back to Drive
  echo "⬆️ Uploading output for $NAME..."
  rclone copy $OUTPUT gdrive:VideoStove_Test/output -P

  echo "✅ Finished $NAME"
done

echo "🎉 All projects processed successfully!"
