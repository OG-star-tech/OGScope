# OGScope board deployment checklist

[中文](DEPLOY.md) | English

Single-page checklist; use together with the [Development Guide](README_EN.md).

## Requirements

- Board: Raspberry Pi / Orange Pi, **ARM** (`aarch64` or `armhf`)
- OS: Debian/apt-based images compatible with `picamera2`/`libcamera`
- Python: **3.10+** (see `pyproject.toml`)
- Network: Poetry downloads on first install; Web UI needs **TCP 8000** reachable (configure firewall as needed)

## First-time install

```bash
cd /path/to/OGScope
chmod +x scripts/install.sh
./scripts/install.sh
```

Notes:

- Default: **`poetry install --only main`**. Set `OGSCOPE_INSTALL_DEV=1` for dev dependencies.
- Low-memory boards: **`OGSCOPE_APT_SLOW=1`** to stagger `apt` installs.
- **Mirrors**: Inside mainland China, run with **`export OGSCOPE_MIRROR=cn`** (Tsinghua mirrors for apt and PyPI). Abroad, use **`auto`** (default) or **`OGSCOPE_MIRROR=international`**.
- After install: `sudo systemctl start ogscope`

## Plate-solve data

Place **`default_database.npz`** under **`data/plate_solve/`** (not shipped in the repo). See [plate-solve-data.md](plate-solve-data.md).

## Routine updates

```bash
cd /path/to/OGScope
chmod +x scripts/board-update.sh
# With git and need pull: OGSCOPE_GIT_PULL=1 ./scripts/board-update.sh
./scripts/board-update.sh
```

## Health check and logs

```bash
curl -s http://127.0.0.1:8000/health
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

## Troubleshooting

- **ImportError: picamera2**: install camera stack via `apt`; venv must be set up by `install.sh` (`system-site-packages` + `PYTHONPATH`).
- **PEP 668**: do not install into system Python; use project `.venv` — see [README_EN §1.2](README_EN.md#12-poetry-pep-668-and-the-virtual-environment-required-reading).
- Service fails: verify `WorkingDirectory`, `ExecStart` points to `.venv` Python, and read `journalctl` errors.
