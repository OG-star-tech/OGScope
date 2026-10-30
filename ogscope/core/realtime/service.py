"""
实时解算服务 / Realtime solving service
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import cv2
from loguru import logger

from ogscope.algorithms.plate_solve import PlateSolver, SolveResult
from ogscope.algorithms.plate_solve.sensor_context import attach_sensor_prediction
from ogscope.algorithms.plate_solve.worker import run_solver_job
from ogscope.application.camera import get_camera_capture as get_camera_manager
from ogscope.config import effective_solver_max_stars, get_settings
from ogscope.domain.camera.encoding import OpenCVEncoder, create_preview_encoder
from ogscope.domain.camera.runtime import CameraCapture


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
    phase: str = "stopped"
    camera_preparation: dict[str, Any] = field(default_factory=dict)


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

    def __init__(self, *, capture: CameraCapture | None = None) -> None:
        self._capture = capture
        settings = get_settings()
        self._max_stars = effective_solver_max_stars(settings)
        self.solver = PlateSolver(
            fov_deg=settings.solver_fov_deg,
            fov_max_error_deg=settings.solver_fov_max_error_deg,
            solve_timeout_ms=settings.solver_timeout_ms,
        )
        self.state = RealtimeState()
        self._task: asyncio.Task[None] | None = None
        self._control_lock = asyncio.Lock()
        self._owner_token: str | None = None
        self._owner_seen_mono = 0.0
        self._ownership_timeout_s = 60.0
        self._ownership_watchdog: asyncio.Task[None] | None = None
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

    def _camera_capture(self) -> CameraCapture:
        """每个服务固定其注入端口；默认使用共享实例 / Resolve the injected or shared capture port."""
        return self._capture if self._capture is not None else get_camera_manager()

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
        self, *, owner_token: str | None = None, **options: Any
    ) -> dict[str, Any]:
        """Acquire one analysis without replacing another caller / 获取分析，禁止替换其他调用者。"""
        async with self._control_lock:
            if self.state.running and self._owner_token != owner_token:
                return {
                    "success": False,
                    "session_id": self.state.session_id,
                    "error_code": "ANALYSIS_BUSY",
                    "message": "Analysis is in use / 分析正在被其他任务使用",
                }
            if not self.state.running and self._task is not None:
                # Finish the old camera release before publishing a new session.
                # 旧任务释放相机后才能发布新会话。
                await self._stop_locked()
            try:
                result = await self._start_locked(**options)
            except BaseException:
                # A failed start must not leave a permanently busy phantom task.
                # 启动失败不能遗留永久忙碌的幽灵任务。
                await self._stop_locked()
                self._owner_token = None
                raise
            if result.get("success"):
                self._owner_token = owner_token
                self._owner_seen_mono = time.monotonic()
                if owner_token and (
                    self._ownership_watchdog is None or self._ownership_watchdog.done()
                ):
                    self._ownership_watchdog = asyncio.create_task(
                        self._expire_owner(self.state.session_id, owner_token)
                    )
            return result

    async def _expire_owner(self, session_id: str, owner_token: str) -> None:
        """Recover capture after a crashed/disconnected caller / 调用者崩溃或失联后回收相机。"""
        while self.state.running and self.state.session_id == session_id:
            await asyncio.sleep(min(5.0, self._ownership_timeout_s / 3))
            if time.monotonic() - self._owner_seen_mono >= self._ownership_timeout_s:
                await self.stop(session_id=session_id, owner_token=owner_token)
                return

    async def _start_locked(
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
            session_id=str(session_id or uuid.uuid4().hex),
            started_mono=time.monotonic(),
            phase="waking_camera",
        )
        with self._snapshot_lock:
            # 新会话不能看到上一轮的图像 / A new session must not expose an older frame.
            self._snapshot = None
        self._has_fullsolve = False
        # 相机在会话之间通常持续采集（供预览使用），缓存里"最新"的那一帧可能是
        # 移动/未稳定期间拍到的，比如刚结束的 GOTO 收尾阶段——但这只在底座
        # 真的刚移动过、驱动仍处于"新鲜窗口"内才是风险；同一姿态内的重试
        # （调用方没有再触发过移动结算）没有这个风险，当前缓存的那一帧本来
        # 就是安全的。is_within_fresh_capture_epoch() 由调用方在真正的移动
        # 结算时显式触发（见 begin_fresh_capture_epoch / Core
        # camera/reset-temporal-history），不是每次 start() 都会置位——如果
        # 这里也无条件调用 begin_fresh_capture_epoch，会让这个窗口在连续重
        # 试时永远续期，等于每次重试都要多付一次完整曝光的等待成本，恰恰是
        # 之前"同一姿态反复重试却几乎抓不到一帧"的根因。驱动没有这类状态
        # （或测试替身）时默认永远安全，直接用当前缓存的那一帧。
        # The camera usually keeps capturing between sessions (for the live
        # preview), so the "latest" cached frame can be one taken during/
        # right after a move, before settling finished - but that's only a
        # risk if the mount actually just moved and the driver is still
        # inside its "fresh window". A retry at an unchanged pose (no new
        # settle happened) has no such risk; the currently cached frame is
        # already safe. is_within_fresh_capture_epoch() is set explicitly by
        # the caller on a real settle (see begin_fresh_capture_epoch / the
        # Core camera/reset-temporal-history endpoint), not by every
        # start() call - calling begin_fresh_capture_epoch
        # unconditionally here would keep re-extending that window on every
        # retry, forcing every single retry to pay a full exposure's wait
        # again, which was exactly why repeated retries at the same pose
        # were barely capturing a frame at all. Drivers with no such state
        # (or test doubles) default to always-safe, using whatever is
        # cached right now.
        # get_raw_frame() must NOT be used for the baseline: without a
        # resident raw cache (the default) it synchronously grabs a whole
        # frame, which can mean waiting out whatever exposure the
        # background grabber is currently holding and then grabbing
        # another - measured to stretch this call past 8-10 seconds on real
        # hardware. get_current_capture_sequence() reads the same counter
        # without touching the camera at all.
        camera = self._camera_capture().get_camera_instance()
        still_within_fresh_epoch = getattr(
            camera, "is_within_fresh_capture_epoch", None
        )
        needs_fresh_frame = False
        if callable(still_within_fresh_epoch):
            try:
                needs_fresh_frame = bool(still_within_fresh_epoch())
            except Exception:  # noqa: BLE001 - best-effort, default to fast path
                needs_fresh_frame = False
        baseline_frame_id = -1
        if needs_fresh_frame:
            try:
                baseline_frame_id = (
                    self._camera_capture().get_current_capture_sequence()
                )
            except Exception:  # noqa: BLE001 - baseline is best-effort
                baseline_frame_id = -1
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

    async def stop(
        self,
        *,
        session_id: str | None = None,
        owner_token: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Stop only the requested session; force is internal shutdown only / 只停指定会话，强制仅供内部退出。"""
        async with self._control_lock:
            wrong_session = (
                session_id is not None and session_id != self.state.session_id
            )
            wrong_owner = self._owner_token is not None and (
                owner_token != self._owner_token or session_id != self.state.session_id
            )
            if not force and (wrong_session or wrong_owner):
                return {
                    "success": False,
                    "session_id": self.state.session_id,
                    "error_code": "ANALYSIS_NOT_OWNED",
                    "message": "Analysis belongs to another session / 分析属于其他会话",
                }
            result = await self._stop_locked()
            self._owner_token = None
            return {**result, "session_id": self.state.session_id}

    async def _stop_locked(self) -> dict[str, Any]:
        """停止实时解算 / Stop realtime solving"""
        watchdog, self._ownership_watchdog = self._ownership_watchdog, None
        if (
            watchdog is not None
            and watchdog is not asyncio.current_task()
            and not watchdog.done()
        ):
            watchdog.cancel()
            # 取消监护任务后确认退出，避免留下锁等待者 / Join the cancelled watchdog so no lock waiter remains.
            await asyncio.gather(watchdog, return_exceptions=True)
        was_running = self.state.running
        self.state.running = False
        self.state.phase = "stopped"
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.shield(self._task)
            except asyncio.CancelledError:
                if not self._task.done():
                    # Request cancellation must not interrupt camera release.
                    # HTTP请求取消不能打断相机释放。
                    try:
                        await asyncio.shield(self._task)
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

    async def get_status(self, *, owner_token: str | None = None) -> dict[str, Any]:
        """读取实时状态 / Read realtime status"""
        if (
            owner_token is not None
            and owner_token == self._owner_token
            and self.state.running
        ):
            self._owner_seen_mono = time.monotonic()
        return {
            "ownership_supported": True,
            "running": self.state.running,
            "frame_count": self.state.frame_count,
            "fullsolve_count": self.state.fullsolve_count,
            "last_result": self.state.last_result,
            "last_error": self.state.last_error,
            "session_id": self.state.session_id,
            "phase": self.state.phase,
            "camera_preparation": dict(self.state.camera_preparation),
        }

    async def _loop(self, initial_frame_id: int = -1) -> None:
        """分析全程持有相机，包括等帧与解算 / Hold capture through frame waits and solving."""
        manager = self._camera_capture()
        try:
            await manager.acquire_analysis_consumer()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - report startup failure / 报告启动失败
            self.state.last_error = str(exc)
            self.state.running = False
            self.state.phase = "failed"
            self._log_event("camera_start_failed", error=str(exc))
            return
        try:
            await self._prepare_camera(manager)
            await self._run_loop(manager, initial_frame_id)
        except asyncio.CancelledError:
            raise
        except (
            Exception
        ) as exc:  # Preparation failures are not solve misses / 准备失败不是星图不匹配。
            self.state.last_error = str(exc)
            self.state.phase = "failed"
            self.state.running = False
            self._log_event("camera_preparation_failed", error=str(exc))
        finally:
            await manager.release_analysis_consumer()

    async def _prepare_camera(self, manager: Any) -> None:
        """Wait before spending any solver attempts / 等待就绪后才消耗解算次数。"""
        from ogscope.domain.camera.readiness import wait_capture_ready

        def progress(value: dict[str, Any]) -> None:
            self.state.camera_preparation = value
            self.state.phase = "analyzing" if value.get("ready") else "preparing_camera"

        await wait_capture_ready(
            manager,
            on_progress=progress,
            should_continue=lambda: self.state.running,
            monotonic=time.monotonic,
        )
        self.state.phase = "analyzing"

    async def _run_loop(self, manager: Any, initial_frame_id: int = -1) -> None:
        """后台循环 / Background loop"""
        last_started_mono = 0.0
        last_frame_id = initial_frame_id
        frame_wait_started = time.monotonic()
        while self.state.running:
            try:
                remaining = self._analysis_interval_sec - (
                    time.monotonic() - last_started_mono
                )
                if remaining > 0:
                    await asyncio.sleep(remaining)
                if time.monotonic() - frame_wait_started > 30:
                    self.state.last_result = None
                    with self._snapshot_lock:
                        self._snapshot = None
                    raise RuntimeError(
                        "CAMERA_NOT_READY: no fresh frame for 30s / 30秒内没有新相机帧"
                    )
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
                frame_wait_started = time.monotonic()
                last_started_mono = time.monotonic()
                tracker = getattr(manager, "analysis_readiness", None)
                if tracker is not None and not tracker.snapshot().get("ready"):
                    # A changed scene must not reuse an older successful result.
                    # 场景变化后，准备曝光期间不能把旧成功结果当作当前结果。
                    self.state.last_result = None
                    with self._snapshot_lock:
                        self._snapshot = None
                    await self._prepare_camera(manager)
                    frame_wait_started = time.monotonic()
                    continue
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
                    solved = await run_solver_job(
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
                        snapshot = await run_solver_job(
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
                # Solver runtime is not missing-frame time / 解算运行时间不计入缺帧时限。
                frame_wait_started = time.monotonic()
            except Exception as exc:  # noqa: BLE001
                changed = str(exc) != self.state.last_error
                self.state.last_error = str(exc)
                if changed:
                    self._log_event("loop_error", error=str(exc), level="warning")
                if str(exc).startswith("CAMERA_NOT_READY"):
                    self.state.phase, self.state.running = "failed", False
                    return
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
        # 相机输出 RGB；解算器接收 BGR 副本，原帧仍供精确快照使用。
        # Camera output is RGB; solve a BGR copy and keep the original for its exact snapshot.
        frame_bgr = (
            cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            if getattr(frame, "ndim", 0) == 3
            else frame
        )
        return self.solver.solve_from_bgr_frame(
            frame_bgr=frame_bgr,
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
