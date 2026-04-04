"""
NetworkManager（nmcli）操作与 STA 回滚监视 / nmcli helpers and STA rollback watcher.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any

from loguru import logger

from ogscope.config import Settings, get_settings
from ogscope.hardware.wifi_switch import wifi_switch_service

_nm_lock = threading.Lock()


def _nm_executable() -> str:
    """nmcli 绝对路径或回退名 / Resolved nmcli path."""
    return shutil.which("nmcli") or "nmcli"


def _run_nm(args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """执行 nmcli；非 root 时默认 sudo -n，避免 polkit Not authorized / Run nmcli; sudo when needed."""
    s = get_settings()
    if s.wifi_nmcli_use_sudo and os.geteuid() != 0:
        cmd = ["sudo", "-n", _nm_executable(), *args]
    else:
        cmd = [_nm_executable(), *args]
    with _nm_lock:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )


def nmcli_rescan(iface: str) -> None:
    """触发 WiFi 重扫 / Trigger WiFi rescan."""
    try:
        _run_nm(["device", "wifi", "rescan", "ifname", iface], timeout=30)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("nmcli rescan 失败 / rescan failed: {}", e)


def _parse_nmcli_wifi_tab(stdout: str) -> list[dict[str, Any]]:
    networks: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("ssid"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        ssid = parts[0].strip()
        if not ssid or ssid == "--":
            continue
        sig: int | None = None
        try:
            if len(parts) > 1 and parts[1].strip():
                sig = int(parts[1].strip())
        except ValueError:
            pass
        sec = parts[2].strip() if len(parts) > 2 else ""
        networks.append(
            {"ssid": ssid, "signal": sig, "security": sec or None},
        )
    return networks


def _parse_nmcli_wifi_colon(stdout: str) -> list[dict[str, Any]]:
    """-t 模式用冒号分隔；SSID 若含冒号则从右侧取两段 / Colon mode; rsplit for SSID with colons."""
    networks: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.rsplit(":", 2)
        if len(parts) < 3:
            continue
        ssid, sig_s, sec = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not ssid or ssid == "--":
            continue
        sig: int | None = None
        try:
            sig = int(sig_s)
        except ValueError:
            pass
        networks.append({"ssid": ssid, "signal": sig, "security": sec or None})
    return networks


def _device_active_connection_name(iface: str) -> str:
    """当前接口活动连接名 / Active connection name on iface."""
    proc = _run_nm(
        ["-t", "-f", "GENERAL.CONNECTION", "device", "show", iface], timeout=15
    )
    if proc.returncode != 0:
        return ""
    line = (proc.stdout or "").strip().split("\n", 1)[0].strip()
    return line if line and line != "--" else ""


def _merge_networks_by_ssid(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同名 SSID 保留信号最强的一条 / Keep strongest signal per SSID."""
    best: dict[str, dict[str, Any]] = {}
    for n in rows:
        ssid = n.get("ssid") or ""
        if not ssid:
            continue
        prev = best.get(ssid)
        if prev is None:
            best[ssid] = n
            continue
        s_new = n.get("signal")
        s_old = prev.get("signal")
        if isinstance(s_new, int) and (not isinstance(s_old, int) or s_new > s_old):
            best[ssid] = n
    return list(best.values())


