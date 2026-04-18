"""
人机交互服务 / HMI service.
"""

from __future__ import annotations

from typing import Any


class HmiService:
    """屏幕/蜂鸣器/RGB/按键服务 / Display, buzzer, RGB and keys service."""

    name = "hmi-service"

    def __init__(self) -> None:
        self._running = False
        self._screen_on = True
        self._buzzer_muted = False
        self._rgb_mode = "idle"

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "screen_on": self._screen_on,
            "buzzer_muted": self._buzzer_muted,
            "rgb_mode": self._rgb_mode,
        }

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
        return {"accepted": False, "message": f"unsupported action: {action}"}

