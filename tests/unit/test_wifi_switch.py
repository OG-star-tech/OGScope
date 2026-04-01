"""
WiFi 切换服务与 API 单元测试 / Unit tests for WiFi switch service and API.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ogscope.config import Settings
from ogscope.hardware.wifi_switch import WifiSwitchService, _parse_status_output


@pytest.mark.unit
def test_parse_status_output() -> None:
    """解析脚本状态输出 / Parse key=value status output."""
    text = "\n".join(
        [
            "MODE=ap",
            "ACTIVE_CONNECTION=OGScope-AP",
            "WIRELESS_INTERFACE=wlan0",
            "AP_IPV4=192.168.4.1/24",
        ]
    )
    data = _parse_status_output(text)
    assert data["MODE"] == "ap"
    assert data["ACTIVE_CONNECTION"] == "OGScope-AP"
    assert data["AP_IPV4"] == "192.168.4.1/24"


@pytest.mark.unit
def test_wifi_service_not_configured(tmp_path: Path) -> None:
    """未配置时返回 unknown / Return unknown when not configured."""
    settings = Settings(
        wifi_sta_connection="",
        wifi_ap_connection="",
        wifi_switch_script=tmp_path / "missing-script",
    )
    service = WifiSwitchService(settings)
    assert service.is_configured() is False
    status = service.get_status()
    assert status["MODE"] == "unknown"
    assert status["error"] == "wifi_not_configured"


@pytest.mark.unit
def test_wifi_service_status_and_switch(monkeypatch, tmp_path: Path) -> None:
    """配置后可执行 status/switch / Run status and switch when configured."""
    script = tmp_path / "ogscope-wifi-switch"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    settings = Settings(
        wifi_sta_connection="HOME-STA",
        wifi_ap_connection="OGScope-AP",
        wifi_switch_script=script,
        wifi_switch_use_sudo=False,
        wifi_interface="wlan0",
    )
    service = WifiSwitchService(settings)

    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[-1] == "status":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="\n".join(
                    [
                        "MODE=sta",
                        "ACTIVE_CONNECTION=HOME-STA",
                        "WIRELESS_INTERFACE=wlan0",
                        "STA_CONNECTION=HOME-STA",
                        "AP_CONNECTION=OGScope-AP",
                    ]
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    status = service.get_status()
    assert status["MODE"] == "sta"
    service.switch("ap")
    service.switch("sta")
    assert calls[0][-1] == "status"
    assert calls[1][-1] == "ap"
    assert calls[2][-1] == "sta"


@pytest.mark.unit
def test_network_api(client, monkeypatch) -> None:
    """网络 API 状态与切换 / Network API status and switch."""
    from ogscope.web.api.network import routes as network_routes

    monkeypatch.setattr(network_routes.wifi_switch_service, "is_configured", lambda: True)
    monkeypatch.setattr(
        network_routes.wifi_switch_service,
        "get_status",
        lambda: {
            "MODE": "ap",
            "ACTIVE_CONNECTION": "OGScope-AP",
            "WIRELESS_INTERFACE": "wlan0",
            "STA_CONNECTION": "HOME-STA",
            "AP_CONNECTION": "OGScope-AP",
            "AP_IPV4": "192.168.4.1/24",
        },
    )
    monkeypatch.setattr(network_routes.wifi_switch_service, "switch", lambda mode: None)

    response = client.get("/api/network/wifi")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "ap"
    assert data["active_connection"] == "OGScope-AP"

    response2 = client.post("/api/network/wifi", json={"mode": "sta"})
    assert response2.status_code == 200
