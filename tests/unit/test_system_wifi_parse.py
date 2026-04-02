"""WiFi 指标解析：/proc/net/wireless 列顺序 / WiFi metrics column order."""

from pathlib import Path

import pytest

from ogscope.web.api.system import services as system_services
from ogscope.web.api.system.services import SystemInfoService

_WIRELESS_SAMPLE = """Inter-| sta-|   Quality        |   Discarded packets
 face | tus | link level noise |  nwid  crypt   frag
 wlan0: 0000   45.  -50.  -256        0      0      0
"""


@pytest.mark.unit
def test_read_wifi_metrics_link_not_status_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """第一列为 status(0000)，link 在 values[1] / First column is status, not link quality."""
    real_path = Path

    def path_new(arg: str) -> object:
        if arg == "/proc/net/wireless":

            class _W:
                def exists(self) -> bool:
                    return True

                def read_text(self, encoding: str | None = None) -> str:
                    return _WIRELESS_SAMPLE

            return _W()
        return real_path(arg)

    monkeypatch.setattr(system_services, "Path", path_new)
    svc = SystemInfoService(cache_ttl_seconds=0.0)
    q, sig, iface = svc._read_wifi_metrics()
    assert iface == "wlan0"
    assert sig == -50.0
    assert q is not None
    assert abs(float(q) - (45.0 / 70.0) * 100.0) < 0.01
