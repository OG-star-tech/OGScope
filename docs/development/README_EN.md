# OGScope Development Guide (Board Deployment and Debugging)

[中文](README.md) | English

This document explains how OGScope is actually run on development boards
(Raspberry Pi / Orange Pi), including dependency requirements, service startup,
and the team-standard debug workflow.

For testing workflow, see [Testing Guide](testing-guide.md).

Recommended workflow: **edit locally -> upload to board -> restart with
`systemd` -> verify**.  
This matches real hardware runtime behavior.

## 0. Quick deployment checklist (hobbyists)

This section lists **common commands and checks only**. For Poetry/PEP 668, mirror options, uninstall, and troubleshooting details, see **§1–§11** below.

### 0.1 Requirements

- Board: **ARM** (`aarch64` or `armhf`), e.g. Raspberry Pi / Orange Pi  
- OS: **Debian/apt**-based images (compatible with `picamera2`/`libcamera`; install script reads `/etc/os-release`, see **§1.4**)  
- Python: **3.10+** (see `pyproject.toml`)  
- Network: first install downloads dependencies; Web UI needs **TCP 8000** reachable (configure firewall as needed)

### 0.2 First-time install

```bash
cd /path/to/OGScope
chmod +x scripts/install.sh
./scripts/install.sh
```

Summary: default `poetry install --only main`; in mainland China use **`export OGSCOPE_MIRROR=cn`**; low-memory boards: **`OGSCOPE_APT_SLOW=1`**. Full options: **§1.4**. After install: `sudo systemctl start ogscope`.

### 0.3 Plate-solve data

Place **`default_database.npz`** under **`data/plate_solve/`** (not shipped in the repo). See [plate-solve-data.md](plate-solve-data.md).

### 0.4 Routine updates

```bash
cd /path/to/OGScope
chmod +x scripts/board-update.sh
# optional: OGSCOPE_GIT_PULL=1  OGSCOPE_MIRROR=cn
./scripts/board-update.sh
```

Details: **§6.2**.

### 0.5 Uninstall and health check

- Remove service and `.venv`: **§6.3** (`scripts/uninstall.sh`)  
- Health and logs:

