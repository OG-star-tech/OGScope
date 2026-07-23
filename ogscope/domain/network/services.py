"""
网络域服务 / Network domain services.
"""

from __future__ import annotations

import asyncio
import subprocess

from ogscope.config import get_settings
from ogscope.domain.network import nmcli_services as net_impl
from ogscope.platform.hardware.wifi_switch import wifi_switch_service


class WifiDomainService:
    """网络域门面 / Network domain facade."""

    @staticmethod
    def build_wifi_status() -> dict:
        settings = get_settings()
        configured = wifi_switch_service.is_configured()
        data = wifi_switch_service.get_status()
        mode = data.get("MODE", "unknown")
        active_connection = data.get("ACTIVE_CONNECTION") or None
        wireless_interface = data.get("WIRELESS_INTERFACE", settings.wifi_interface)
        sta_connection = data.get("STA_CONNECTION", settings.wifi_sta_connection)
        ap_connection = data.get("AP_CONNECTION", settings.wifi_ap_connection)
        ap_ipv4 = data.get("AP_IPV4") or None
        ap_url_hint = (
            f"http://{settings.wifi_ap_url_host}:{settings.port}"
            if mode == "ap"
            else None
        )
        message = data.get("error")
        suffix = settings.device_id_suffix or None
        ap_ssid = settings.wifi_ap_ssid or None
        mdns_hint = f"ogscope-{suffix}.local" if suffix else None
        return {
            "mode": mode if mode in {"ap", "sta"} else "unknown",
            "active_connection": active_connection,
            "wireless_interface": wireless_interface,
            "sta_connection": sta_connection,
            "ap_connection": ap_connection,
            "ap_ipv4": ap_ipv4,
            "ap_url_hint": ap_url_hint,
            "configured": configured,
            "message": message,
            "device_id_suffix": suffix,
            "ap_ssid": ap_ssid,
            "mdns_hostname_hint": mdns_hint,
        }

    async def switch_mode(self, mode: str) -> dict:
        if mode == "ap":
            net_impl.cancel_sta_rollback_watch()
        wifi_switch_service.switch(mode)
        if mode == "sta":
            net_impl.schedule_sta_rollback_watch()
        return self.build_wifi_status()

    async def scan_wifi(self):
        settings = get_settings()
        return await asyncio.to_thread(
            net_impl.nmcli_wifi_scan, settings.wifi_interface
        )

    async def list_profiles(self):
        settings = get_settings()
        return await asyncio.to_thread(net_impl.nmcli_wifi_profiles, settings)

    async def connect_sta(self, ssid: str, password: str) -> dict:
        settings = get_settings()
        if not wifi_switch_service.is_configured():
            raise RuntimeError("wifi_not_configured")
        await asyncio.to_thread(
            net_impl.nmcli_modify_sta_to_ssid, settings, ssid, password
        )
        await asyncio.to_thread(wifi_switch_service.switch, "sta")
        net_impl.schedule_sta_rollback_watch()
        return self.build_wifi_status()

    async def activate_profile(self, connection_name: str) -> dict:
        settings = get_settings()
        if not wifi_switch_service.is_configured():
            raise RuntimeError("wifi_not_configured")
        name = connection_name.strip()
        if not name:
            raise ValueError("empty_connection_name")
        if name == settings.wifi_sta_connection:
            await asyncio.to_thread(wifi_switch_service.switch, "sta")
        else:
            await asyncio.to_thread(
                net_impl.nm_down_if_exists, settings.wifi_ap_connection
            )
            await asyncio.to_thread(net_impl.nmcli_activate_connection, settings, name)
        net_impl.schedule_sta_rollback_watch()
        return self.build_wifi_status()


wifi_domain_service = WifiDomainService()

# 保留 nmcli 辅助函数导出，供现有调用方使用 / Keep helper exports for existing callers.
nmcli_wifi_scan = net_impl.nmcli_wifi_scan
nmcli_wifi_profiles = net_impl.nmcli_wifi_profiles
nmcli_modify_sta_to_ssid = net_impl.nmcli_modify_sta_to_ssid
nm_down_if_exists = net_impl.nm_down_if_exists
nmcli_activate_connection = net_impl.nmcli_activate_connection
schedule_sta_rollback_watch = net_impl.schedule_sta_rollback_watch
cancel_sta_rollback_watch = net_impl.cancel_sta_rollback_watch
TimeoutExpired = subprocess.TimeoutExpired
CalledProcessError = subprocess.CalledProcessError

__all__ = [
    "wifi_domain_service",
    "WifiDomainService",
    "nmcli_wifi_scan",
    "nmcli_wifi_profiles",
    "nmcli_modify_sta_to_ssid",
    "nm_down_if_exists",
    "nmcli_activate_connection",
    "schedule_sta_rollback_watch",
    "cancel_sta_rollback_watch",
    "TimeoutExpired",
    "CalledProcessError",
]
