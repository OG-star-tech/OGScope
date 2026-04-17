"""
网络相关 API 路由（WiFi AP/STA） / Network API routes for WiFi AP/STA.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ogscope.domain.network.services import (
    CalledProcessError,
    TimeoutExpired,
    wifi_domain_service,
)
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

router = APIRouter()


@router.get("/network/wifi", response_model=WifiStatus)
async def get_wifi_status() -> WifiStatus:
    """获取 WiFi 模式状态 / Get WiFi mode status."""
    return wifi_domain_service.build_wifi_status()


@router.post("/network/wifi", response_model=WifiStatus)
async def switch_wifi_mode(payload: WifiModeRequest) -> WifiStatus:
    """切换 WiFi 模式（AP/STA）/ Switch WiFi mode."""
    try:
        return await wifi_domain_service.switch_mode(payload.mode)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except TimeoutExpired as e:
        raise HTTPException(status_code=504, detail=f"wifi_switch_timeout: {e}") from e
    except CalledProcessError as e:
        err = (e.stderr or e.output or str(e)).strip()
        raise HTTPException(status_code=500, detail=f"wifi_switch_failed: {err}") from e


@router.get("/network/wifi/scan", response_model=WifiScanResponse)
async def scan_wifi() -> WifiScanResponse:
    """扫描附近 WiFi（由设备执行 nmcli）/ Scan WiFi (nmcli on device)."""
    try:
        nets, scan_hint = await wifi_domain_service.scan_wifi()
    except TimeoutExpired as e:
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
    try:
        rows = await wifi_domain_service.list_profiles()
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
    try:
        return await wifi_domain_service.connect_sta(payload.ssid, payload.password)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except CalledProcessError as e:
        err = (e.stderr or e.output or str(e)).strip()
        raise HTTPException(status_code=500, detail=f"sta_connect_failed: {err}") from e


@router.post("/network/wifi/profile/activate", response_model=WifiStatus)
async def activate_wifi_profile(payload: WifiProfileActivateRequest) -> WifiStatus:
    """激活已保存连接并切 STA / Activate saved profile (STA)."""
    try:
        return await wifi_domain_service.activate_profile(payload.connection_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except CalledProcessError as e:
        err = (e.stderr or e.output or str(e)).strip()
        raise HTTPException(status_code=500, detail=f"activate_failed: {err}") from e