```bash
curl -s http://127.0.0.1:8000/health
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

### 0.6 Troubleshooting (short)

| Symptom | Where to look |
|---------|----------------|
| `ImportError: picamera2` | Install camera stack with `apt`; venv from `install.sh` (**§1.2, §3**) |
| PEP 668 | Use project `.venv` only; do not mix into system Python (**§1.2**) |
| Service fails to start | `WorkingDirectory`, `ExecStart`, `journalctl` (**§10**) |

## 1. Python Version and Project Dependencies

### 1.1 Python baseline

- Source of truth: `pyproject.toml` (`python = "^3.10"`)
- Recommended board runtime: Python 3.10+
- Any `3.9+` wording in old docs should be treated as historical

### 1.2 Poetry, PEP 668, and the virtual environment (required reading)

- **You must use a Poetry-managed project venv** (`.venv`). Do **not** set
  `virtualenvs.create false` globally and mix packages into the system Python;
  that leads to **PEP 668** errors (distribution-managed site-packages cannot be
  modified by `pip`/`poetry`).
- On the board, run `scripts/install.sh` to set `virtualenvs.create true`,
  `virtualenvs.in-project true`, and preferably
  **`virtualenvs.options.system-site-packages true`** so the venv can import
  `apt`-installed `picamera2`.
- **Production defaults** to runtime-only deps: `poetry install --only main`
  (script default). For pytest and dev tools, set `OGSCOPE_INSTALL_DEV=1` on a
  dev machine or board and reinstall.

### 1.3 Install Poetry and Python packages

```bash
cd /path/to/OGScope
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
# dev machine: full dependency set including dev
poetry install
# board (manual): match install.sh default
# poetry install --no-interaction --only main
```

### 1.4 Install script (recommended for first-time setup)

The repository provides `scripts/install.sh`. It performs initial board setup:

- reads `/etc/os-release` and **only supports Debian/Ubuntu family** (including **Raspberry Pi OS**); aborts on other distros for safety
- installs system dependencies and Poetry
- configures Poetry for `.venv` and `system-site-packages` (when supported)
- defaults to `poetry install --only main` (set `OGSCOPE_INSTALL_DEV=1` for dev)
- optional `OGSCOPE_APT_SLOW=1`: stagger `apt` and pause between batches on low-memory boards
- **`OGSCOPE_MIRROR`**: `auto` (default, heuristic from `LANG`/`LC_*` and timezone), `cn` (mainland China mirrors for apt + PyPI via Tsinghua), `international` (do not rewrite apt; default PyPI). If you are in China but use `en_US` locale, set `export OGSCOPE_MIRROR=cn`.
- creates `logs`, `uploads`, `data/plate_solve`, etc.
- creates/updates `systemd` service (`ogscope.service`)
- injects `PYTHONPATH` and `LD_LIBRARY_PATH` (paths that exist)
- enables service autostart

Run:

```bash
cd /path/to/OGScope
chmod +x scripts/install.sh
./scripts/install.sh
```

### 1.5 Dependency maintenance

- keep `poetry.lock` in sync with the repository
- after updates on the board, run `./scripts/board-update.sh`, or
  `poetry install --only main` then `sudo systemctl restart ogscope`
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

**Relationship to `system-site-packages`**: when enabled, the venv `sys.path`
includes system site-packages, which is usually enough to `import picamera2`.
`PYTHONPATH` in `systemd` still covers distro-specific paths such as
`/usr/local/lib/python3.x/dist-packages`; both layers work together.

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
- `scripts/board-update.sh`
  - purpose: incremental update after install (optional `OGSCOPE_GIT_PULL=1` for
    `git pull`, `poetry install`, restart `ogscope`)
  - status: recommended for routine deployment
- `scripts/uninstall.sh`
  - purpose: stop and remove `ogscope` systemd unit, optionally remove `.venv`;
    keeps `logs/`, `data/` by default; requires confirmation (`YES` or
    `OGSCOPE_UNINSTALL_CONFIRM=1`)
  - status: uninstall helper; does not remove apt packages or global Poetry
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

After code updates (`git pull` or manual upload), you can run:

```bash
cd /path/to/OGScope
chmod +x scripts/board-update.sh
# with git and need pull: OGSCOPE_GIT_PULL=1 ./scripts/board-update.sh
./scripts/board-update.sh
```

Or manually:

```bash
cd /path/to/OGScope
poetry install --no-interaction --only main
sudo systemctl restart ogscope
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

Notes:

- if only templates/static files changed, `poetry install` is usually not needed
- if service file changed, run `sudo systemctl daemon-reload` first

### 6.3 Uninstall service and local environment (`scripts/uninstall.sh`)

Use `scripts/uninstall.sh` when you need to **remove the systemd unit**, delete the project **`.venv`**, or clean up before reinstalling in another directory. The script **does not** remove packages installed with `apt` (e.g. `python3-picamera2`) or the user-level **Poetry** installation; it only manages the OGScope service file and optional content under the project tree.

**What it does**

- `systemctl stop` / `disable` `ogscope`
- removes `/etc/systemd/system/ogscope.service` if present, then `daemon-reload`
- by default removes `.venv` at the project root (can be kept; see below)

**Kept by default**

- `logs/`, `uploads/`, `data/` (including `data/plate_solve/`); to remove them you must opt in (below)

**Environment variables**

| Variable | Meaning |
|----------|---------|
| `OGSCOPE_UNINSTALL_CONFIRM=1` | **Required for non-interactive** runs (CI, scripts); without it, the script exits when stdin is not a TTY |
| `OGSCOPE_UNINSTALL_KEEP_VENV=1` | keep `.venv` |
| `OGSCOPE_UNINSTALL_REMOVE_DATA=1` | **dangerous**: deletes `logs/`, `uploads/`, `data/` (user data including plate DB) |

