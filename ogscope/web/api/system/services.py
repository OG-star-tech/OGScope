"""
系统信息服务 / System information service
"""

from __future__ import annotations

import os
import platform
import time
from pathlib import Path
from threading import Lock
from typing import Any


class SystemInfoService:
    """系统信息采集服务（低开销缓存） / System info collector with low-overhead cache."""

    def __init__(self, cache_ttl_seconds: float = 10.0) -> None:
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache_data: dict[str, Any] | None = None
        self._cache_timestamp = 0.0
        self._lock = Lock()
        self._last_cpu_total: int | None = None
        self._last_cpu_idle: int | None = None

    def get_system_info(self) -> dict[str, Any]:
        """获取系统信息 / Get system information."""
        now = time.monotonic()
        with self._lock:
            if (
                self._cache_data is not None
                and (now - self._cache_timestamp) < self._cache_ttl_seconds
            ):
                return self._cache_data

            data = {
                "platform": self._read_platform_name(),
                "os": self._read_os_name(),
                "cpu_usage": round(self._read_cpu_usage_percent(), 2),
                "memory_usage": round(self._read_memory_usage_percent(), 2),
                "temperature": round(self._read_cpu_temperature_celsius(), 2),
                "uptime_seconds": self._read_uptime_seconds(),
                "load_average_1m": round(self._read_load_average_1m(), 2),
            }
            wifi_quality, wifi_signal_dbm, wifi_interface = self._read_wifi_metrics()
            data["wifi_quality"] = wifi_quality
            data["wifi_signal_dbm"] = wifi_signal_dbm
            data["wifi_interface"] = wifi_interface

            self._cache_data = data
            self._cache_timestamp = now
            return data

    def _read_platform_name(self) -> str:
        model_path = Path("/proc/device-tree/model")
        if model_path.exists():
            try:
                return model_path.read_text(encoding="utf-8", errors="ignore").strip(
                    "\x00 \n\t"
                )
            except OSError:
                pass
        return platform.machine() or "Unknown"

    def _read_os_name(self) -> str:
        os_release = Path("/etc/os-release")
        if os_release.exists():
            try:
                for line in os_release.read_text(encoding="utf-8").splitlines():
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
            except OSError:
                pass
        return f"{platform.system()} {platform.release()}".strip()

    def _read_cpu_usage_percent(self) -> float:
        stat_path = Path("/proc/stat")
        if not stat_path.exists():
            try:
                load_1m = self._read_load_average_1m()
                cpu_count = max(1, (os.cpu_count() or 1))
                return min(100.0, max(0.0, (load_1m / cpu_count) * 100.0))
            except (OSError, ValueError):
                return 0.0

        try:
            first_line = stat_path.read_text(encoding="utf-8").splitlines()[0]
            parts = first_line.split()
            if len(parts) < 5 or parts[0] != "cpu":
                return 0.0

            values = [int(value) for value in parts[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            total = sum(values)

            if self._last_cpu_total is None or self._last_cpu_idle is None:
                self._last_cpu_total = total
                self._last_cpu_idle = idle
                return 0.0

            total_delta = total - self._last_cpu_total
            idle_delta = idle - self._last_cpu_idle
            self._last_cpu_total = total
            self._last_cpu_idle = idle

            if total_delta <= 0:
                return 0.0
            usage = (1.0 - (idle_delta / total_delta)) * 100.0
            return min(100.0, max(0.0, usage))
        except (OSError, ValueError, IndexError):
            return 0.0

    def _read_memory_usage_percent(self) -> float:
        meminfo_path = Path("/proc/meminfo")
        if not meminfo_path.exists():
            return 0.0

        total_kb: int | None = None
        available_kb: int | None = None
        try:
            for line in meminfo_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
                if total_kb is not None and available_kb is not None:
                    break
        except (OSError, ValueError):
            return 0.0

        if not total_kb or available_kb is None:
            return 0.0
        used_kb = max(0, total_kb - available_kb)
        return (used_kb / total_kb) * 100.0

    def _read_cpu_temperature_celsius(self) -> float:
        thermal_glob = Path("/sys/class/thermal")
        if thermal_glob.exists():
            for zone in thermal_glob.glob("thermal_zone*/temp"):
                try:
                    raw_value = zone.read_text(encoding="utf-8").strip()
                    temp = float(raw_value)
                    if temp > 1000:
                        return temp / 1000.0
                    if temp > 0:
                        return temp
                except (OSError, ValueError):
                    continue
        return 0.0

    def _read_wifi_metrics(self) -> tuple[float | None, float | None, str | None]:
        wireless_path = Path("/proc/net/wireless")
        if not wireless_path.exists():
            return None, None, None

        try:
            lines = wireless_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None, None, None

        for line in lines[2:]:
            if ":" not in line:
                continue
            interface, values_str = line.split(":", 1)
            values = values_str.split()
            if len(values) < 3:
                continue
            try:
                link_quality = float(values[0].rstrip("."))
                signal_level = float(values[1].rstrip("."))
                quality_percent = max(0.0, min(100.0, (link_quality / 70.0) * 100.0))
                return (
                    round(quality_percent, 2),
                    round(signal_level, 2),
                    interface.strip(),
                )
            except ValueError:
                continue
        return None, None, None

    def _read_uptime_seconds(self) -> int:
        uptime_path = Path("/proc/uptime")
        if not uptime_path.exists():
            return 0
        try:
            text = uptime_path.read_text(encoding="utf-8").strip()
            return int(float(text.split()[0]))
        except (OSError, ValueError, IndexError):
            return 0

    def _read_load_average_1m(self) -> float:
        try:
            return float(os.getloadavg()[0])
        except OSError:
            return 0.0


system_info_service = SystemInfoService()
