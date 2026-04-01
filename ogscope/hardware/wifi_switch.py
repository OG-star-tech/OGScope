"""
WiFi 模式切换（调用 ogscope-wifi-switch.sh + nmcli）
WiFi mode switch via external NetworkManager helper script.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Literal

from loguru import logger

from ogscope.config import Settings, get_settings

WifiMode = Literal["ap", "sta", "unknown"]


def _wifi_env(settings: Settings) -> dict[str, str]:
    """合并当前环境与 WiFi 相关 OGSCOPE_* 变量 / Merge env with WiFi OGSCOPE_* vars."""
    env = {k: v for k, v in os.environ.items() if v is not None}
    env["OGSCOPE_WIFI_STA_CONNECTION"] = settings.wifi_sta_connection
    env["OGSCOPE_WIFI_AP_CONNECTION"] = settings.wifi_ap_connection
    env["OGSCOPE_WIFI_INTERFACE"] = settings.wifi_interface
    return env


def _parse_status_output(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


class WifiSwitchService:
    """封装脚本调用 / Script invocation wrapper."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def is_configured(self) -> bool:
        """是否已配置连接名与脚本 / Whether connection names and script are set."""
        s = self._settings
        if not s.wifi_sta_connection or not s.wifi_ap_connection:
            return False
        p = Path(s.wifi_switch_script)
        return p.is_file()

    def get_status(self) -> dict[str, str | None]:
        """执行 status，返回解析后的键值 / Run status subcommand."""
        if not self.is_configured():
            return {
                "MODE": "unknown",
                "error": "wifi_not_configured",
            }
        raw = self._run_script("status", check=False)
        data = _parse_status_output(raw)
        if not data.get("MODE"):
            data["MODE"] = "unknown"
        return data

    def switch(self, mode: Literal["ap", "sta"]) -> None:
        """切换模式；失败抛 subprocess.CalledProcessError / Switch mode."""
        if not self.is_configured():
            raise RuntimeError("wifi_not_configured")
        self._run_script(mode, check=True)

    def _run_script(self, subcommand: str, *, check: bool) -> str:
        s = self._settings
        script = Path(s.wifi_switch_script)
        cmd: list[str] = []
        if s.wifi_switch_use_sudo:
            cmd.extend(["sudo", "-n", "-E", str(script), subcommand])
        else:
            cmd.extend([str(script), subcommand])
        logger.info(
            "WiFi script: {} / Running WiFi script",
            " ".join(shlex.quote(c) for c in cmd),
        )
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=s.wifi_switch_timeout_seconds,
                env=_wifi_env(s),
                check=check,
            )
        except subprocess.TimeoutExpired as e:
            logger.error("WiFi 脚本超时 / WiFi script timeout: {}", e)
            raise
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        combined = "\n".join(x for x in (out, err) if x)
        if err:
            logger.debug("WiFi script stderr / stderr: {}", err)
        if proc.returncode != 0 and check:
            logger.warning(
                "WiFi 脚本失败 rc={} / script failed: {}\n{}",
                proc.returncode,
                out,
                err,
            )
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, output=out, stderr=err
            )
        return combined


wifi_switch_service = WifiSwitchService()