**Interactive**: if `OGSCOPE_UNINSTALL_CONFIRM=1` is not set and the session is a TTY, type **`YES`** in full caps to proceed.

```bash
cd /path/to/OGScope
chmod +x scripts/uninstall.sh

# Interactive: type YES when prompted
./scripts/uninstall.sh

# Non-interactive
OGSCOPE_UNINSTALL_CONFIRM=1 ./scripts/uninstall.sh

# Remove service only, keep venv
OGSCOPE_UNINSTALL_CONFIRM=1 OGSCOPE_UNINSTALL_KEEP_VENV=1 ./scripts/uninstall.sh

# Also remove logs and data (use with care)
OGSCOPE_UNINSTALL_CONFIRM=1 OGSCOPE_UNINSTALL_REMOVE_DATA=1 ./scripts/uninstall.sh
```

To deploy again after uninstall, run `./scripts/install.sh`.

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

## 9. API Documentation and Interactive Debugging

### 9.1 Documentation Endpoints

Once the service is running, FastAPI provides interactive API documentation automatically:

| URL | Description |
|-----|-------------|
| `http://<host>:8000/docs` | Swagger UI — interactive API testing |
| `http://<host>:8000/redoc` | ReDoc — structured API documentation |
| `http://<host>:8000/openapi.json` | OpenAPI Schema (JSON) |

### 9.2 API Grouping (Tags)

All endpoints are grouped by module in the documentation. Grouping is controlled via the `tags` parameter during router registration:

| Group | Module | Description |
|-------|--------|-------------|
| Camera - 相机 | `ogscope.web.api.camera` | Camera control and image capture |
| Alignment - 极轴校准 | `ogscope.web.api.alignment` | Polar alignment workflow and status |
| System - 系统 | `ogscope.web.api.system` | System information and configuration |
| Debug - 调试 | `ogscope.web.api.debug` | Debug console endpoints |

Tags are specified in `ogscope/web/api/main.py` via the `tags` parameter of `include_router()`. Group descriptions are defined in the `openapi_tags` list in `ogscope/web/app.py`.

### 9.3 Adding Documentation for New API Modules

When adding a new API module, update two files to ensure proper documentation grouping:

1. **`ogscope/web/app.py`** — add a group description to the `openapi_tags` list:

```python
{
    "name": "NewModule - 新模块",
    "description": "Module description / 模块说明",
},
```

2. **`ogscope/web/api/main.py`** — specify `tags` when registering the router:

```python
router.include_router(new_router, tags=["NewModule - 新模块"])
```

### 9.4 Custom ReDoc Configuration

The project uses a custom ReDoc route with a pinned version (`redoc@2.1.5`) instead of FastAPI's default `redoc@next`, to avoid blank pages caused by unstable pre-release builds. See the `custom_redoc()` function in `ogscope/web/app.py`.

## 10. Troubleshooting Checklist

If service fails to start, check:

- `WorkingDirectory` points to project root
- `ExecStart` uses correct venv Python
- `PYTHONPATH` includes system `dist-packages`
- `LD_LIBRARY_PATH` includes `libcamera` library path
- code upload is complete and dependencies are installed
- **`No module named 'scipy'`**: `board-update.sh` / `install.sh` verify imports after `poetry install` and retry with `--no-cache` plus a pip fallback; if it still fails, remove `.venv` and run `OGSCOPE_MIRROR=cn ./scripts/board-update.sh` (or `./scripts/install.sh`)

## 11. Command Cheatsheet

```bash
# dev machine; on board use ./scripts/board-update.sh
poetry install
poetry run python -m ogscope.main
sudo systemctl restart ogscope
sudo systemctl status ogscope
sudo journalctl -u ogscope -f

# Uninstall service and .venv (see §6.3; requires confirm or OGSCOPE_UNINSTALL_CONFIRM=1)
# ./scripts/uninstall.sh
# OGSCOPE_UNINSTALL_CONFIRM=1 ./scripts/uninstall.sh
```
