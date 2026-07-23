"""
人机交互服务 / HMI service.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from typing import Any

from ogscope.config import get_settings


class HmiService:
    """屏幕/蜂鸣器/RGB/按键服务 / Display, buzzer, RGB and keys service."""

    name = "hmi-service"

    def __init__(self) -> None:
        self._running = False
        self._screen_on = True
        self._buzzer_muted = False
        self._rgb_mode = "idle"
        self._spi_lock = threading.Lock()
        self._display: Any = None
        self._display_last_error: str | None = None
        self._last_pattern: str | None = None

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        await asyncio.to_thread(self._close_display_sync)

    def _close_display_sync(self) -> None:
        with self._spi_lock:
            if self._display is not None:
                try:
                    self._display.close()
                except Exception:
                    pass
                self._display = None

    async def status(self) -> dict[str, Any]:
        settings = get_settings()
        spi_path = "/dev/spidev0.0"
        return {
            "running": self._running,
            "screen_on": self._screen_on,
            "buzzer_muted": self._buzzer_muted,
            "rgb_mode": self._rgb_mode,
            "display": {
                "enabled": bool(settings.display_enabled),
                "type": settings.display_type,
                "width": int(settings.display_width),
                "height": int(settings.display_height),
                "dc_pin": int(settings.display_dc_pin),
                "spi_max_hz": int(settings.display_spi_max_speed_hz),
                "spidev_present": os.path.exists(spi_path),
                "driver_open": self._display is not None,
                "last_error": self._display_last_error,
                "last_pattern": self._last_pattern,
            },
        }

    def _ensure_display_sync(self) -> Any:
        settings = get_settings()
        if not settings.display_enabled:
            raise RuntimeError(
                "display_disabled：在环境变量或 .env 中设置 OGSCOPE_DISPLAY_ENABLED=true"
            )
        if settings.display_type.lower() != "st7796":
            raise RuntimeError(
                f"unsupported display_type: {settings.display_type!r} (expected st7796)"
            )
        if sys.platform != "linux":
            raise RuntimeError(
                "ST7796 仅支持 Linux（树莓派）/ ST7796 requires Linux (Raspberry Pi)"
            )
        if self._display is not None:
            return self._display
        from ogscope.platform.hardware.st7796_spi import ST7796SPI

        self._display = ST7796SPI(
            dc_pin=int(settings.display_dc_pin),
            width=int(settings.display_width),
            height=int(settings.display_height),
            max_speed_hz=int(settings.display_spi_max_speed_hz),
        )
        self._display_last_error = None
        return self._display

    def _make_pattern_image(self, pattern: str, payload: dict[str, Any]) -> Any:
        from PIL import Image, ImageDraw, ImageFont

        settings = get_settings()
        w, h = int(settings.display_width), int(settings.display_height)
        if pattern == "fill":
            r = int(payload.get("r", 0))
            g = int(payload.get("g", 0))
            b = int(payload.get("b", 255))
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            return Image.new("RGB", (w, h), (r, g, b))
        if pattern == "colorbars":
            im = Image.new("RGB", (w, h))
            draw = ImageDraw.Draw(im)
            colors = [
                (255, 0, 0),
                (255, 128, 0),
                (255, 255, 0),
                (0, 255, 0),
                (0, 255, 255),
                (0, 0, 255),
                (128, 0, 255),
                (255, 255, 255),
            ]
            n = len(colors)
            seg = w / n
            for i, c in enumerate(colors):
                x0 = int(i * seg)
                x1 = int((i + 1) * seg) - 1 if i < n - 1 else w - 1
                draw.rectangle((x0, 0, x1, h - 1), fill=c)
            return im
        # smoke (default)
        im = Image.new("RGB", (w, h), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        draw.rectangle((0, 0, w - 1, h - 1), outline=(200, 200, 200))
        try:
            font = ImageFont.load_default()
        except OSError:
            font = None
        msg = "OGScope\nSPI OK"
        if font:
            draw.multiline_text(
                (8, h // 2 - 20),
                msg,
                fill=(255, 255, 255),
                font=font,
                spacing=4,
            )
        else:
            draw.text((8, h // 2), "OGScope SPI OK", fill=(255, 255, 255))
        return im

    def _draw_pattern_sync(self, pattern: str, payload: dict[str, Any]) -> None:
        if not self._screen_on:
            raise RuntimeError("screen_off：已关闭屏幕输出（先执行 screen.set 打开）")
        with self._spi_lock:
            disp = self._ensure_display_sync()
            im = self._make_pattern_image(pattern, payload)
            disp.show_pil_rgb(im)
            self._last_pattern = pattern
            self._display_last_error = None

    async def command(
        self, action: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = payload or {}
        if action == "screen.set":
            self._screen_on = bool(payload.get("on", True))
            return {"accepted": True, "screen_on": self._screen_on}
        if action == "buzzer.mute":
            self._buzzer_muted = bool(payload.get("mute", True))
            return {"accepted": True, "buzzer_muted": self._buzzer_muted}
        if action == "rgb.set_mode":
            self._rgb_mode = str(payload.get("mode", "idle"))
            return {"accepted": True, "rgb_mode": self._rgb_mode}
        if action == "display.test_pattern":
            pattern = str(payload.get("pattern", "smoke"))
            if pattern not in ("smoke", "fill", "colorbars"):
                return {
                    "accepted": False,
                    "message": f"unknown pattern: {pattern}",
                }
            try:
                await asyncio.to_thread(self._draw_pattern_sync, pattern, payload)
            except Exception as exc:
                self._display_last_error = str(exc)
                return {
                    "accepted": False,
                    "message": str(exc),
                    "pattern": pattern,
                }
            return {"accepted": True, "pattern": pattern}
        if action == "display.release":
            await asyncio.to_thread(self._close_display_sync)
            return {"accepted": True, "driver_open": False}
        return {"accepted": False, "message": f"unsupported action: {action}"}
