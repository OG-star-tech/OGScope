"""
Core 标准契约应用服务 / Core standard contract application service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogscope.__version__ import __version__
from ogscope.core.capabilities import capability_map
from ogscope.core.realtime import realtime_solve_service
from ogscope.web.api.system.services import system_info_service


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
        return {
            "success": True,
            "health": "healthy",
            "version": __version__,
            "capabilities": capability_map(),
            "system": system_info_service.get_system_info(),
        }


core_contract_service = CoreContractService()
