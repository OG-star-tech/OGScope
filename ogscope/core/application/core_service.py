"""
Core 标准契约应用服务 / Core standard contract application service.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ogscope.__version__ import __version__
from ogscope.config import get_settings
from ogscope.core.capabilities import capability_map
from ogscope.core.realtime import realtime_solve_service
from ogscope.domain.camera.services import (
    camera_domain_service,
    file_domain_service,
    stream_state_domain_service,
)
from ogscope.domain.system.services import system_info_service
from ogscope.platform.hardware.wifi_switch import wifi_switch_service
from ogscope.platform.hardware_plane.runtime import (
    describe_hardware_plane_profile,
    get_hardware_plane_client,
)


@dataclass(slots=True)
class CoreAnalysisSession:
    """Core 分析会话状态 / Core analysis session state."""

    session_id: str = "realtime-default"
    running: bool = False


class CoreContractService:
    """OGScope 对上层调用方的稳定契约服务 / Stable OGScope contract for upstream callers."""

    def __init__(self) -> None:
        self._session = CoreAnalysisSession()

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _build_ambient_hint(info: dict[str, Any], *, streaming: bool) -> dict[str, Any]:
        """构造环境亮度建议遥测 / Build ambient brightness hint telemetry."""
        lux = CoreContractService._optional_float(info.get("lux"))
        exposure_us = CoreContractService._optional_float(
            info.get("actual_exposure_us", info.get("exposure_us"))
        )
        digital_gain = CoreContractService._optional_float(
            info.get("actual_digital_gain", info.get("digital_gain"))
        )
        max_exposure_us = CoreContractService._optional_float(
            info.get("auto_exposure_max_us", info.get("frame_duration_us"))
        )

        scores: list[float] = []
        if lux is not None and lux >= 0:
            scores.append(CoreContractService._clamp01(1.0 - math.log10(lux + 1.0) / 2.0))
        if exposure_us is not None and exposure_us > 0:
            exposure_ceiling = max(max_exposure_us or 100_000.0, 1.0)
            exposure_score = CoreContractService._clamp01(exposure_us / exposure_ceiling)
            gain_score = 0.0
            if digital_gain is not None:
                gain_score = CoreContractService._clamp01((digital_gain - 1.0) / 7.0)
            scores.append(CoreContractService._clamp01(exposure_score * 0.75 + gain_score * 0.25))

        dark_score = sum(scores) / len(scores) if scores else None
        return {
            "available": bool(streaming and dark_score is not None),
            "source": "camera_metadata" if dark_score is not None else "unavailable",
            "confidence": "live" if streaming and dark_score is not None else "stale",
            "dark_score": round(dark_score, 3) if dark_score is not None else None,
            "lux": lux,
            "exposure_us": int(exposure_us) if exposure_us is not None else None,
            "digital_gain": digital_gain,
        }

    @staticmethod
    def _normalize_camera_status(status: dict[str, Any]) -> dict[str, Any]:
        """统一 Core 相机状态形状 / Normalize camera status payload shape."""
        streaming = bool(status.get("streaming", False))
        info = status.get("info", {}) or {}
        return {
            "connected": bool(status.get("connected", False)),
            "streaming": streaming,
            "recording": bool(status.get("recording", False)),
            "info": info,
            "ambient_hint": CoreContractService._build_ambient_hint(
                info,
                streaming=streaming,
            ),
            "runtime_overrides": status.get("runtime_overrides", {}) or {},
            "error": status.get("error"),
        }

    @staticmethod
    def _network_health_in_scope(profile: dict[str, Any]) -> bool:
        """网络是否纳入 OGScope health 评估 / Whether network affects OGScope health."""
        if bool(profile.get("subordinate_mode")):
            return False
        return wifi_switch_service.is_configured()

    @staticmethod
    def _health_reasons(
        camera_status: dict[str, Any],
        network: dict[str, Any],
        *,
        network_in_health_scope: bool,
    ) -> list[str]:
        """稳定 health 降级原因码 / Stable machine-readable health degradation codes."""
        reasons: list[str] = []
        if not camera_status.get("connected", False):
            reasons.append("camera_not_connected")
        if not network_in_health_scope:
            return reasons
        net_err = network.get("error")
        if net_err:
            token = str(net_err).strip().lower().replace("-", "_")
            if token and token.replace("_", "").isalnum():
                reasons.append(f"network_{token}")
            else:
                reasons.append("network_error")
        return reasons

    @staticmethod
    def _build_network_status(
        profile: dict[str, Any],
        system: dict[str, Any],
    ) -> dict[str, Any]:
        """构造 network 块：职责外仅遥测，不参与 health / Build network block with scope metadata."""
        settings = get_settings()
        in_health_scope = CoreContractService._network_health_in_scope(profile)
        base: dict[str, Any] = {
            "wireless_interface": settings.wifi_interface,
            "signal_dbm": system.get("wifi_signal_dbm"),
            "quality_percent": system.get("wifi_quality"),
            "in_health_scope": in_health_scope,
        }
        if not in_health_scope:
            managed_by = "external" if profile.get("subordinate_mode") else "unconfigured"
            return {
                **base,
                "managed_by": managed_by,
                "status": "delegated",
                "mode": "unknown",
                "active_connection": None,
                "ap_ipv4": None,
                "error": None,
            }
        wifi_raw = wifi_switch_service.get_status()
        return {
            **base,
            "managed_by": "ogscope",
            "status": "managed",
            "mode": wifi_raw.get("MODE", "unknown"),
            "active_connection": wifi_raw.get("ACTIVE_CONNECTION"),
            "ap_ipv4": wifi_raw.get("AP_IPV4"),
            "error": wifi_raw.get("error"),
        }

    async def start_analysis(
        self,
        *,
        hint_ra_deg: float | None = None,
        hint_dec_deg: float | None = None,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
        solve_context: Any | None = None,
    ) -> dict[str, Any]:
        """开始实时分析 / Start realtime analysis."""
        result = await realtime_solve_service.start(
            hint_ra_deg=hint_ra_deg,
            hint_dec_deg=hint_dec_deg,
            fov_estimate=fov_estimate,
            fov_max_error=fov_max_error,
            solve_timeout_ms=solve_timeout_ms,
            solve_context=solve_context,
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
        profile = describe_hardware_plane_profile()
        network_in_health_scope = self._network_health_in_scope(profile)
        hardware_client = get_hardware_plane_client()
        hw_status_resp = await hardware_client.status_get()
        hw_status_data = hw_status_resp.get("data", {}) if hw_status_resp.get("success") else {}
        camera_service_status = (
            hw_status_data.get("services", {}).get("camera", {})
            if isinstance(hw_status_data, dict)
            else {}
        )
        raw_camera_status = await camera_domain_service.get_status()
        camera_status = self._normalize_camera_status(raw_camera_status)
        if camera_service_status:
            camera_status["connected"] = bool(
                camera_service_status.get("connected", camera_status["connected"])
            )
            camera_status["streaming"] = bool(
                camera_service_status.get("streaming", camera_status["streaming"])
            )
        system = system_info_service.get_system_info()
        sensors = {
            "temperature_c": system.get("temperature"),
            "cpu_usage_percent": system.get("cpu_usage"),
            "memory_usage_percent": system.get("memory_usage"),
            "uptime_seconds": system.get("uptime_seconds"),
        }
        network = self._build_network_status(profile, system)
        health_reasons = self._health_reasons(
            camera_status,
            network,
            network_in_health_scope=network_in_health_scope,
        )
        health = "healthy" if not health_reasons else "degraded"
        return {
            "success": True,
            "health": health,
            "health_reasons": health_reasons,
            "version": __version__,
            "capabilities": capability_map(),
            "hardware_plane": {
                "started": bool(hw_status_data.get("started", False))
                if isinstance(hw_status_data, dict)
                else False,
                "metrics": hw_status_data.get("metrics", {})
                if isinstance(hw_status_data, dict)
                else {},
                "services": hw_status_data.get("services", {})
                if isinstance(hw_status_data, dict)
                else {},
            },
            "system": system,
            "camera": {"success": True, **camera_status},
            "network": network,
            "sensors": sensors,
        }

    async def get_camera_status(self) -> dict[str, Any]:
        """获取 Core 相机状态 / Get core camera status."""
        hardware_client = get_hardware_plane_client()
        hp_status = await hardware_client.status_get()
        hp_camera = (
            hp_status.get("data", {}).get("services", {}).get("camera", {})
            if hp_status.get("success")
            else {}
        )
        status = await camera_domain_service.get_status()
        normalized = self._normalize_camera_status(status)
        if hp_camera:
            normalized["connected"] = bool(hp_camera.get("connected", normalized["connected"]))
            normalized["streaming"] = bool(hp_camera.get("streaming", normalized["streaming"]))
            normalized["recording"] = bool(hp_camera.get("recording", normalized["recording"]))
        return {"success": True, **normalized}

    async def start_camera(self) -> dict[str, Any]:
        """启动 Core 相机 / Start core camera."""
        hardware_client = get_hardware_plane_client()
        hp_result = await hardware_client.device_command("camera", "start")
        result = await camera_domain_service.start()
        return {
            "success": bool(result.get("success", True)),
            "message": result.get("message", ""),
            "info": {},
            "applied": {
                "action": "start",
                "hardware_plane_ok": bool(hp_result.get("success", False)),
            },
        }

    async def stop_camera(self) -> dict[str, Any]:
        """停止 Core 相机 / Stop core camera."""
        hardware_client = get_hardware_plane_client()
        hp_result = await hardware_client.device_command("camera", "stop")
        result = await camera_domain_service.stop()
        return {
            "success": bool(result.get("success", True)),
            "message": result.get("message", ""),
            "info": {},
            "applied": {
                "action": "stop",
                "hardware_plane_ok": bool(hp_result.get("success", False)),
            },
        }

    async def tune_camera(self, payload: dict[str, Any]) -> dict[str, Any]:
        """按 Core 语义微调相机参数 / Tune camera params with core semantics."""
        applied: dict[str, Any] = {}
        auto_exposure = payload.get("auto_exposure")
        if auto_exposure is not None:
            await camera_domain_service.set_auto_exposure_mode(bool(auto_exposure))
            applied["auto_exposure"] = bool(auto_exposure)

        if payload.get("exposure_us") is not None:
            await camera_domain_service.update_settings({"exposure": payload["exposure_us"]})
            applied["exposure_us"] = int(payload["exposure_us"])

        if payload.get("analogue_gain") is not None:
            settings: dict[str, Any] = {"gain": float(payload["analogue_gain"])}
            if payload.get("digital_gain") is not None:
                settings["digitalGain"] = float(payload["digital_gain"])
                applied["digital_gain"] = float(payload["digital_gain"])
            await camera_domain_service.update_settings(settings)
            applied["analogue_gain"] = float(payload["analogue_gain"])
        elif payload.get("digital_gain") is not None:
            await camera_domain_service.update_settings(
                {"digitalGain": float(payload["digital_gain"])}
            )
            applied["digital_gain"] = float(payload["digital_gain"])

        if payload.get("fps") is not None:
            await camera_domain_service.set_fps(int(payload["fps"]))
            applied["fps"] = int(payload["fps"])

        if payload.get("width") is not None and payload.get("height") is not None:
            await camera_domain_service.set_size(
                int(payload["width"]), int(payload["height"])
            )
            applied["width"] = int(payload["width"])
            applied["height"] = int(payload["height"])

        if payload.get("rotation") is not None:
            await camera_domain_service.set_rotation(int(payload["rotation"]))
            applied["rotation"] = int(payload["rotation"])

        if (
            payload.get("flip_horizontal") is not None
            or payload.get("flip_vertical") is not None
        ):
            fh = bool(payload.get("flip_horizontal", False))
            fv = bool(payload.get("flip_vertical", False))
            await camera_domain_service.set_mirror(fh, fv)
            applied["flip_horizontal"] = fh
            applied["flip_vertical"] = fv

        if payload.get("sampling_mode") is not None:
            await camera_domain_service.set_sampling_mode(str(payload["sampling_mode"]))
            applied["sampling_mode"] = str(payload["sampling_mode"])

        if payload.get("color_mode") is not None:
            await camera_domain_service.set_color_mode(str(payload["color_mode"]))
            applied["color_mode"] = str(payload["color_mode"])

        if payload.get("white_balance_mode") is not None:
            await camera_domain_service.set_white_balance(
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
        camera_status = await camera_domain_service.get_status()
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
        stream = await stream_state_domain_service.get_stream_status()
        return {
            "success": True,
            **stream,
        }

    async def list_video_files(self) -> dict[str, Any]:
        """列出视频文件信息 / List recorded video file metadata."""
        data = await file_domain_service.list_files()
        files = data.get("files", [])
        videos = [f for f in files if isinstance(f, dict) and f.get("type") == "video"]
        return {"success": True, "files": videos}

    async def get_video_file_info(self, filename: str) -> dict[str, Any]:
        """获取视频文件详情 / Get video file detail metadata."""
        info = await file_domain_service.get_file_info(filename)
        if info.get("type") != "video":
            raise ValueError("requested file is not video")
        return {"success": True, "file": info}


core_contract_service = CoreContractService()
