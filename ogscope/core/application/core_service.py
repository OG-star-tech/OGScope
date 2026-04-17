"""
Core 标准契约应用服务 / Core standard contract application service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ogscope.__version__ import __version__
from ogscope.config import get_settings
from ogscope.core.capabilities import capability_map
from ogscope.core.realtime import realtime_solve_service
from ogscope.hardware.wifi_switch import wifi_switch_service
from ogscope.web.api.debug.services import DebugCameraService, DebugFileService
from ogscope.web.api.system.services import system_info_service
from ogscope.web.mjpeg_stream_limiter import get_mjpeg_stream_limiter


@dataclass(slots=True)
class CoreAnalysisSession:
    """Core 分析会话状态 / Core analysis session state."""

    session_id: str = "realtime-default"
    running: bool = False


class CoreContractService:
    """OGScope 对上层调用方的稳定契约服务 / Stable OGScope contract for upstream callers."""

    def __init__(self) -> None:
        self._session = CoreAnalysisSession()

    async def start_analysis(
        self,
        *,
        hint_ra_deg: float | None = None,
        hint_dec_deg: float | None = None,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """开始实时分析 / Start realtime analysis."""
        result = await realtime_solve_service.start(
            hint_ra_deg=hint_ra_deg,
            hint_dec_deg=hint_dec_deg,
            fov_estimate=fov_estimate,
            fov_max_error=fov_max_error,
            solve_timeout_ms=solve_timeout_ms,
        )
        self._session.running = True
        return {
            "success": bool(result.get("success", True)),
            "session_id": self._session.session_id,
            "state": "running",
            "message": result.get("message", ""),
        }

    async def get_analysis_result(self) -> dict[str, Any]:
        """获取分析结果 / Get analysis result."""
        status = await realtime_solve_service.get_status()
        running = bool(status.get("running", False))
        last_result = status.get("last_result")
        state = "running" if running else "stopped"
        if not running and last_result:
            state = "completed"
        return {
            "success": True,
            "session_id": self._session.session_id,
            "state": state,
            "result": last_result,
            "last_error": status.get("last_error", ""),
            "frame_count": int(status.get("frame_count", 0)),
            "fullsolve_count": int(status.get("fullsolve_count", 0)),
        }

    async def stop_analysis(self) -> dict[str, Any]:
        """结束实时分析 / Stop realtime analysis."""
        result = await realtime_solve_service.stop()
        self._session.running = False
        return {
            "success": bool(result.get("success", True)),
            "session_id": self._session.session_id,
            "state": "stopped",
            "message": result.get("message", ""),
        }

    async def get_system_status(self) -> dict[str, Any]:
        """系统状态与能力 / System status and capability map."""
        wifi_raw = wifi_switch_service.get_status()
        camera_status = await DebugCameraService.get_camera_status()
        system = system_info_service.get_system_info()
        sensors = {
            "temperature_c": system.get("temperature"),
            "cpu_usage_percent": system.get("cpu_usage"),
            "memory_usage_percent": system.get("memory_usage"),
            "uptime_seconds": system.get("uptime_seconds"),
        }
        network = {
            "mode": wifi_raw.get("MODE", "unknown"),
            "wireless_interface": wifi_raw.get(
                "WIRELESS_INTERFACE", get_settings().wifi_interface
            ),
            "signal_dbm": system.get("wifi_signal_dbm"),
            "quality_percent": system.get("wifi_quality"),
            "active_connection": wifi_raw.get("ACTIVE_CONNECTION"),
            "ap_ipv4": wifi_raw.get("AP_IPV4"),
            "error": wifi_raw.get("error"),
        }
        return {
            "success": True,
            "health": "healthy",
            "version": __version__,
            "capabilities": capability_map(),
            "system": system,
            "camera": camera_status,
            "network": network,
            "sensors": sensors,
        }

    async def get_camera_status(self) -> dict[str, Any]:
        """获取 Core 相机状态 / Get core camera status."""
        status = await DebugCameraService.get_camera_status()
        return {"success": True, **status}

    async def start_camera(self) -> dict[str, Any]:
        """启动 Core 相机 / Start core camera."""
        result = await DebugCameraService.start_camera()
        return {
            "success": bool(result.get("success", True)),
            "message": result.get("message", ""),
            "info": {},
            "applied": {"action": "start"},
        }

    async def stop_camera(self) -> dict[str, Any]:
        """停止 Core 相机 / Stop core camera."""
        result = await DebugCameraService.stop_camera()
        return {
            "success": bool(result.get("success", True)),
            "message": result.get("message", ""),
            "info": {},
            "applied": {"action": "stop"},
        }

    async def tune_camera(self, payload: dict[str, Any]) -> dict[str, Any]:
        """按 Core 语义微调相机参数 / Tune camera params with core semantics."""
        applied: dict[str, Any] = {}
        auto_exposure = payload.get("auto_exposure")
        if auto_exposure is not None:
            await DebugCameraService.set_auto_exposure_mode(bool(auto_exposure))
            applied["auto_exposure"] = bool(auto_exposure)

        if payload.get("exposure_us") is not None:
            await DebugCameraService.update_settings({"exposure": payload["exposure_us"]})
            applied["exposure_us"] = int(payload["exposure_us"])

        if payload.get("analogue_gain") is not None:
            settings: dict[str, Any] = {"gain": float(payload["analogue_gain"])}
            if payload.get("digital_gain") is not None:
                settings["digitalGain"] = float(payload["digital_gain"])
                applied["digital_gain"] = float(payload["digital_gain"])
            await DebugCameraService.update_settings(settings)
            applied["analogue_gain"] = float(payload["analogue_gain"])

        if payload.get("fps") is not None:
            await DebugCameraService.set_fps(int(payload["fps"]))
            applied["fps"] = int(payload["fps"])

        if payload.get("width") is not None and payload.get("height") is not None:
            await DebugCameraService.set_size(int(payload["width"]), int(payload["height"]))
            applied["width"] = int(payload["width"])
            applied["height"] = int(payload["height"])

        if payload.get("rotation") is not None:
            await DebugCameraService.set_rotation(int(payload["rotation"]))
            applied["rotation"] = int(payload["rotation"])

        if (
            payload.get("flip_horizontal") is not None
            or payload.get("flip_vertical") is not None
        ):
            fh = bool(payload.get("flip_horizontal", False))
            fv = bool(payload.get("flip_vertical", False))
            await DebugCameraService.set_mirror(fh, fv)
            applied["flip_horizontal"] = fh
            applied["flip_vertical"] = fv

        if payload.get("sampling_mode") is not None:
            await DebugCameraService.set_sampling_mode(str(payload["sampling_mode"]))
            applied["sampling_mode"] = str(payload["sampling_mode"])

        if payload.get("color_mode") is not None:
            await DebugCameraService.set_color_mode(str(payload["color_mode"]))
            applied["color_mode"] = str(payload["color_mode"])

        if payload.get("white_balance_mode") is not None:
            await DebugCameraService.set_white_balance(
                str(payload["white_balance_mode"]),
                float(payload.get("white_balance_gain_r", 1.0)),
                float(payload.get("white_balance_gain_b", 1.0)),
            )
            applied["white_balance_mode"] = str(payload["white_balance_mode"])
            if payload.get("white_balance_gain_r") is not None:
                applied["white_balance_gain_r"] = float(payload["white_balance_gain_r"])
            if payload.get("white_balance_gain_b") is not None:
                applied["white_balance_gain_b"] = float(payload["white_balance_gain_b"])

        info = {}
        camera_status = await DebugCameraService.get_camera_status()
        if isinstance(camera_status, dict):
            info = camera_status.get("info", {}) or {}

        return {
            "success": True,
            "message": "camera_tuned",
            "info": info,
            "applied": applied,
        }

    async def get_stream_status(self) -> dict[str, Any]:
        """获取流控状态 / Get stream limiter status."""
        limiter = get_mjpeg_stream_limiter()
        settings = get_settings()
        return {
            "success": True,
            "max_clients": int(limiter.max_clients),
            "active_clients": int(limiter.active_clients),
            "frame_fetch_timeout_ms": int(settings.stream_mjpeg_frame_fetch_timeout_ms),
            "target_preview_fps": int(os.getenv("OGSCOPE_SHARED_PREVIEW_FPS", "8") or "8"),
        }

    async def list_video_files(self) -> dict[str, Any]:
        """列出视频文件信息 / List recorded video file metadata."""
        data = await DebugFileService.get_files()
        files = data.get("files", [])
        videos = [f for f in files if isinstance(f, dict) and f.get("type") == "video"]
        return {"success": True, "files": videos}

    async def get_video_file_info(self, filename: str) -> dict[str, Any]:
        """获取视频文件详情 / Get video file detail metadata."""
        info = await DebugFileService.get_file_info(filename)
        if info.get("type") != "video":
            raise ValueError("requested file is not video")
        return {"success": True, "file": info}


core_contract_service = CoreContractService()
