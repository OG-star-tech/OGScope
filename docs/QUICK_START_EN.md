# OGScope Quick Start Guide

English | [中文](QUICK_START.md)

Use this guide for a first installation and basic validation on a Raspberry Pi Zero 2W. See the [Development Guide](development/README_EN.md) for all installer options, WiFi, low-memory tuning, and routine updates.

## 1. Prepare

### Hardware

- Raspberry Pi Zero 2W
- IMX327 MIPI camera
- 32 GB or larger MicroSD card
- Stable 5 V / 2 A or better power supply

### Software

- Raspberry Pi OS Lite 64-bit (Debian/apt based)
- Python 3.10+
- Git
- Access to apt, PyPI, and GitHub during first installation

Use Raspberry Pi Imager to configure the hostname, SSH, public key, and initial user. Do not rely on historical default usernames or passwords.

## 2. Connect to the board

```bash
ssh <user>@raspberrypi.local
# Use the router-assigned IP when mDNS is unavailable
ssh <user>@<board-ip>
```

Public-key authentication is recommended:

```bash
ssh-copy-id <user>@<board-ip>
ssh -o BatchMode=yes <user>@<board-ip> true
```

## 3. Clone and install

```bash
git clone https://github.com/OG-star-tech/OGScope.git
cd OGScope
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

`bootstrap.sh` deploys the runtime tree to `/opt/ogscope` by default, then creates the project virtual environment, installs system dependencies, and registers `ogscope.service`.

For mainland China mirrors:

```bash
export OGSCOPE_MIRROR=cn
./scripts/bootstrap.sh
```

For the minimal runtime:

```bash
OGSCOPE_BOOTSTRAP_MODE=min ./scripts/bootstrap.sh
```

When the source already resides in the target runtime directory, you can run:

```bash
./scripts/install.sh
```

## 4. Verify

```bash
sudo systemctl status ogscope --no-pager
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/core/v1/system/status
```

Open:

- Home: `http://<board-ip>:8000/`
- Debug console: `http://<board-ip>:8000/debug`
- API documentation: `http://<board-ip>:8000/docs`

Camera checks:

```bash
rpicam-hello --list-cameras 2>/dev/null || libcamera-hello --list-cameras
curl -fsS http://127.0.0.1:8000/api/core/v1/camera/status
```

`POST /api/core/v1/camera/start` succeeds only after the camera confirms both `connected=true` and `streaming=true`.

## 5. Routine updates

```bash
cd /opt/ogscope
./scripts/board-update.sh
```

To install development dependencies:

```bash
OGSCOPE_INSTALL_DEV=1 ./scripts/board-update.sh
```

## 6. Local development

```bash
poetry install
poetry run pytest -q

cd web/spa
npm ci
npm run build
```

Changes involving the camera, GPIO, I2C, or systemd must be revalidated on real hardware. See the [Development Guide](development/README_EN.md) and `scripts/sync_dev_board.sh` for board synchronization.

## 7. Troubleshooting

### Service does not start

```bash
sudo journalctl -u ogscope -b --no-pager -n 200
sudo systemctl cat ogscope
```

### Camera is unavailable

```bash
rpicam-hello --list-cameras 2>/dev/null || libcamera-hello --list-cameras
sudo journalctl -u ogscope -b --no-pager | grep -i -E 'camera|libcamera|imx327'
```

Check the camera overlay, ribbon orientation, and `/boot/firmware/config.txt` before rebooting.

### Network or hotspot problems

Follow the [WiFi / NetworkManager Guide](development/wifi-nm_EN.md). Do not run multiple network initialization stacks at the same time.

## 8. Next documents

- [Documentation index](README_EN.md) | [中文](README.md)
- [Development Guide](development/README_EN.md) | [中文](development/README.md)
- [Core REST v1 contract](contracts/core-rest-v1_EN.md) | [中文](contracts/core-rest-v1.md)
- [Debug console](DEBUG_CONSOLE_EN.md) | [中文](DEBUG_CONSOLE.md)
- [Issue tracker](https://github.com/OG-star-tech/OGScope/issues)
