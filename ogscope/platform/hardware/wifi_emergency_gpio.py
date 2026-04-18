"""
WiFi 应急 GPIO 监控：短接 2s 强制切回 STA
WiFi emergency GPIO watcher: short pins to force STA.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from loguru import logger

from ogscope.config import Settings, get_settings
from ogscope.hardware.wifi_switch import wifi_switch_service
from ogscope.utils.environment import is_raspberry_pi


@dataclass
class _WatcherState:
    low_since: float | None = None
    last_trigger_at: float = 0.0


class WifiEmergencyGpioMonitor:
    """应急 GPIO 监控器 / Emergency GPIO monitor."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._gpio = None
        self._state = _WatcherState()

    def start(self) -> None:
        """启动监控线程 / Start monitor thread."""
        if not self._settings.wifi_emergency_gpio_enabled:
            logger.info("应急 GPIO 未启用 / Emergency GPIO disabled by config")
            return
        if self._thread and self._thread.is_alive():
            return
        if not is_raspberry_pi():
            logger.info("非树莓派环境，跳过应急 GPIO / Skip emergency GPIO on non-RPi")
            return
        try:
            import RPi.GPIO as gpio  # type: ignore
        except Exception as e:
            logger.warning(
                "未安装 RPi.GPIO，无法启用应急短接 / RPi.GPIO unavailable: {}", e
            )
            return

        self._gpio = gpio
        self._setup_gpio()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="wifi-emergency-gpio",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "应急 GPIO 已启动 / Emergency GPIO monitor started: out={}, in={}, hold={}s",
            self._settings.wifi_emergency_pin_out_bcm,
            self._settings.wifi_emergency_pin_in_bcm,
            self._settings.wifi_emergency_hold_seconds,
        )

    def stop(self) -> None:
        """停止监控线程并释放 GPIO / Stop monitor and cleanup GPIO."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        if self._gpio:
            try:
                self._gpio.cleanup(
                    [
                        self._settings.wifi_emergency_pin_out_bcm,
                        self._settings.wifi_emergency_pin_in_bcm,
                    ]
                )
            except Exception:
                pass
        self._gpio = None
        logger.info("应急 GPIO 已停止 / Emergency GPIO monitor stopped")

    def _setup_gpio(self) -> None:
        assert self._gpio is not None
        g = self._gpio
        g.setwarnings(False)
        g.setmode(g.BCM)
        g.setup(self._settings.wifi_emergency_pin_out_bcm, g.OUT, initial=g.LOW)
        g.setup(self._settings.wifi_emergency_pin_in_bcm, g.IN, pull_up_down=g.PUD_UP)

    def _run_loop(self) -> None:
        assert self._gpio is not None
        g = self._gpio
        interval = 0.05
        hold = self._settings.wifi_emergency_hold_seconds
        while not self._stop_event.is_set():
            now = time.monotonic()
            pin_low = g.input(self._settings.wifi_emergency_pin_in_bcm) == g.LOW
            if pin_low:
                if self._state.low_since is None:
                    self._state.low_since = now
                if (now - self._state.low_since) >= hold:
                    if (now - self._state.last_trigger_at) >= hold:
                        self._state.last_trigger_at = now
                        self._force_sta()
            else:
                self._state.low_since = None
            time.sleep(interval)

    def _force_sta(self) -> None:
        logger.warning(
            "检测到应急短接，强制切换 STA / Emergency short detected, forcing STA"
        )
        if not wifi_switch_service.is_configured():
            logger.error(
                "WiFi 未配置，无法应急切 STA / WiFi not configured, cannot force STA"
            )
            return
        try:
            wifi_switch_service.switch("sta")
        except Exception as e:
            logger.error("应急切 STA 失败 / Failed to force STA: {}", e)


wifi_emergency_gpio_monitor = WifiEmergencyGpioMonitor()
