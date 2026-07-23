"""
实时解算服务 / Realtime solving service
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from ogscope.algorithms.plate_solve import PlateSolver, SolveResult
from ogscope.algorithms.plate_solve.sensor_context import attach_sensor_prediction
from ogscope.algorithms.star_extract import StarExtractor, StarPoint
from ogscope.config import effective_solver_max_stars, get_settings
from ogscope.web.camera_shared import get_camera_manager


@dataclass(slots=True)
class RealtimeState:
    """实时状态 / Realtime state"""

    running: bool = False
    frame_count: int = 0
    fullsolve_count: int = 0
    last_result: dict[str, Any] | None = None
    last_error: str = ""


class RealtimeSolveService:
    """实时解算器：周期性 Tetra3 全量解算 / Realtime solver with periodic Tetra3"""

    def __init__(self) -> None:
        settings = get_settings()
        self.extractor = StarExtractor(max_stars=effective_solver_max_stars(settings))
        self.solver = PlateSolver(
            fov_deg=settings.solver_fov_deg,
            fov_max_error_deg=settings.solver_fov_max_error_deg,
            solve_timeout_ms=settings.solver_timeout_ms,
        )
        self.state = RealtimeState()
        self._task: asyncio.Task[None] | None = None
        self._previous_stars: list[StarPoint] | None = None
        self._hint_ra = settings.solver_hint_ra_deg
        self._hint_dec = settings.solver_hint_dec_deg
        self._fullsolve_interval = max(1, settings.solver_fullsolve_interval_frames)
        self._fov_estimate: float | None = None
        self._fov_max_error: float | None = None
        self._solve_timeout_ms: int | None = None
        self._solve_context: Any | None = None
        self._analysis_interval_sec = max(
            float(settings.star_analysis_min_interval_ms) / 1000.0,
            1.0 / max(0.01, float(settings.star_analysis_target_fps)),
        )

    async def start(
        self,
        hint_ra_deg: float | None = None,
        hint_dec_deg: float | None = None,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
        solve_context: Any | None = None,
    ) -> dict[str, Any]:
        """启动实时解算 / Start realtime solving"""
        if self.state.running:
            return {
                "success": True,
                "message": "实时解算已在运行 / Realtime solver already running",
            }
        if hint_ra_deg is not None:
            self._hint_ra = hint_ra_deg
        if hint_dec_deg is not None:
            self._hint_dec = hint_dec_deg
        self._fov_estimate = fov_estimate
        self._fov_max_error = fov_max_error
        self._solve_timeout_ms = solve_timeout_ms
        self._solve_context = solve_context
        self.state = RealtimeState(running=True)
        self._previous_stars = None
        self._task = asyncio.create_task(self._loop())
        return {"success": True, "message": "实时解算已启动 / Realtime solver started"}

    async def stop(self) -> dict[str, Any]:
        """停止实时解算 / Stop realtime solving"""
        self.state.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        return {"success": True, "message": "实时解算已停止 / Realtime solver stopped"}

    async def get_status(self) -> dict[str, Any]:
        """读取实时状态 / Read realtime status"""
        return {
            "running": self.state.running,
            "frame_count": self.state.frame_count,
            "fullsolve_count": self.state.fullsolve_count,
            "last_result": self.state.last_result,
            "last_error": self.state.last_error,
        }

    async def _loop(self) -> None:
        """后台循环 / Background loop"""
        last_started_mono = 0.0
        last_frame_id = -1
        while self.state.running:
            try:
                remaining = self._analysis_interval_sec - (
                    time.monotonic() - last_started_mono
                )
                if remaining > 0:
                    await asyncio.sleep(remaining)
                manager = get_camera_manager()
                cam = manager.get_camera_instance()
                if not cam or not getattr(cam, "is_capturing", False):
                    await asyncio.sleep(0.1)
                    continue
                # 必须与共享预览走同一套读锁 + 线程卸载，禁止在事件循环线程里直接 capture_array
                # Must share the same read lock as shared preview; never call capture_array on the event-loop thread.
                try:
                    frame, frame_id, _ts = await manager.get_raw_frame()
                except RuntimeError:
                    await asyncio.sleep(0.1)
                    continue
                if frame is None:
                    await asyncio.sleep(0.1)
                    continue
                if frame_id == last_frame_id:
                    await asyncio.sleep(0.05)
                    continue
                last_frame_id = frame_id
                last_started_mono = time.monotonic()
                stars = self.extractor.extract(frame)
                self.state.frame_count += 1

                use_fullsolve = (
                    self.state.frame_count % self._fullsolve_interval == 0
                    or self._previous_stars is None
                )
                if use_fullsolve:
                    solved = await asyncio.to_thread(
                        self._solve_frame_sync,
                        frame,
                        stars,
                    )
                    self._apply_solve_result(solved)
                    self.state.fullsolve_count += 1
                self._previous_stars = stars
            except Exception as exc:  # noqa: BLE001
                self.state.last_error = str(exc)
                await asyncio.sleep(0.1)

    def _solve_frame_sync(
        self,
        frame: Any,
        stars: list[StarPoint],
    ) -> SolveResult:
        """同步解算单帧（线程池中调用）/ Sync solve for one frame."""
        return self.solver.solve(
            stars=stars,
            frame_shape=frame.shape,
            hint_ra_deg=self._hint_ra,
            hint_dec_deg=self._hint_dec,
            solve_source="realtime",
            fov_estimate=self._fov_estimate,
            fov_max_error=self._fov_max_error,
            solve_timeout_ms=self._solve_timeout_ms,
        )

    def _apply_solve_result(self, solved: SolveResult) -> None:
        """写入解算结果 / Persist solve result"""
        row = solved.to_dict()
        attach_sensor_prediction(row, self._solve_context)
        self.state.last_result = row
        self._hint_ra = solved.ra_deg
        self._hint_dec = solved.dec_deg


realtime_solve_service = RealtimeSolveService()
