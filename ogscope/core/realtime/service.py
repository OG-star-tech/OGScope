"""
实时解算服务 / Realtime solving service
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ogscope.algorithms.plate_solve import PlateSolver, SolveResult
from ogscope.algorithms.star_extract import StarExtractor, StarPoint
from ogscope.algorithms.star_match import FastTracker
from ogscope.config import get_settings
from ogscope.web.api.debug.services import DebugCameraService


@dataclass(slots=True)
class RealtimeState:
    """实时状态 / Realtime state"""

    running: bool = False
    frame_count: int = 0
    fullsolve_count: int = 0
    last_result: dict[str, Any] | None = None
    last_error: str = ""


class RealtimeSolveService:
    """实时解算器 / Realtime solver"""

    def __init__(self) -> None:
        settings = get_settings()
        self.extractor = StarExtractor(max_stars=settings.solver_max_stars)
        self.solver = PlateSolver(fov_deg=settings.solver_fov_deg)
        self.tracker = FastTracker()
        self.state = RealtimeState()
        self._task: asyncio.Task[None] | None = None
        self._previous_stars: list[StarPoint] | None = None
        self._hint_ra = settings.solver_hint_ra_deg
        self._hint_dec = settings.solver_hint_dec_deg
        self._fullsolve_interval = max(1, settings.solver_fullsolve_interval_frames)

    async def start(
        self, hint_ra_deg: float | None = None, hint_dec_deg: float | None = None
    ) -> dict[str, Any]:
        """启动实时解算 / Start realtime solving"""
        if self.state.running:
            return {"success": True, "message": "实时解算已在运行 / Realtime solver already running"}
        if hint_ra_deg is not None:
            self._hint_ra = hint_ra_deg
        if hint_dec_deg is not None:
            self._hint_dec = hint_dec_deg
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
        while self.state.running:
            try:
                camera = DebugCameraService.get_camera_instance()
                if not camera or not getattr(camera, "is_capturing", False):
                    await asyncio.sleep(0.1)
                    continue
                frame = camera.get_video_frame()
                if frame is None:
                    await asyncio.sleep(0.02)
                    continue
                stars = self.extractor.extract(frame)
                self.state.frame_count += 1

                use_fullsolve = (
                    self.state.frame_count % self._fullsolve_interval == 0
                    or self._previous_stars is None
                )
                if use_fullsolve:
                    solved = self.solver.solve(
                        stars=stars,
                        frame_shape=frame.shape,
                        hint_ra_deg=self._hint_ra,
                        hint_dec_deg=self._hint_dec,
                        solve_source="full",
                    )
                    self._apply_solve_result(solved)
                    self.state.fullsolve_count += 1
                else:
                    track = self.tracker.track(self._previous_stars or [], stars)
                    deg_per_px = self.solver.fov_deg / max(frame.shape[1], 1)
                    self._hint_dec = float(
                        max(-90.0, min(90.0, self._hint_dec - track.delta_y * deg_per_px))
                    )
                    self._hint_ra = float((self._hint_ra + track.delta_x * deg_per_px) % 360.0)
                    solved = self.solver.solve(
                        stars=stars,
                        frame_shape=frame.shape,
                        hint_ra_deg=self._hint_ra,
                        hint_dec_deg=self._hint_dec,
                        solve_source="track",
                    )
                    base = solved.to_dict()
                    base["track"] = track.to_dict()
                    self.state.last_result = base
                    self._hint_ra = solved.ra_deg
                    self._hint_dec = solved.dec_deg
                self._previous_stars = stars
                await asyncio.sleep(0.02)
            except Exception as exc:  # noqa: BLE001
                self.state.last_error = str(exc)
                await asyncio.sleep(0.1)

    def _apply_solve_result(self, solved: SolveResult) -> None:
        """写入解算结果 / Persist solve result"""
        self.state.last_result = solved.to_dict()
        self._hint_ra = solved.ra_deg
        self._hint_dec = solved.dec_deg


realtime_solve_service = RealtimeSolveService()
