# WiFi: STA / AP and NetworkManager

English | [中文](wifi-nm.md)

This document is the **authoritative reference** for OGScope networking on **Raspberry Pi OS**: hotspot/STA passwords and access, `network.env`, sudoers, `/debug/system`, Web APIs, and how **boot-time network bring-up** (`ogscope-network-boot`) differs from **runtime STA rollback** (`wifi_sta_rollback_*`). For the overall **Poetry / `install.sh` / `board-update.sh` flow** on the board, see the [Development Guide (quick deployment)](README_EN.md) **§0.2** and **§0.5**. Below: **user guide → init → environment → sudoers → API → verification**.

## User guide (passwords, access, security)

Information for **end users / field operators**; technical details follow in later sections.

### Default hotspot (AP mode)

| Item | Description |
|------|-------------|
| **SSID** | `OGScope_xxxx` where `xxxx` is the **last 4 hex digits of wlan0 MAC** (lowercase), unique per device. Confirm on the device label or in logs / `diag` after `init`. |
| **Password (PSK)** | Fixed **`ogscopeadmin`** (written to NetworkManager by [`ogscope-network-init.sh`](../../scripts/ogscope-network-init.sh), **not random**). |
| **Gateway / address** | In hotspot mode the wireless side is usually **`192.168.4.1/24`**; NM profile `OGScope-AP` uses **`ipv4.method shared`** (dnsmasq DHCP) so clients do not get stuck with **169.254.x.x** only and cannot reach the gateway. |
| **Web access** | After joining the hotspot, open **`http://192.168.4.1:<port>`**; HTTP port follows OGScope config on the device (often **8000**, see app or `ogscope` service environment). |
| **mDNS hostname** | After init, hostname looks like **`ogscope-xxxx`** (`xxxx` matches SSID suffix). On the LAN try **`http://ogscope-xxxx.local:<port>/debug/system`** (requires **Avahi** and working DNS). |

### Connecting to a home router (STA mode)

1. Join the OGScope hotspot and open **`/debug/system`** (system debug page).
2. Use **“Scan WiFi”** (runs `nmcli` on the device; list may be empty, see below) or **manual SSID + password**.
3. After submit, the device switches to STA; if no LAN IPv4 before the timeout, it **falls back to AP** to avoid total loss of access.

**Note**: The browser **cannot** read WiFi lists from your phone; lists must come from **NetworkManager on the Raspberry Pi**, or you **type SSID/password manually**.

### Saved WiFi list and “Activate”

- **Purpose**: Lists **saved WiFi connections** in NetworkManager (excluding hotspot `OGScope-AP`). **“Activate”** runs `nmcli connection up` on that profile **without** the hotspot script path—useful for networks already saved with credentials.
- **Difference from “manual / scan then connect”**: The latter updates **`OGScope-STA`** SSID/password then switches STA; “Activate” is for **other named connections** (if any).
- **Error `Not authorized to control networking`**: The service user (e.g. `ogstartech`) is blocked by **polkit** from `nmcli connection up`. Init writes **`/etc/sudoers.d/ogscope-nmcli`** so that user may run **`nmcli`** without a password; the app uses **`sudo -n`** (see `OGSCOPE_WIFI_NMCLI_USE_SUDO`, default on). If it still fails, run  
  `sudo ./scripts/ogscope-network-init.sh ensure-systemd` (refreshes `ogscope-nmcli` sudoers) or add manually per **§3**, then **`sudo systemctl restart ogscope`**.

### Important notes (required reading)

1. **Default hotspot password is public** (`ogscopeadmin`)—suitable for field debug and closed environments only. For long-term exposure, change **`OGScope-AP`** PSK in NetworkManager and record it; sync with operators.
2. **Single-radio cards in AP mode** often **cannot list neighboring BSSIDs** (scan may show 0); **enter SSID/password manually**.
3. **After STA→AP or network change**, the browser session may drop; reconnect to hotspot `OGScope_xxxx` or find the device via **mDNS / router admin**.
4. **HTTPS pages cannot mix with HTTP APIs**: pure HTTPS entry points may block **`/health` LAN probes**; prefer **HTTP** on the same LAN for debug pages (see on-page hints).
5. After code updates, if WiFi misbehaves, sync **`ogscope-wifi-switch`** to `/usr/local/bin` and **restart `ogscope`** (see “Verify nmcli” below and `board-update.sh`).
6. **Client only has 169.254.x.x on hotspot**: often old **`OGScope-AP`** with `ipv4.method manual` and no DHCP. Sync latest `ogscope-network-init.sh` and run **`sudo ./scripts/ogscope-network-init.sh init --yes`** (reuse suffix, rebuild NM); or adjust:  
   `sudo nmcli connection modify OGScope-AP wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp ipv4.method shared ipv4.addresses 192.168.4.1/24`, then `sudo nmcli connection down OGScope-AP && sudo nmcli connection up OGScope-AP` (interface usually `wlan0`).

