# OGScope Debug Console

English | [中文](DEBUG_CONSOLE.md)

## Overview

The OGScope debug console is a developer-focused camera tool: live preview, capture controls, parameter tuning, presets, and file management.

## Features

### Live preview
- Low-memory-board-friendly live preview. Effective FPS is governed by `preview_target_fps` and runtime throttling.
- Start/stop preview
- Live status: capture FPS, preview FPS, exposure, consumers, encoder, and memory pressure

### Capture
- **Still capture**: high-quality photos with auto-save
- **Video recording**: manual duration, MP4
- **Filenames**: timestamp-based names
- **Sidecar metadata**: `.txt` parameter file per capture

### Parameters
- **Exposure**: 1ms–100ms (fine steps)
- **Analog gain**: 1x–16x (0.1x steps)
- **Digital gain**: 1x–4x (0.1x steps)
- **White balance**: `auto` / `manual` / `night`; manual mode exposes red/blue gains
- **Auto-exposure ceiling**: `camera_auto_exposure_max_us` controls the longest dark-field frame duration
- **Flicker and noise reduction**: AE flicker and semantic noise-reduction modes
- **Preview encoder**: `auto` / `turbojpeg` / `opencv`
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

Camera status also exposes diagnostic fields:

| Field | Meaning |
|-------|---------|
| `sensor_target_fps` / `preview_target_fps` | Sensor and preview target FPS |
| `actual_capture_fps` / `actual_preview_fps` | Measured capture and preview FPS |
| `actual_exposure_us` / `frame_duration_us` | Current exposure and frame duration |
| `preview_consumers` / `analysis_consumers` / `recording_consumers` | Preview, analysis, and recording consumers |
| `jpeg_average_encode_ms` / `jpeg_cached_bytes` | JPEG encode time and cached bytes |
| `throttle_reason` | Current throttle reason, for example low memory or no consumers |
| `process_rss_kb` / `process_swap_kb` / `cma_free_kb` | Process memory, swap, and CMA free memory |
| `preview_encoder` / `jpeg_source_format` | Selected preview encoder and input format |
| `camera_driver` / `camera_backend` | Camera driver and backend names |
| `lores_enabled` / `lores_available` / `lores_width` / `lores_height` / `lores_format` | Low-resolution helper stream state |

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
5. **32-bit OS**: OpenCV, SciPy, and PyTurboJPEG may not have suitable wheels. Prefer distro packages or piwheels, and use lower preview FPS plus automatic encoder selection on low-memory boards.

## Camera Pipeline Configuration

These settings enter runtime through environment variables or config files. Names match `ogscope/config.py`:

| Setting | Default | Meaning |
|---------|---------|---------|
| `camera_idle_shutdown_sec` | `20.0` | Warm-idle timeout after the last consumer |
| `camera_frame_stale_timeout_sec` | `5.0` | Re-probe when no successful frame arrives within this duration |
| `camera_white_balance_mode` | `auto` | `auto` / `manual` / `night` |
| `camera_white_balance_gain_r` / `camera_white_balance_gain_b` | `1.0` | Manual white-balance red/blue gains |
| `camera_night_mode` | `false` | Apply night white-balance flag at startup |
| `camera_auto_exposure_max_us` | `2000000` | Longest AE frame duration for dark fields |
| `camera_ae_flicker_mode` | `off` | `off` / `50hz` / `60hz` |
| `camera_noise_reduction_mode` | `fast` | `off` / `fast` / `high_quality` |
| `camera_lores_enabled` | `true` | Enable the low-resolution helper stream |
| `camera_lores_width` / `camera_lores_height` | `320` / `240` | Low-resolution helper stream size |
| `camera_lores_format` | `YUV420` | Low-resolution helper stream format |
| `preview_encoder` | `auto` | `auto` / `turbojpeg` / `opencv` |

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
