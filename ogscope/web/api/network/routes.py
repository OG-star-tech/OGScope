"""
网络相关 API 路由（WiFi AP/STA） / Network API routes for WiFi AP/STA.
"""

from __future__ import annotations

import asyncio
import subprocess

from fastapi import APIRouter, HTTPException

from ogscope.config import get_settings
from ogscope.hardware.wifi_switch import wifi_switch_service
from ogscope.web.api.models.schemas import (
    WifiModeRequest,
    WifiNetworkScanEntry,
    WifiProfileActivateRequest,
    WifiProfileEntry,
    WifiProfilesResponse,
    WifiScanResponse,
    WifiStaConnectRequest,
    WifiStatus,
)
from ogscope.domain.network import services as net_services

router = APIRouter()


def _build_wifi_status() -> WifiStatus:
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
        f"http://{settings.wifi_ap_url_host}:{settings.port}" if mode == "ap" else None
    )
    message = data.get("error")
    suffix = settings.device_id_suffix or None
    ap_ssid = settings.wifi_ap_ssid or None
    mdns_hint = f"ogscope-{suffix}.local" if suffix else None
    return WifiStatus(
        mode=mode if mode in {"ap", "sta"} else "unknown",
        active_connection=active_connection,
        wireless_interface=wireless_interface,
        sta_connection=sta_connection,
        ap_connection=ap_connection,
        ap_ipv4=ap_ipv4,
        ap_url_hint=ap_url_hint,
        configured=configured,
        message=message,
        device_id_suffix=suffix,
        ap_ssid=ap_ssid,
        mdns_hostname_hint=mdns_hint,
    )


@router.get("/network/wifi", response_model=WifiStatus)
async def get_wifi_status() -> WifiStatus:
    """获取 WiFi 模式状态 / Get WiFi mode status."""
    return _build_wifi_status()


@router.post("/network/wifi", response_model=WifiStatus)
async def switch_wifi_mode(payload: WifiModeRequest) -> WifiStatus:
    """切换 WiFi 模式（AP/STA）/ Switch WiFi mode."""
    if payload.mode == "ap":
        net_services.cancel_sta_rollback_watch()
    try:
        wifi_switch_service.switch(payload.mode)
        if payload.mode == "sta":
            net_services.schedule_sta_rollback_watch()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail=f"wifi_switch_timeout: {e}") from e
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.output or str(e)).strip()
        raise HTTPException(status_code=500, detail=f"wifi_switch_failed: {err}") from e
    return _build_wifi_status()


@router.get("/network/wifi/scan", response_model=WifiScanResponse)
async def scan_wifi() -> WifiScanResponse:
    """扫描附近 WiFi（由设备执行 nmcli）/ Scan WiFi (nmcli on device)."""
    settings = get_settings()
    try:
        nets, scan_hint = await asyncio.to_thread(
            net_services.nmcli_wifi_scan,
            settings.wifi_interface,
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail=f"wifi_scan_timeout: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return WifiScanResponse(
        networks=[WifiNetworkScanEntry(**n) for n in nets],
        hint=scan_hint,
    )


@router.get("/network/wifi/profiles", response_model=WifiProfilesResponse)
async def list_wifi_profiles() -> WifiProfilesResponse:
    """列出已保存的 WiFi 连接（不含 AP）/ List saved WiFi profiles."""
    settings = get_settings()
    try:
        rows = await asyncio.to_thread(
            net_services.nmcli_wifi_profiles,
            settings,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return WifiProfilesResponse(
        profiles=[
            WifiProfileEntry(
                connection_name=r["connection_name"],
                ssid=r["ssid"],
                autoconnect=r["autoconnect"],
            )
            for r in rows
        ],
    )


@router.post("/network/wifi/sta/connect", response_model=WifiStatus)
async def connect_sta_wifi(payload: WifiStaConnectRequest) -> WifiStatus:
    """配置 STA 并切换到 STA，启动失败回滚监视 / Configure STA and switch, start rollback watch."""
    settings = get_settings()
    if not wifi_switch_service.is_configured():
        raise HTTPException(status_code=503, detail="wifi_not_configured")
    try:
        await asyncio.to_thread(
            net_services.nmcli_modify_sta_to_ssid,
            settings,
            payload.ssid,
            payload.password,
        )
        await asyncio.to_thread(wifi_switch_service.switch, "sta")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.output or str(e)).strip()
        raise HTTPException(status_code=500, detail=f"sta_connect_failed: {err}") from e
    net_services.schedule_sta_rollback_watch()
    return _build_wifi_status()


@router.post("/network/wifi/profile/activate", response_model=WifiStatus)
async def activate_wifi_profile(payload: WifiProfileActivateRequest) -> WifiStatus:
    """激活已保存连接并切 STA / Activate saved profile (STA)."""
    settings = get_settings()
    if not wifi_switch_service.is_configured():
        raise HTTPException(status_code=503, detail="wifi_not_configured")
    name = payload.connection_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="empty_connection_name")
    try:
        if name == settings.wifi_sta_connection:
            await asyncio.to_thread(wifi_switch_service.switch, "sta")
        else:
            await asyncio.to_thread(
                net_services.nm_down_if_exists, settings.wifi_ap_connection
            )
            await asyncio.to_thread(
                net_services.nmcli_activate_connection,
                settings,
                name,
            )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.output or str(e)).strip()
        raise HTTPException(status_code=500, detail=f"activate_failed: {err}") from e
    net_services.schedule_sta_rollback_watch()
    return _build_wifi_status()
