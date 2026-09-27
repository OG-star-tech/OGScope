"""
实时解算服务 / Realtime solving service
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from ogscope.algorithms.plate_solve import PlateSolver, SolveResult
from ogscope.algorithms.plate_solve.sensor_context import attach_sensor_prediction
from ogscope.config import effective_solver_max_stars, get_settings
from ogscope.domain.camera.encoding import OpenCVEncoder, create_preview_encoder
from ogscope.web.camera_shared import get_camera_manager


@dataclass(slots=True)
class RealtimeState:
    """实时状态 / Realtime state"""

    running: bool = False
    frame_count: int = 0
    fullsolve_count: int = 0
    last_result: dict[str, Any] | None = None
    last_error: str = ""
    session_id: str = ""
    started_mono: float = 0.0


@dataclass(frozen=True, slots=True)
class SolveFrameSnapshot:
    """与解算结果严格对应的单张 JPEG / Single JPEG corresponding exactly to a solve."""

    content: bytes
    session_id: str
    frame_id: int
    captured_at: float
    width: int
    height: int
    encoder: str
    encode_ms: float


class RealtimeSolveService:
    """实时解算器：周期性 Tetra3 全量解算 / Realtime solver with periodic Tetra3"""

    def __init__(self) -> None:
        settings = get_settings()
        self._max_stars = effective_solver_max_stars(settings)
        self.solver = PlateSolver(
            fov_deg=settings.solver_fov_deg,
            fov_max_error_deg=settings.solver_fov_max_error_deg,
            solve_timeout_ms=settings.solver_timeout_ms,
        )
        self.state = RealtimeState()
        self._task: asyncio.Task[None] | None = None
        self._has_fullsolve = False
        self._hint_ra = settings.solver_hint_ra_deg
        self._hint_dec = settings.solver_hint_dec_deg
        self._fullsolve_interval = max(1, settings.solver_fullsolve_interval_frames)
        self._fov_estimate: float | None = None
        self._fov_max_error: float | None = None
        self._solve_timeout_ms: int | None = None
        self._solve_context: Any | None = None
        self._snapshot_lock = threading.Lock()
        self._snapshot: SolveFrameSnapshot | None = None
        self._snapshot_encoder = create_preview_encoder(
            getattr(settings, "preview_encoder", "auto")
        )
        self._snapshot_quality = min(70, int(settings.preview_jpeg_quality))
        self._snapshot_encode_failures = 0
        self._analysis_interval_sec = max(
            float(settings.star_analysis_min_interval_ms) / 1000.0,
            1.0 / max(0.01, float(settings.star_analysis_target_fps)),
        )

    @staticmethod
    def _capture_time_payload(
        capture_completed_ts: float,
        camera_info: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build exposure-midpoint UTC telemetry / 构造曝光中点 UTC 遥测。"""
        try:
            completed_ts = float(capture_completed_ts)
            if completed_ts <= 0:
                return {}
            info = camera_info if isinstance(camera_info, dict) else {}
            exposure_us = max(
                0,
                int(info.get("actual_exposure_us", info.get("exposure_us", 0)) or 0),
            )
            midpoint_ts = completed_ts - exposure_us / 2_000_000.0
            completed_iso = (
                datetime.fromtimestamp(completed_ts, timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            midpoint_iso = (
                datetime.fromtimestamp(midpoint_ts, timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
        except (OSError, OverflowError, TypeError, ValueError):
            return {}
        return {
            "observation_time_utc": midpoint_iso,
            "capture_completed_at_utc": completed_iso,
            "capture_exposure_us": exposure_us,
        }

    async def start(
        self,
        hint_ra_deg: float | None = None,
        hint_dec_deg: float | None = None,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
        solve_context: Any | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """启动实时解算 / Start realtime solving"""
        if self.state.running:
            return {
                "success": True,
                "session_id": self.state.session_id,
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
        self.state = RealtimeState(
            running=True,
            session_id=str(session_id or ""),
            started_mono=time.monotonic(),
        )
        with self._snapshot_lock:
            # 新会话不能看到上一轮的图像 / A new session must not expose an older frame.
            self._snapshot = None
        self._has_fullsolve = False
        # 相机在会话之间通常持续采集（供预览使用），缓存里"最新"的那一帧可能是
        # 移动/未稳定期间拍到的，比如刚结束的 GOTO 收尾阶段。_loop 原来把
        # last_frame_id 初始化成 -1，会把这张缓存里已有的旧帧当成本次会话的
        # 全新首帧、立即拿去做 fullsolve——这正是"稳定时间之后仍然解算到带
        # 拖线的帧"的根因。这里先取一次当前帧号作为基线，循环里必须等到真正
        # 采集时间晚于此刻的新帧号，才会把它当作本次会话的首帧。
        # The camera usually keeps capturing between sessions (for the live
        # preview), so the "latest" cached frame can be one taken during/
        # right after a move, before settling finished. _loop used to seed
        # last_frame_id with -1, so that already-cached stale frame got
        # accepted as this session's brand-new first frame and solved
        # immediately - this was the root cause of "still solving a trailed
        # frame after the settle wait". Grab the current frame id as a
        # baseline here so the loop only accepts a frame captured after this
        # point as its first frame.
        baseline_frame_id = -1
        try:
            _frame, baseline_frame_id, _ts = await get_camera_manager().get_raw_frame()
        except Exception:  # noqa: BLE001 - baseline is best-effort
            baseline_frame_id = -1
        # A newer frame_id is not the same guarantee as a newer optical scene:
        # the V4L2 backend's temporal-NR EMA accumulator used to reset only on
        # an exposure/gain change or a physical camera (re)start, so a frame
        # captured after this point could still be blended with raw frames
        # from before the mount settled. Tell the driver this is a fresh
        # analysis-session epoch so it discards that history too - drivers
        # with no such state (or test doubles) simply don't implement the
        # hook.
        camera = get_camera_manager().get_camera_instance()
        begin_epoch = getattr(camera, "begin_fresh_capture_epoch", None)
        if callable(begin_epoch):
            begin_epoch()
        self._task = asyncio.create_task(self._loop(baseline_frame_id))
        self._log_event(
            "session_started",
            fov_estimate=fov_estimate,
            fov_max_error=fov_max_error,
            solve_timeout_ms=solve_timeout_ms,
        )
        return {
            "success": True,
            "session_id": self.state.session_id,
            "message": "实时解算已启动 / Realtime solver started",
        }

    async def stop(self) -> dict[str, Any]:
        """停止实时解算 / Stop realtime solving"""
        was_running = self.state.running
        self.state.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        if was_running:
            self._log_event(
                "session_stopped",
                frame_count=self.state.frame_count,
                fullsolve_count=self.state.fullsolve_count,
                last_status=str((self.state.last_result or {}).get("status") or ""),
                last_error=self.state.last_error,
            )
        return {"success": True, "message": "实时解算已停止 / Realtime solver stopped"}

    async def get_status(self) -> dict[str, Any]:
        """读取实时状态 / Read realtime status"""
        return {
            "running": self.state.running,
            "frame_count": self.state.frame_count,
            "fullsolve_count": self.state.fullsolve_count,
            "last_result": self.state.last_result,
            "last_error": self.state.last_error,
            "session_id": self.state.session_id,
        }

    async def _loop(self, initial_frame_id: int = -1) -> None:
        """后台循环 / Background loop"""
        last_started_mono = 0.0
        last_frame_id = initial_frame_id
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
                    frame, frame_id, frame_ts = await manager.get_raw_frame()
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
                self.state.frame_count += 1
                try:
                    camera_info = cam.get_camera_info()
                except (
                    Exception
                ):  # noqa: BLE001 - timing remains optional / 时间遥测可降级
                    camera_info = {}
                capture_time = self._capture_time_payload(frame_ts, camera_info)

                use_fullsolve = (
                    self.state.frame_count % self._fullsolve_interval == 0
                    or not self._has_fullsolve
                    or str((self.state.last_result or {}).get("status") or "")
                    != "MATCH_FOUND"
                )
                if use_fullsolve:
                    solve_started = time.monotonic()
                    solved = await asyncio.to_thread(
                        self._solve_frame_sync,
                        frame,
                    )
                    snapshot: SolveFrameSnapshot | None = None
                    snapshot_attempted = self._should_retain_snapshot(solved)
                    if snapshot_attempted:
                        source_format = str(
                            getattr(cam, "output_pixel_format", None)
                            or getattr(cam, "pixel_format", None)
                            or "RGB888"
                        )
                        snapshot = await asyncio.to_thread(
                            self._encode_snapshot_sync,
                            frame,
                            session_id=self.state.session_id,
                            frame_id=frame_id,
                            captured_at=frame_ts,
                            source_format=source_format,
                        )
                    self._apply_solve_result(
                        solved,
                        capture_time=capture_time,
                        frame_id=frame_id,
                        snapshot=snapshot,
                        snapshot_attempted=snapshot_attempted,
                    )
                    self.state.fullsolve_count += 1
                    self._log_event(
                        "fullsolve_finished",
                        frame_count=self.state.frame_count,
                        fullsolve_count=self.state.fullsolve_count,
                        status=solved.status,
                        detected_stars=solved.detected_stars,
                        matches=solved.matches,
                        t_solve_ms=solved.t_solve_ms,
                        t_extract_ms=solved.t_extract_ms,
                        t_preprocess_ms=solved.t_preprocess_ms,
                        wall_ms=int((time.monotonic() - solve_started) * 1000),
                        rmse_arcsec=solved.rmse_arcsec,
                        observation_time_utc=capture_time.get("observation_time_utc"),
                        solve_snapshot_bytes=len(snapshot.content) if snapshot else 0,
                        solve_snapshot_encode_ms=(
                            round(snapshot.encode_ms, 3) if snapshot else None
                        ),
                        solve_snapshot_encoder=snapshot.encoder if snapshot else None,
                    )
                    # ``solve_from_bgr_frame`` is the authoritative production
                    # image pipeline.  Keep only a sentinel here; StarExtractor
                    # remains available for focus metrics and lightweight counts.
                    # ``solve_from_bgr_frame`` 是生产解算权威图像管线；这里只保留哨兵。
                    # StarExtractor 仍用于焦点指标和轻量星点计数。
                    self._has_fullsolve = True
            except Exception as exc:  # noqa: BLE001
                changed = str(exc) != self.state.last_error
                self.state.last_error = str(exc)
                if changed:
                    self._log_event("loop_error", error=str(exc), level="warning")
                await asyncio.sleep(0.1)

    def _log_event(self, event: str, *, level: str = "info", **fields: Any) -> None:
        """Emit one correlated solve lifecycle event / 输出一条可关联的解算生命周期事件。"""
        started = self.state.started_mono
        payload = {
            "event": event,
            "session_id": self.state.session_id,
            "elapsed_ms": int((time.monotonic() - started) * 1000) if started else 0,
            **fields,
        }
        log = logger.warning if level == "warning" else logger.info
        log(
            "analysis_event {}",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
        )

    def _solve_frame_sync(
        self,
        frame: Any,
    ) -> SolveResult:
        """同步解算单帧（线程池中调用）/ Sync solve for one frame."""
        return self.solver.solve_from_bgr_frame(
            frame_bgr=frame,
            max_stars=self._max_stars,
            hint_ra_deg=self._hint_ra,
            hint_dec_deg=self._hint_dec,
            solve_source="realtime",
            fov_estimate=self._fov_estimate,
            fov_max_error=self._fov_max_error,
            solve_timeout_ms=self._solve_timeout_ms,
        )

    @staticmethod
    def _should_retain_snapshot(solved: SolveResult) -> bool:
        """成功解算或存在结构证据时保留一帧 / Retain successes or structural evidence."""
        if solved.status == "MATCH_FOUND":
            return True
        quality = solved.centroid_quality
        scene = quality.get("scene") if isinstance(quality, dict) else None
        return bool(
            isinstance(scene, dict) and scene.get("has_structural_evidence", False)
        )

    def _encode_snapshot_sync(
        self,
        frame: Any,
        *,
        session_id: str,
        frame_id: int,
        captured_at: float,
        source_format: str,
    ) -> SolveFrameSnapshot | None:
        """在线程中编码一次，失败不影响解算 / Encode once off-loop; failure is non-fatal."""
        started = time.perf_counter()
        try:
            encoded = self._snapshot_encoder.encode_jpeg(
                frame,
                quality=self._snapshot_quality,
                source_format=source_format,
            )
            if encoded is None:
                encoded = OpenCVEncoder().encode_jpeg(
                    frame,
                    quality=self._snapshot_quality,
                    source_format=source_format,
                )
        except Exception:  # noqa: BLE001 - snapshot is best effort / 快照为尽力而为
            encoded = None
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if encoded is None:
            self._snapshot_encode_failures += 1
            return None
        height = int(getattr(frame, "shape", [0, 0])[0])
        width = int(getattr(frame, "shape", [0, 0])[1])
        return SolveFrameSnapshot(
            content=encoded.data,
            session_id=session_id,
            frame_id=int(frame_id),
            captured_at=float(captured_at),
            width=width,
            height=height,
            encoder=encoded.encoder,
            encode_ms=elapsed_ms,
        )

    def get_solve_frame_snapshot(self) -> SolveFrameSnapshot | None:
        """返回不可变快照引用 / Return the immutable current snapshot."""
        with self._snapshot_lock:
            return self._snapshot

    def _apply_solve_result(
        self,
        solved: SolveResult,
        *,
        capture_time: dict[str, Any] | None = None,
        frame_id: int | None = None,
        snapshot: SolveFrameSnapshot | None = None,
        snapshot_attempted: bool = False,
    ) -> None:
        """写入解算结果 / Persist solve result"""
        row = solved.to_dict()
        if capture_time:
            # Optional additive Core fields keep old consumers compatible. /
            # 可选增量字段保持旧版 Core 消费方兼容。
            row.update(capture_time)
        if frame_id is not None:
            row["solve_frame"] = {
                "available": snapshot is not None,
                "session_id": self.state.session_id,
                "frame_id": int(frame_id),
                "width": snapshot.width if snapshot else None,
                "height": snapshot.height if snapshot else None,
                "media_type": "image/jpeg" if snapshot else None,
                "byte_size": len(snapshot.content) if snapshot else 0,
                "encoder": snapshot.encoder if snapshot else None,
                "encode_ms": round(snapshot.encode_ms, 3) if snapshot else None,
                "encode_failures": self._snapshot_encode_failures,
                "reason": (
                    None
                    if snapshot is not None
                    else "encode_failed" if snapshot_attempted else "not_retained"
                ),
            }
        with self._snapshot_lock:
            # 始终覆盖，防止新结果错误搭配旧图 / Always replace to prevent result/frame mixing.
            self._snapshot = snapshot
        attach_sensor_prediction(row, self._solve_context)
        self.state.last_result = row
        # A later completed frame supersedes a transient capture/solve exception.
        # 后续完成的帧应清除瞬时采集或解算异常，避免上层永久看到旧错误。
        self.state.last_error = ""
        self._hint_ra = solved.ra_deg
        self._hint_dec = solved.dec_deg


realtime_solve_service = RealtimeSolveService()
