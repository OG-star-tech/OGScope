# OGScope Debug Console

English | [中文](DEBUG_CONSOLE.md)

## Overview

The OGScope debug console is a developer-focused camera tool: live preview, capture controls, parameter tuning, presets, and file management.

## Features

### Live preview
- ~15 fps live preview
- Start/stop preview
- Live status

### Capture
- **Still capture**: high-quality photos with auto-save
- **Video recording**: manual duration, MP4
- **Filenames**: timestamp-based names
- **Sidecar metadata**: `.txt` parameter file per capture

### Parameters
- **Exposure**: 1ms–100ms (fine steps)
- **Analog gain**: 1x–16x (0.1x steps)
- **Digital gain**: 1x–4x (0.1x steps)
- **Apply immediately**: changes take effect at once
- **Reset**: restore defaults

### Presets
- **Save**: up to 10 presets
- **Apply**: one-click restore
- **Description** text per preset
- **Delete** presets

### Files
- **List** all captures
- **Download** to your machine
- **Info** with capture parameters
- **Auto refresh** after new shots

## Install and run

### 1) Dependencies

```bash
pip install -U pip setuptools wheel
pip install opencv-python-headless fastapi uvicorn numpy pillow
sudo apt install -y python3-picamera2 libcamera-apps
```

### 2) Start the service

```bash
poetry run python -m ogscope.main
```

### 3) Open the console

Browser: `http://localhost:8000/debug`

## Usage

### Basic flow

1. **Start preview** — click Start, wait for init, view stream.
2. **Tune parameters** — Parameters tab, adjust sliders, Apply.
3. **Capture still** — Capture tab, Capture photo; files under `~/dev_captures/`.
4. **Record video** — Start recording, stop when done.
5. **Presets** — Presets tab: name, description, Save; Apply from cards.
6. **Files** — Files tab: list, download, details.

### Keyboard shortcuts

- `Space`: start/stop preview
- `C`: capture photo
- `R`: start/stop recording
- `1`–`5`: switch tabs
- `Esc`: stop recording

## File layout

```
~/dev_captures/
├── IMG_20241201_143022.jpg
├── IMG_20241201_143022.txt
├── VID_20241201_143045.mp4
├── VID_20241201_143045.txt
└── presets.json
```

### Sidecar format (example)

```json
{
  "filename": "IMG_20241201_143022",
  "timestamp": "2024-12-01T14:30:22.123456",
  "exposure_us": 10000,
  "analogue_gain": 2.0,
  "digital_gain": 1.0,
  "resolution": "1920x1080",
  "file_size": 2048576,
  "camera_type": "imx327_mipi",
  "fps": 15
}
```

## API overview

### Camera
- `GET /api/dev/debug/camera/status`
- `POST /api/dev/debug/camera/start`
- `POST /api/dev/debug/camera/stop`
- `GET /api/dev/debug/camera/preview`

### Capture
- `POST /api/dev/debug/camera/capture`
- `POST /api/dev/debug/camera/record/start`
- `POST /api/dev/debug/camera/record/stop`

### Settings
- `POST /api/dev/debug/camera/settings`
- `POST /api/dev/debug/camera/reset`

### Presets
- `GET /api/dev/debug/camera/presets`
- `POST /api/dev/debug/camera/presets`
- `POST /api/dev/debug/camera/presets/{name}/apply`
- `DELETE /api/dev/debug/camera/presets/{name}`

### Files
- `GET /api/dev/debug/files`
- `GET /api/dev/debug/files/{filename}`
- `GET /api/dev/debug/files/{filename}/info`

## Tests

```bash
python scripts/test_debug_console.py
python scripts/test_debug_console.py --test api
python scripts/test_debug_console.py --test web
python scripts/test_debug_console.py --test deps
```

## Notes

1. **Hardware**: Picamera2-capable Raspberry Pi.
2. **Permissions**: camera access for the service user.
3. **Disk**: ensure free space for captures.
4. **Network**: Web UI requires reachable HTTP port.

## Troubleshooting

1. **Camera init fails** — verify Picamera2 import, `/dev/video*`, permissions; set `PYTHONPATH` / `LD_LIBRARY_PATH` for systemd if needed.
2. **No preview** — camera started? OpenCV? browser console errors?
3. **Save fails** — directory permissions, disk space, logs.
4. **Preset save fails** — duplicate name, 10-preset limit, write permissions.

### Logs

```bash
tail -f /home/<user>/ogscope_server.log
journalctl -u ogscope.service -f
```

## Raspberry Pi deployment notes

- Uses system Picamera2 / libcamera.
- Under venv, inject system paths in the service unit, e.g.  
  `PYTHONPATH=/usr/lib/python3/dist-packages:/usr/local/lib/python3.13/dist-packages`  
  `LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu`

## Support

1. This troubleshooting section  
2. Run test scripts  
3. Application logs  
4. Open an Issue on the repository

---

**OGScope Debug Console** — simpler camera bring-up for development.