def _wifi_list_one(
    iface: str | None,
    *,
    prefer_tab: bool,
) -> tuple[list[dict[str, Any]], int, str]:
    """单次 list；返回 (解析结果, returncode, stderr) / Single list parse."""
    base_tab = ["-m", "tab", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"]
    base_t = ["-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"]
    if iface:
        args_tab = [*base_tab, "ifname", iface]
        args_t = [*base_t, "ifname", iface]
    else:
        args_tab = base_tab
        args_t = base_t
    if prefer_tab:
        proc = _run_nm(args_tab, timeout=60)
        if proc.returncode == 0 and (proc.stdout or "").strip():
            return (
                _parse_nmcli_wifi_tab(proc.stdout or ""),
                proc.returncode,
                proc.stderr or "",
            )
        proc2 = _run_nm(args_t, timeout=60)
        if proc2.returncode == 0:
            return (
                _parse_nmcli_wifi_colon(proc2.stdout or ""),
                proc2.returncode,
                proc2.stderr or "",
            )
        logger.debug(
            "nmcli wifi list(tab+t) iface={} rc={} / {}",
            iface,
            proc2.returncode,
            proc2.stderr,
        )
        return [], proc2.returncode, proc2.stderr or ""
    proc = _run_nm(args_t, timeout=60)
    if proc.returncode == 0:
        return (
            _parse_nmcli_wifi_colon(proc.stdout or ""),
            proc.returncode,
            proc.stderr or "",
        )
    return [], proc.returncode, proc.stderr or ""


def nmcli_wifi_scan(iface: str) -> tuple[list[dict[str, Any]], str | None]:
    """扫描可见 AP；返回 (列表, 可选提示) / List APs; returns (list, optional hint)."""
    settings = get_settings()
    last_err = ""
    networks: list[dict[str, Any]] = []
    ap_name = settings.wifi_ap_connection
    active = _device_active_connection_name(iface)
    ap_mode = bool(ap_name and active == ap_name)

    for attempt in range(1, 3):
        nmcli_rescan(iface)
        time.sleep(1.5 if attempt == 1 else 2.5)
        for use_iface in (iface, None):
            nets, rc, err = _wifi_list_one(use_iface, prefer_tab=True)
            last_err = err or last_err
            if nets:
                networks = _merge_networks_by_ssid(nets)
                networks.sort(
                    key=lambda x: (-(x.get("signal") or -1000), x.get("ssid") or "")
                )
                return networks, None
            if rc != 0 and err:
                logger.warning(
                    "nmcli wifi list 失败 attempt={} iface={!r} / failed: {}",
                    attempt,
                    use_iface,
                    err,
                )
        time.sleep(1.0)

    hint: str | None = None
    if ap_mode:
        hint = (
            "当前为热点(AP)模式：单频网卡通常无法同时列出周边 WiFi。"
            "请用下方「手动输入 SSID」连接；或先切到 STA 再试扫描（视驱动而定）。"
        )
    elif not networks:
        hint = (
            "未扫描到网络。请稍后重试、检查天线/区域码，"
            "或查看日志中 nmcli 错误。"
            + (f" 末次: {last_err.strip()[:200]}" if last_err.strip() else "")
        )
    return networks, hint


def _connection_mode(name: str) -> str:
    proc = _run_nm(
        ["-g", "802-11-wireless.mode", "connection", "show", name], timeout=15
    )
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip().split("\n", 1)[0].strip()


def _connection_ssid(name: str) -> str:
    proc = _run_nm(
        ["-g", "802-11-wireless.ssid", "connection", "show", name], timeout=15
    )
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip().split("\n", 1)[0].strip()


def _connection_autoconnect(name: str) -> bool:
    proc = _run_nm(
        ["-g", "connection.autoconnect", "connection", "show", name], timeout=15
    )
    if proc.returncode != 0:
        return False
    v = (proc.stdout or "").strip().lower()
    return v in {"yes", "true", "1"}


def nmcli_wifi_profiles(settings: Settings) -> list[dict[str, Any]]:
    """列出已保存的 WiFi 连接（不含 AP）/ List saved WiFi connections (exclude AP)."""
    proc = _run_nm(["-t", "-f", "NAME,TYPE", "connection", "show"], timeout=30)
    if proc.returncode != 0:
        return []
    profiles: list[dict[str, Any]] = []
    ap_name = settings.wifi_ap_connection
    for line in (proc.stdout or "").splitlines():
        if ":" not in line:
            continue
        name, typ = line.split(":", 1)
        name = name.strip()
        typ = typ.strip()
        if typ != "802-11-wireless":
            continue
        if name == ap_name:
            continue
        mode = _connection_mode(name)
        if mode == "ap":
            continue
        ssid = _connection_ssid(name)
        profiles.append(
            {
                "connection_name": name,
                "ssid": ssid or name,
                "autoconnect": _connection_autoconnect(name),
            },
        )
    return profiles


def nmcli_modify_sta_to_ssid(
    settings: Settings, ssid: str, password: str | None
) -> None:
    """将 STA 连接改为指定 SSID 与密码 / Point STA profile at SSID (WPA or open)."""
    sta = settings.wifi_sta_connection
    if not sta:
        raise RuntimeError("wifi_sta_connection not configured")
    proc = _run_nm(["connection", "modify", sta, "wifi.ssid", ssid], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "nmcli modify ssid failed")
    if password:
        proc2 = _run_nm(
            [
                "connection",
                "modify",
                sta,
                "wifi-sec.key-mgmt",
                "wpa-psk",
                "wifi-sec.psk",
                password,
            ],
            timeout=30,
        )
        if proc2.returncode != 0:
            raise RuntimeError(
                proc2.stderr or proc2.stdout or "nmcli modify psk failed"
            )
    else:
        proc3 = _run_nm(
            ["connection", "modify", sta, "wifi-sec.key-mgmt", "none"],
            timeout=30,
        )
        if proc3.returncode != 0:
            raise RuntimeError(
                proc3.stderr or proc3.stdout or "nmcli modify open failed"
            )


def nm_down_if_exists(conn_name: str) -> None:
    """尝试 down 连接（忽略未激活）/ Try to bring connection down."""
    proc = _run_nm(["connection", "down", conn_name], timeout=30)
    if proc.returncode != 0:
        logger.debug("connection down {}: {} / {}", conn_name, proc.stdout, proc.stderr)


def nmcli_activate_connection(settings: Settings, connection_name: str) -> None:
    """激活指定连接（STA 用）/ Bring up a saved connection."""
    proc = _run_nm(
        ["connection", "up", connection_name, "ifname", settings.wifi_interface],
        timeout=settings.wifi_switch_timeout_seconds,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "nmcli connection up failed")


def sta_interface_has_usable_ipv4(settings: Settings) -> bool:
    """STA 是否已获得非链路本地 IPv4 / Whether STA has non-link-local IPv4."""
    iface = settings.wifi_interface
    proc = _run_nm(["-g", "IP4.ADDRESS", "device", "show", iface], timeout=15)
    if proc.returncode != 0:
        return False
    text = (proc.stdout or "").strip()
    if not text or text == "--":
        return False
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([\d.]+)/", line)
        if m and not m.group(1).startswith("169.254."):
            return True
    return False


_sta_rollback_task: asyncio.Task[None] | None = None


def cancel_sta_rollback_watch() -> None:
    """取消 STA 回滚任务 / Cancel STA rollback task."""
    global _sta_rollback_task
    if _sta_rollback_task and not _sta_rollback_task.done():
        _sta_rollback_task.cancel()
        logger.info("已取消 STA 回滚监视 / STA rollback watchdog cancelled")
    _sta_rollback_task = None


def schedule_sta_rollback_watch() -> None:
    """STA 切换后启动回滚监视（超时切回 AP）/ Start rollback watchdog after STA switch."""
    global _sta_rollback_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _sta_rollback_task and not _sta_rollback_task.done():
        _sta_rollback_task.cancel()
    _sta_rollback_task = loop.create_task(_sta_rollback_loop())


async def _sta_rollback_loop() -> None:
    settings = get_settings()
    timeout_s = settings.wifi_sta_rollback_timeout_seconds
    interval_s = settings.wifi_sta_rollback_interval_seconds
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    logger.info(
        "STA 回滚监视启动，{}s 内无可用 IPv4 则切回 AP / STA rollback watchdog {}s",
        timeout_s,
        timeout_s,
    )
    try:
        while loop.time() < deadline:
            await asyncio.sleep(interval_s)
            ok = await asyncio.to_thread(sta_interface_has_usable_ipv4, settings)
            if ok:
                logger.info(
                    "STA 回滚监视：已获得 IPv4，停止 / STA watchdog: got IPv4, stop"
                )
                return
        logger.warning(
            "STA 回滚监视：超时，切回 AP / STA watchdog: timeout, switching to AP"
        )
        await asyncio.to_thread(wifi_switch_service.switch, "ap")
    except asyncio.CancelledError:
        logger.info("STA 回滚监视已取消 / STA rollback cancelled")
        raise
    except Exception as e:
        logger.error("STA 回滚失败 / Rollback to AP failed: {}", e)