### Security and privacy (brief)

- **`/etc/ogscope/network.env`** holds connection names and device suffix; mode **600**, do not commit.
- **sudoers**: Only **`/usr/local/bin/ogscope-wifi-switch`** and **`nmcli` absolute path** (`/etc/sudoers.d/ogscope-wifi`, `ogscope-nmcli`); never use blanket `NOPASSWD: ALL`.
- Do not leave AP exposed on untrusted networks long-term; production should use router ACLs, strong passwords, and firmware updates.

---

## 1. Recommended: one-shot init (`ogscope-network-init.sh`)

Full **`install.sh` behavior and optional env** summary: [Development Guide §0.2](README_EN.md#02-first-time-install).

The install script [scripts/install.sh](../../scripts/install.sh) installs `network-manager`, `avahi-daemon`, and runs:

```bash
sudo env OGSCOPE_SERVICE_USER="$USER" ./scripts/ogscope-network-init.sh init --yes
```

- Derives hotspot SSID from **last 4 hex digits of wlan0 MAC**: `OGScope_xxxx`, password **`ogscopeadmin`**.
- Creates NM profiles **`OGScope-STA`** (placeholder for Web SSID/password) and **`OGScope-AP`** (`192.168.4.1/24`, `ipv4.method shared`, WPA2-only).
- Writes **`/etc/ogscope/network.env`** (for systemd `EnvironmentFile`).
- Installs **`/usr/local/bin/ogscope-wifi-switch`** and **sudoers** (passwordless script; plus **`ogscope-nmcli`** for Web **`nmcli`**, avoiding polkit denial).
- Sets hostname **`ogscope-xxxx`** and **`/etc/hosts`** `127.0.1.1` (reduces `sudo: unable to resolve host`).
- Writes **systemd drop-in** `/etc/systemd/system/ogscope.service.d/ogscope-network-env.conf` so **`ogscope` loads `/etc/ogscope/network.env`** (matches newer [`install.sh`](../../scripts/install.sh); **deployments that never had this line** may have seen `wifi_not_configured` in Web/API).
- Enables **`http://ogscope-xxxx.local:<port>`** (with Avahi).
- **[`install.sh`](../../scripts/install.sh)** also installs **`ogscope-network-boot.service`** (**root**, `Type=oneshot`, `Before=ogscope.service`), running [`scripts/ogscope-network-boot.sh`](../../scripts/ogscope-network-boot.sh): on boot, if **default IPv4 route is already on a non-wireless interface** (e.g. Ethernet), **skip**; otherwise within **`OGSCOPE_BOOT_STA_WAIT_SEC`** (default 55s) poll whether **`wlan0` has a non-169.254 IPv4** (same semantics as Python `sta_interface_has_usable_ipv4`); if not, try **`nmcli connection up` STA** (retries from **`OGSCOPE_BOOT_STA_UP_RETRIES`** etc.), then **bring up AP** if still failing—avoids cold boot with no network. Skip unit: `OGSCOPE_SKIP_NETWORK_BOOT=1 ./scripts/install.sh`. Logs: `journalctl -u ogscope-network-boot -b`.
- **Difference from in-process STA rollback**: **Boot bring-up** does not depend on the `ogscope` process; in-app **`wifi_sta_rollback_*`** only applies **after** user switches to STA via Web/API and monitors timeout.

Skip init: `OGSCOPE_SKIP_NETWORK_INIT=1 ./scripts/install.sh`

**`init` and SSH**: The script deletes and recreates NetworkManager connections on `wlan0`; **SSH over Wi‑Fi** may drop during `create_nm_connections`—expected. Use **Ethernet**, **serial**, or **local console**, or reconnect to hotspot `OGScope_xxxx` after disconnect.

Diagnostics and reset:

```bash
sudo ./scripts/ogscope-network-init.sh diag
sudo ./scripts/ogscope-network-init.sh ensure-systemd   # systemd drop-in + /etc/hosts 127.0.1.1 (needs existing network.env)
sudo ./scripts/ensure-ogscope-systemd-network-env.sh
sudo ./scripts/ogscope-network-init.sh reset   # interactive
sudo ./scripts/ogscope-network-init.sh reset --yes
```

### Older deployments missing WiFi or systemd env load

1. If **`/etc/ogscope/network.env` exists** but UI still shows **`wifi_not_configured`**: run  
   `sudo ./scripts/ogscope-network-init.sh ensure-systemd`, then **`sudo systemctl restart ogscope`**.  
   (`diag` checks `systemctl cat ogscope` for `EnvironmentFile` pointing to `network.env`.)
2. If `network.env` was never created, run full **`init`**.
3. If **`/etc/hosts`** was not updated with hostname, `sudo` may show `unable to resolve host`; re-run **`init`** to set `127.0.1.1 ogscope-xxxx`, or edit `/etc/hosts` manually.

## 2. Environment variables (`/etc/ogscope/network.env` or `.env`)

Aligned with `OGSCOPE_` keys in [ogscope/config.py](../../ogscope/config.py):

| Variable | Meaning |
|----------|---------|
| `OGSCOPE_WIFI_STA_CONNECTION` | STA profile name (default `OGScope-STA`) |
| `OGSCOPE_WIFI_AP_CONNECTION` | AP profile name (default `OGScope-AP`) |
| `OGSCOPE_WIFI_INTERFACE` | Wireless interface, default `wlan0` |
| `OGSCOPE_DEVICE_ID_SUFFIX` | 4 hex digit suffix (matches hotspot SSID) |
| `OGSCOPE_WIFI_AP_SSID` | Full hotspot SSID (e.g. `OGScope_a1b2`) |
| `OGSCOPE_WIFI_NMCLI_USE_SUDO` | Default `true`: non-root uses `sudo -n nmcli`; requires **`ogscope-nmcli` sudoers** |

## 3. Manual install of switch script and sudoers

```bash
sudo install -m 755 scripts/ogscope-wifi-switch.sh /usr/local/bin/ogscope-wifi-switch
sudo visudo -f /etc/sudoers.d/ogscope-wifi
# Web scan / activate saved WiFi needs passwordless nmcli (path from which):
# sudo visudo -f /etc/sudoers.d/ogscope-nmcli
```

Example:

```
ogstartech ALL=(ALL) NOPASSWD: /usr/local/bin/ogscope-wifi-switch
```

`nmcli` (same as auto-generated by `init`, `which nmcli` is often `/usr/bin/nmcli`):

```
ogstartech ALL=(ALL) NOPASSWD: /usr/bin/nmcli
```

## 4. Web API and STA rollback

- `GET /api/network/wifi/scan`: runs `nmcli` scan on the device (**browsers cannot scan WiFi**—no Web API for that). Response `networks` may be empty; in AP mode with empty list, a hint explains single-radio limitation.
- `POST /api/network/wifi/sta/connect`: switch to STA with SSID/password; if no usable IPv4 within **`wifi_sta_rollback_timeout_seconds`**, **fall back to AP** to avoid bricking remote access.
- `GET /api/network/wifi/profiles`: saved WiFi connections (NetworkManager persistence).
- `POST /api/network/wifi/profile/activate`: **activate** a saved profile (`nmcli connection up`); needs **`ogscope-nmcli` sudoers** or polkit, else **Not authorized**.
- System debug page: `/debug/system` (hints for bring-up, mDNS, LAN `/health` probe).
- **`OGSCOPE_WIFI_NMCLI_USE_SUDO`** (default `true`): set `false` only if the runtime user is allowed by polkit to control NM without sudo.

## 5. Verify nmcli

```bash
sudo /usr/local/bin/ogscope-wifi-switch status
sudo /usr/local/bin/ogscope-wifi-switch ap
sudo /usr/local/bin/ogscope-wifi-switch sta
```

The script **`source`s `/etc/ogscope/network.env`** when the environment is not inherited (same as systemd). If you still use `sudo -E`, some sudoers deny **preserving environment**—omit `-E`.
