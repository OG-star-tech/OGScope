# OGScope Development Guide (Board Deployment and Debugging)

[中文](README.md) | English

This document explains how OGScope is actually run on development boards
(Raspberry Pi / Orange Pi), including dependency requirements, service startup,
and the team-standard debug workflow.

Recommended workflow: **edit locally -> upload to board -> restart with
`systemd` -> verify**.  
This matches real hardware runtime behavior.

## 1. Python Version and Project Dependencies

### 1.1 Python baseline

- Source of truth: `pyproject.toml` (`python = "^3.10"`)
- Recommended board runtime: Python 3.10+
- Any `3.9+` wording in old docs should be treated as historical

### 1.2 Install Poetry and Python packages

```bash
cd /path/to/OGScope
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
poetry install
```

### 1.3 Install script (recommended for first-time setup)

The repository provides `scripts/install.sh`. It performs initial board setup:

- installs system dependencies and Poetry
- installs project dependencies
- creates/updates `systemd` service (`ogscope.service`)
- injects `PYTHONPATH` and `LD_LIBRARY_PATH`
- enables service autostart

Run:

```bash
cd /path/to/OGScope
chmod +x scripts/install.sh
./scripts/install.sh
```

### 1.4 Dependency maintenance

- keep `poetry.lock` in sync with the repository
- run `poetry install` after significant code updates
- prefer a fixed venv Python in service startup (see section 5)

## 2. System Dependencies (Important)

OGScope depends on board-level camera stack (`picamera2`/`libcamera`) in
addition to Poetry packages.

Typical requirements:

- Python/build tools: `python3`, `python3-venv`, `python3-dev`, `build-essential`
- camera stack: `python3-picamera2` (with system `libcamera` runtime)
- image stack: `libjpeg`, `libpng`, OpenCV-related system libs

Example:

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-dev build-essential \
  python3-picamera2 libjpeg-dev libpng-dev libopencv-dev
```

## 3. Why `PYTHONPATH` Is Needed in a Virtual Environment

This is a key runtime detail for this project.

- OGScope runs in a Poetry virtual environment
- board camera packages are often installed via `apt` into system paths (for
  example `/usr/lib/python3/dist-packages`)
- those system paths are not always in the Poetry venv `sys.path`

Result: service may fail to import packages such as `picamera2`.

So the service explicitly injects `PYTHONPATH`, for example:

```ini
Environment=PYTHONPATH=/usr/lib/python3/dist-packages:/usr/local/lib/python3.13/dist-packages
```

And for shared libraries:

```ini
Environment=LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu
```

## 4. Startup Chain and Script Status

### 4.1 Active runtime startup chain

1. `systemd` starts service `ogscope`
2. `ExecStart` runs `python -m ogscope.main` (typically venv Python)
3. `ogscope/main.py` starts Uvicorn with `ogscope.web.app:app`

### 4.2 Script status in repository

- `scripts/install.sh`
  - purpose: setup/install and create service
  - status: installer utility, not a runtime auto-invoked entrypoint
- `scripts/start_debug_console.sh`
  - purpose: foreground run with `PYTHONPATH`/`LD_LIBRARY_PATH`
  - status: manual debug helper, not default production startup
- `Makefile` (`run/dev/deploy`)
  - purpose: developer convenience commands
  - status: helper entrypoints, not replacement for `systemd`

## 5. Configure `systemd` Service and Autostart

Recommended service path:

- `/etc/systemd/system/ogscope.service`

Template:

```ini
[Unit]
Description=OGScope Service
After=network.target

[Service]
Type=simple
User=<your-user>
WorkingDirectory=<project-dir>
Environment=PYTHONPATH=/usr/lib/python3/dist-packages:/usr/local/lib/python3.13/dist-packages
Environment=LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu
Environment=OGSCOPE_RELOAD=false
Environment=OGSCOPE_LOG_LEVEL=INFO
ExecStart=<venv-path>/bin/python -m ogscope.main
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ogscope
sudo systemctl start ogscope
sudo systemctl status ogscope
```

## 6. Code Update and Deployment Flow (Team Standard)

### 6.1 First deployment

1. Clone/pull project code
2. Run `scripts/install.sh`
3. Start and validate `ogscope` service

### 6.2 Daily update flow

After code updates (`git pull` or manual upload), run:

```bash
cd /path/to/OGScope
poetry install
sudo systemctl restart ogscope
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

Notes:

- if only templates/static files changed, `poetry install` is usually not needed
- if service file changed, run `sudo systemctl daemon-reload` first

## 7. PyCharm Remote Development (Current Practice)

Current practice is **local IDE editing + manual deployment to board**, not
IDE-managed remote runtime.

Recommended steps:

1. edit in local PyCharm
2. upload changes to board
3. run `sudo systemctl restart ogscope`
4. verify via `status` and `journalctl`
5. validate behavior via Web/API

## 8. Debug SOP

```bash
sudo systemctl restart ogscope
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

Quick API checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api
```

## 9. Troubleshooting Checklist

If service fails to start, check:

- `WorkingDirectory` points to project root
- `ExecStart` uses correct venv Python
- `PYTHONPATH` includes system `dist-packages`
- `LD_LIBRARY_PATH` includes `libcamera` library path
- code upload is complete and dependencies are installed

## 10. Command Cheatsheet

```bash
poetry install
poetry run python -m ogscope.main
sudo systemctl restart ogscope
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```
