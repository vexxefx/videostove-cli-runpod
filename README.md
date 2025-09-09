# VideoStove CLI Cloud

GPU-accelerated batch video rendering pipeline, optimized for **RunPod Serverless**.
Pulls assets and projects from Google Drive, processes them with presets, and pushes outputs back automatically.

---

## ✨ Features

* 🎯 **Preset-first workflow** → generate YAML jobs locally
* 🗂️ **Google Drive integration** via `rclone` (assets, projects, jobs, outputs)
* ⚡ **Mode aware** → slideshow vs montage qualification rules
* 🎬 **Batch processing** → multiple projects in a single YAML
* ☁️ **RunPod ready** → secure auth via `$RCLONE_CONF_B64`
* 🐳 **Dockerized** → portable, reproducible builds

---

## 📂 Google Drive Structure

```
<DriveFolder>/
├── assets/
│   ├── presets/
│   ├── overlays/
│   ├── fonts/
│   └── bgmusic/
├── projects/
│   ├── project1/
│   │   ├── img1.jpg
│   │   ├── video1.mp4
│   │   └── audio.mp3
│   └── project2/...
├── jobs/
│   ├── batch__preset_twovet_20250908.yaml
│   └── batch__preset_science.yaml
└── output/
    └── (rendered mp4 files pushed here)
```

---

## 🔧 Local Setup

```bash
git clone https://github.com/<yourusername>/videostove-cli-cloud.git
cd videostove-cli-cloud
pip install -r requirements.txt
```

Generate a batch YAML locally:

```bash
python3 cli-job-maker.py
# Follows prompts → outputs tmp_projects/jobs/batch__*.yaml
# Auto-uploads YAML to gdrive:<DriveFolder>/jobs/
```

---

## 🐳 Docker Build & Push

```bash
docker build -t vexexfx/videostove-cli-cloud:latest .
docker push vexexfx/videostove-cli-cloud:latest
```

---

## 🚀 RunPod Usage

### Environment Variable

* `RCLONE_CONF_B64` → base64 encoded `rclone.conf`

  ```bash
  base64 -w 0 ~/.config/rclone/rclone.conf
  ```

### Input Arguments

`start.sh` expects:

```
<job.yaml filename> <DriveFolderName>
```

Example (RunPod Web UI input box):

```
batch__preset_twovet_20250908.yaml VideoStove_Test
```

### RunPod CLI Example

```bash
runpodctl create-job \
  --image vexexfx/videostove-cli-cloud:latest \
  --input "batch__preset_twovet_20250908.yaml VideoStove_Test"
```

---

## ⚙️ Rendering Workflow

1. Decode `rclone.conf` from `$RCLONE_CONF_B64`
2. Pull `/assets/` and `/jobs/` from Drive
3. Locate selected job YAML in `/workspace/jobs/`
4. For each project in YAML:

   * Pull project folder from Drive
   * Run render via `videostove_cli.py`
   * Push result to `<DriveFolder>/output/`

---

## 📝 License

MIT — free to use and modify.

---
