"""单设备生命周期与组件协调 / Single-device lifecycle and component coordination."""

from __future__ import annotations

import asyncio
import logging
import time
from threading import Lock
from typing import Any, Callable

from loguru import logger as event_logger

from ogscope.application.camera_frames import (
    CameraFramePipeline,
)
from ogscope.application.camera_frames import (
    CapturedFrame as CapturedFrame,
)
from ogscope.application.camera_resources import CameraResources
from ogscope.config import get_settings
from ogscope.domain.camera.ownership import CameraOwnership
from ogscope.domain.camera.readiness import CaptureReadiness
from ogscope.domain.camera.runtime import SharedFrame
from ogscope.platform.adapters.camera_config import build_camera_config


class CameraManager:
    """唯一设备所有者；串行协调启停、占用和帧流水线 / Sole device owner serializing lifetime, ownership and frames."""

    def __init__(self) -> None:
        settings = get_settings()
        self._camera: Any = None
        self.analysis_readiness = CaptureReadiness()
        self._control_lock = asyncio.Lock()
        self._read_lock = Lock()
        self._idle_shutdown_task: asyncio.Task | None = None
        self._idle_stop_in_progress = False
        self._runtime_overrides: dict[str, Any] = {}
        self._probe_timeout_sec = max(0.5, float(settings.camera_probe_timeout_sec))
        self._capture_timeout_sec = max(0.5, float(settings.camera_capture_timeout_sec))
        # 停止预算覆盖最长在途曝光，避免正常收敛帧超时导致无法回收。
        # Stop must outlive an in-flight long-AE convergence frame to permit native cleanup.
        self._stop_timeout_sec = max(4.0, self._capture_timeout_sec + 2.0)
        self._close_timeout_sec = 2.5
        self._stale_timeout_sec = max(
            0.5, float(settings.camera_frame_stale_timeout_sec)
        )
        self._idle_shutdown_sec = max(0.0, float(settings.camera_idle_shutdown_sec))
        self._health_error: str | None = None
        self._restart_required = False
        self._stream_started_at = 0.0
        self._logger = logging.getLogger(__name__)
        self._warmup_task: asyncio.Task | None = None
        self._shutdown_task: asyncio.Task | None = None
        self._shutting_down = False
        self._shutdown_complete = False
        self._resources = CameraResources()
        self._ownership = CameraOwnership(
            spawn=self._resources.spawn,
            check_accepting_work=self._check_accepting_work,
            on_active=self._cancel_idle_shutdown,
            on_inactive=self._schedule_idle_shutdown,
        )
        self._frames = CameraFramePipeline(
            settings=settings,
            resources=self._resources,
            get_camera=self.get_camera_instance,
            read_lock=self._read_lock,
            readiness=self.analysis_readiness,
            check_accepting_work=self._check_accepting_work,
            is_closing=lambda: self._shutting_down,
            quarantine=self._mark_restart_required,
            invalidate=self._invalidate_from_pipeline,
        )

    async def _invalidate_from_pipeline(self, reason: str) -> None:
        """流水线不能直接释放设备，必须取得生命周期锁 / Pipeline failures acquire the lifetime lock before releasing hardware."""
        async with self._control_lock:
            await self._invalidate_camera_locked(reason)

    def _check_accepting_work(self) -> None:
        """终止关闭后拒绝新工作，普通 stop 仍可重启 / Reject work after terminal shutdown, not reusable stop."""
        if self._shutting_down:
            raise RuntimeError(
                "相机运行服务正在关闭，需要重启服务 / Camera runtime is shutting down; service restart required"
            )

    def start_warmup(self) -> None:
        """统一持有启动预热任务，不阻塞服务就绪 / Own background warm-up without delaying service readiness."""
        self._check_accepting_work()
        if self._warmup_task is not None:
            return

        async def warm() -> None:
            try:
                await self.ensure_started()
                self._logger.info("相机预热完成 / Camera warm-up completed")
            except Exception as exc:
                self._logger.warning(
                    "相机预热未完成 / Camera warm-up incomplete: %s", exc
                )

        self._warmup_task = self._resources.spawn(warm())

    def begin_shutdown(self) -> None:
        """先关闭入口，再由 shutdown 有界回收 / Fence acquisition before bounded shutdown."""
        self._shutting_down = True
        self._ownership.begin_shutdown()
        self._cancel_idle_shutdown()

    async def shutdown(self, *, timeout_sec: float = 8.0) -> None:
        """幂等终止关闭；取消等待者不会打断实际清理 / Idempotent terminal close survives cancellation of a waiter."""
        if self._shutdown_task is None:
            self.begin_shutdown()
            self._shutdown_task = asyncio.create_task(self._shutdown_impl(timeout_sec))
            # 即使调用方断开，也读取后台关闭异常 / Observe shutdown failures after caller disconnect.
            self._shutdown_task.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
        await asyncio.shield(self._shutdown_task)

    async def _shutdown_resources(self) -> None:
        """等待预热/正在释放的空闲任务，再统一停止抓帧 / Settle warm-up and active idle closure before capture stop."""
        joining = {
            task
            for task in (self._warmup_task, self._idle_shutdown_task)
            if task is not None
        }
        if joining:
            await asyncio.gather(
                *(asyncio.shield(task) for task in joining), return_exceptions=True
            )
        await self.stop(force=True)
        if (
            self._camera is not None
            or self._restart_required
            or self._control_lock.locked()
        ):
            raise RuntimeError(
                self._health_error or "相机释放未确认 / Camera release unconfirmed"
            )
        if self._resources.background_tasks:
            await asyncio.gather(
                *(
                    asyncio.shield(task)
                    for task in tuple(self._resources.background_tasks)
                ),
                return_exceptions=True,
            )
        if self._resources.worker_futures:
            await asyncio.gather(
                *(
                    asyncio.shield(future)
                    for future in tuple(self._resources.worker_futures)
                ),
                return_exceptions=True,
            )
        self._ownership.clear_after_shutdown()

    async def _shutdown_impl(self, timeout_sec: float) -> None:
        """成功才确认释放；超时保留句柄并封闭执行器 / Confirm release only on success; quarantine timeouts and seal pools."""
        try:
            await asyncio.wait_for(
                self._shutdown_resources(), timeout=max(0.05, timeout_sec)
            )
            self._shutdown_complete = True
        except (Exception, asyncio.CancelledError) as exc:
            self._mark_restart_required(
                "相机终止关闭未完成，需要重启服务 / Camera terminal shutdown incomplete; service restart required"
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise RuntimeError(self._health_error) from exc
        finally:
            pending = {
                task for task in self._resources.background_tasks if not task.done()
            }
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.wait(pending, timeout=0.1)
            # 不在事件循环 join 卡住的原生线程；wait=False 不表示它已释放。
            # Never join a stuck native worker on the event loop; wait=False does not establish release.
            self._resources.close_executors()
            # 退出回执使用产品日志通道，默认非开发模式也必须可见 / Emit receipts through product logging, including non-development mode.
            event_logger.info(
                "camera_runtime_shutdown released={} pending_workers={} pending_tasks={}",
                self._shutdown_complete,
                sum(not future.done() for future in self._resources.worker_futures),
                sum(not task.done() for task in self._resources.background_tasks),
            )

    def _build_base_config(self) -> dict[str, Any]:
        from ogscope.config import get_settings

        return build_camera_config(
            get_settings(), self._runtime_overrides, self._capture_timeout_sec
        )

    def _create_camera_sync(self):
        from ogscope.platform.hardware.camera import create_camera

        config = self._build_base_config()
        camera = create_camera(config)
        if camera and camera.initialize():
            return camera
        if camera and getattr(camera, "requires_service_restart", False):
            self._mark_restart_required(
                "ISP 资源未能安全关闭，需重启服务 / ISP cleanup failed; service restart required"
            )
        return None

    def _camera_is_fresh(self) -> bool:
        """判断运行中的相机是否仍有新鲜帧 / Check whether a running camera is still fresh."""
        if self._restart_required:
            return False
        if self._camera is None or not getattr(self._camera, "is_capturing", False):
            return False
        if self._frames.health.last_success_mono <= 0:
            return False
        return (
            time.monotonic() - self._frames.health.last_success_mono
        ) <= self._stale_timeout_sec

    def _has_consumers(self) -> bool:
        return self._ownership.active

    def _cancel_idle_shutdown(self) -> None:
        # Hardware shutdown already owns the lock; let it finish before reopening.
        # 硬件关闭已取得锁时，让它完成后再重新开启，不能在释放资源中途取消。
        if self._idle_stop_in_progress:
            return
        task = self._idle_shutdown_task
        if task is not None and not task.done():
            task.cancel()
        self._idle_shutdown_task = None

    async def ensure_started(self, *, start_grabber: bool = False) -> None:
        """确保单相机进入采集并启动共享帧抓取 / Ensure capture and shared frame grabber."""
        self._check_accepting_work()
        self._cancel_idle_shutdown()
        if self._restart_required:
            raise RuntimeError(
                self._health_error
                or "相机需要重启服务后恢复 / Camera service restart required"
            )
        # 快速返回不能等待锁；锁显示空闲时仍可能有更早排队的关闭请求。
        # The fast return must not await a lock: an unlocked lock can have a queued closer.
        if (
            not start_grabber
            and self._camera_is_fresh()
            and not self._control_lock.locked()
        ):
            self._schedule_idle_shutdown()
            return
        async with self._control_lock:
            self._check_accepting_work()
            if self._restart_required:
                raise RuntimeError(
                    self._health_error
                    or "相机需要重启服务后恢复 / Camera service restart required"
                )
            if self._camera_is_fresh():
                if start_grabber:
                    await self._frames.start()
                self._schedule_idle_shutdown()
                return
            if self._camera is None:
                self._health_error = None
                self._restart_required = False
                self._frames.health.has_frame = False
                creation = self._resources.submit(None, self._create_camera_sync)

                def retain_created_handle(done: asyncio.Future) -> None:
                    # 取消启动也不能遗失仍在创建的句柄 / Retain a late handle even if startup was cancelled.
                    if not done.cancelled() and done.exception() is None:
                        self._camera = done.result()

                creation.add_done_callback(retain_created_handle)
                try:
                    self._camera = await asyncio.shield(creation)
                except asyncio.CancelledError:
                    self._mark_restart_required(
                        "相机初始化等待取消 / Camera initialization wait cancelled; restart required"
                    )
                    raise
                self._check_accepting_work()
                if self._camera is None:
                    self._health_error = "相机初始化失败 / Camera init failed"
                    raise RuntimeError(self._health_error)
            if not getattr(self._camera, "is_capturing", False):
                self.analysis_readiness.reset()
                ok = await self._resources.run(None, self._camera.start_capture)
                self._check_accepting_work()
                if not ok:
                    await self._invalidate_camera_locked(
                        "相机启动失败 / Camera start failed"
                    )
                    raise RuntimeError(self._health_error or "相机启动失败")
                self._stream_started_at = time.time()
            # Long 切换可能跳过临时手动帧；启动探测须覆盖驱动的长曝光等待预算。
            # Long transitions discard temporary manual frames; startup must allow the driver's frame budget.
            probe_budget = max(
                self._probe_timeout_sec,
                float(
                    getattr(
                        self._camera, "capture_timeout_sec", self._probe_timeout_sec
                    )
                ),
            )
            probe_ok = await self._resources.run(
                None, self._probe_stream_health_sync, probe_budget
            )
            self._check_accepting_work()
            if not probe_ok:
                await self._invalidate_camera_locked(
                    "相机无有效帧 / Camera produces no frames"
                )
                raise RuntimeError(self._health_error or "相机无有效帧")
            self._health_error = None
            self._frames.health.consecutive_failures = 0
            if start_grabber:
                await self._frames.start()
        self._schedule_idle_shutdown()

    async def acquire_preview_consumer(self) -> None:
        """注册预览消费者并启动共享编码 / Register a preview consumer."""
        self._ownership.acquire("preview")
        try:
            await self.ensure_started(start_grabber=True)
        except (Exception, asyncio.CancelledError):
            self._ownership.release("preview")
            raise

    async def release_preview_consumer(self) -> None:
        """释放预览消费者；最后一路离开时停止JPEG流水线 / Release preview consumer."""
        self._ownership.release("preview")
        if self._ownership.counts["preview"] == 0 and not self._shutting_down:
            async with self._control_lock:
                await self._frames.stop()
                self._frames.clear_preview()
            self._schedule_idle_shutdown()

    async def acquire_analysis_consumer(self) -> None:
        """分析会话持有相机，直到结束 / Hold the camera for the analysis session."""
        self._ownership.acquire("analysis")
        try:
            await self.ensure_started()
        except (Exception, asyncio.CancelledError):
            self._ownership.release("analysis")
            self._schedule_idle_shutdown()
            raise

    async def release_analysis_consumer(self) -> None:
        """结束分析后开始热驻留计时 / Start warm-idle timing after analysis ends."""
        self._ownership.release("analysis")
        self._schedule_idle_shutdown()

    async def acquire_recording_consumer(self) -> None:
        """注册录像消费者 / Register a recording consumer."""
        self._ownership.acquire("recording")
        try:
            await self.ensure_started()
        except (Exception, asyncio.CancelledError):
            self._ownership.release("recording")
            raise

    async def release_recording_consumer(self) -> None:
        """释放录像消费者 / Release a recording consumer."""
        self._ownership.release("recording")
        self._schedule_idle_shutdown()

    def update_operation_lease(
        self,
        *,
        lease_id: str | None = None,
        release: bool = False,
        ttl_seconds: float = 60.0,
    ) -> dict[str, Any]:
        """占用规则由独立组件维护 / Delegate lease policy to its owner."""
        return self._ownership.update_lease(
            lease_id=lease_id, release=release, ttl_seconds=ttl_seconds
        )

    def lifecycle_status(self) -> dict[str, Any]:
        """Expose ownership and readiness separately / 分别报告占用与分析就绪。"""
        phase = (
            "sleeping"
            if self._camera is None
            else "active" if self._has_consumers() else "warm_idle"
        )
        return {
            "phase": phase,
            "idle_shutdown_seconds": self._idle_shutdown_sec,
            "preview_consumers": self._ownership.counts["preview"],
            "analysis_consumers": self._ownership.counts["analysis"],
            "recording_consumers": self._ownership.counts["recording"],
            "operation_consumers": self._ownership.snapshot()["operation_consumers"],
            "analysis_readiness": self.analysis_readiness.snapshot(),
        }

    def _schedule_idle_shutdown(self) -> None:
        if self._shutting_down or self._has_consumers():
            return
        self._cancel_idle_shutdown()
        self._idle_shutdown_task = self._resources.spawn(
            self._idle_shutdown_after_delay()
        )

    async def _idle_shutdown_after_delay(self) -> None:
        """热驻留结束后释放相机 / Release camera after the warm-idle period."""
        current = asyncio.current_task()
        try:
            if self._idle_shutdown_sec > 0:
                await asyncio.sleep(self._idle_shutdown_sec)
            if not self._has_consumers():
                await self.stop()
        except asyncio.CancelledError:
            raise
        finally:
            if current is self._idle_shutdown_task:
                self._idle_shutdown_task = None

    async def stop(self, *, force: bool = False) -> None:
        """停止相机采集 / Stop camera capture."""
        if self._shutdown_complete:
            return
        if self._resources.executors_closed:
            raise RuntimeError(
                self._health_error or "相机服务已终止 / Camera runtime is shut down"
            )
        current = asyncio.current_task()
        if self._idle_shutdown_task is not current:
            self._cancel_idle_shutdown()
        acquired = False
        try:
            await asyncio.wait_for(self._control_lock.acquire(), timeout=2.0)
            acquired = True
        except asyncio.TimeoutError:
            self._logger.warning(
                "等待相机控制锁超时，跳过优雅停机 / Timed out waiting camera lock, skip graceful stop"
            )
            return
        try:
            # Recheck under the lifecycle lock: a new consumer may have arrived.
            # 在生命周期锁内复核，避免空闲关闭与新消费者启动竞争。
            if current is self._idle_shutdown_task and self._has_consumers():
                return
            if not force and self._ownership.blocks_stop:
                raise RuntimeError("Camera is in use / 相机仍被分析、校准或录像占用")
            self._idle_stop_in_progress = current is self._idle_shutdown_task
            if not await self._frames.stop():
                return
            if self._camera is None:
                self._restart_required = False
                return
            stop_ok, stop_timed_out = await self._run_lifecycle_step_locked(
                "stop", self._safe_stop_capture_sync, self._stop_timeout_sec
            )
            if stop_timed_out:
                return
            if not stop_ok:
                self._mark_restart_required(
                    "相机采集未能安全停止，需要重启服务 / "
                    "Camera capture did not stop safely; service restart required"
                )
                return
            close_ok, close_timed_out = await self._run_lifecycle_step_locked(
                "close", self._safe_close_camera_sync, self._close_timeout_sec
            )
            if close_timed_out or not close_ok:
                self._mark_restart_required(
                    "相机资源未能安全关闭，需要重启服务 / "
                    "Camera resources did not close safely; service restart required"
                )
                return
            self._clear_camera_state_locked(health_error=None)
        except asyncio.CancelledError:
            # 取消协程不会终止原生工作线程；释放控制锁前隔离仍持有的句柄。
            # Cancelling a coroutine cannot stop native workers; quarantine before unlocking.
            self._mark_restart_required(
                "相机关闭等待被取消，需要重启服务 / "
                "Camera close wait cancelled; service restart required"
            )
            raise
        finally:
            self._idle_stop_in_progress = False
            if acquired:
                self._control_lock.release()

    def _safe_stop_capture_sync(self) -> bool:
        camera = self._camera
        if camera is None:
            return True
        if not getattr(camera, "is_capturing", False):
            return True
        try:
            return bool(camera.stop_capture())
        except Exception as e:
            self._logger.warning(
                "停止相机捕获异常 / Failed to stop camera capture: %s", e
            )
            return False

    def _safe_close_camera_sync(self) -> bool:
        camera = self._camera
        if camera is None:
            return True
        try:
            # 驱动级 close() 负责释放 V4L2 fd；Picamera2 继续兼容内部对象关闭。
            # Driver-level close() releases V4L2 fds; Picamera2 keeps its inner close path.
            close_driver = getattr(camera, "close", None)
            if callable(close_driver):
                return close_driver() is not False
            inner_camera = getattr(camera, "camera", None)
            if inner_camera is not None and hasattr(inner_camera, "close"):
                inner_camera.close()
            return True
        except Exception as e:
            self._logger.warning("关闭相机资源异常 / Failed to close camera: %s", e)
            return False

    def _mark_restart_required(self, reason: str) -> None:
        """标记不可在进程内恢复的相机故障 / Mark a camera fault unsafe for in-process recovery."""
        self._restart_required = True
        self._health_error = reason
        self._logger.critical("camera_restart_required reason=%s", reason)

    def _clear_camera_state_locked(self, *, health_error: str | None) -> None:
        """确认原生释放后才能清理设备及帧状态 / Clear device/frame state only after confirmed native release."""
        self._camera = None
        self._restart_required = False
        self._health_error = health_error
        self._stream_started_at = 0.0
        self._frames.clear_after_close()

    async def _run_lifecycle_step_locked(
        self,
        operation_name: str,
        fn: Callable[[], bool],
        timeout_sec: float,
    ) -> tuple[bool, bool]:
        """在读锁内限时执行生命周期步骤 / Run a bounded lifecycle step under the read lock."""
        try:
            result = await asyncio.wait_for(
                self._resources.run(None, self._call_with_read_lock, fn),
                timeout=max(0.05, float(timeout_sec)),
            )
            return bool(result), False
        except asyncio.TimeoutError:
            self._mark_restart_required(
                f"相机{operation_name}超时，需要重启服务 / "
                f"Camera {operation_name} timed out; service restart required"
            )
            return False, True

    async def pause_grabber(self) -> None:
        """暂停共享抓帧任务（保留采集）/ Pause shared frame grabber only."""
        async with self._control_lock:
            await self._frames.stop()

    async def resume_grabber(self) -> None:
        """恢复共享抓帧任务 / Resume shared frame grabber."""
        self._check_accepting_work()
        async with self._control_lock:
            self._check_accepting_work()
            if self._camera is not None and getattr(
                self._camera, "is_capturing", False
            ):
                await self._frames.start()

    def _call_with_read_lock(self, fn: Callable[[], Any]) -> Any:
        """在读锁下执行阻塞操作，避免与抓帧并发 / Run blocking op under read lock."""
        with self._read_lock:
            return fn()

    async def reconfigure_camera(
        self,
        operation_name: str,
        fn: Callable[[], Any],
        *,
        timeout_sec: float = 10.0,
    ) -> Any:
        """受控重配置：同一临界区内停抓帧->改参->恢复 / Controlled reconfigure."""
        self._check_accepting_work()
        async with self._control_lock:
            self._check_accepting_work()
            t0 = time.time()
            if not await self._frames.stop():
                raise RuntimeError(
                    self._health_error
                    or "相机抓帧任务未能停止 / Camera grabber did not stop"
                )
            try:
                result = await asyncio.wait_for(
                    self._resources.run(None, self._call_with_read_lock, fn),
                    timeout=timeout_sec,
                )
                return result
            except asyncio.TimeoutError:
                self._mark_restart_required(
                    f"相机重配置超时（{operation_name}），需要重启服务 / "
                    f"Camera reconfiguration timed out ({operation_name}); service restart required"
                )
                raise
            finally:
                if (
                    not self._shutting_down
                    and not self._restart_required
                    and self._camera is not None
                    and getattr(self._camera, "is_capturing", False)
                ):
                    await self._frames.start()
                self._logger.info(
                    "camera_reconfigure_done op=%s cost_ms=%.2f",
                    operation_name,
                    (time.time() - t0) * 1000.0,
                )

    def _probe_stream_health_sync(self, timeout_sec: float) -> bool:
        """启动后探测是否能读到至少一帧 / Probe at least one frame after start."""
        deadline = time.time() + max(0.1, float(timeout_sec))
        while time.time() < deadline:
            # 健康探测也复用读帧工作线程 / Health probes reuse the capture worker too.
            frame = self._resources.capture_executor.submit(
                self._frames._read_frame_sync
            ).result()
            if frame is not None:
                return True
            time.sleep(0.05)
        return False

    async def _invalidate_camera_locked(self, reason: str) -> None:
        """标记相机离线并释放资源（需持有控制锁）/ Mark camera offline and release resources."""
        self._health_error = reason
        if self._frames.has_grabber and not await self._frames.stop():
            return
        _, stop_timed_out = await self._run_lifecycle_step_locked(
            "stop", self._safe_stop_capture_sync, self._stop_timeout_sec
        )
        if stop_timed_out:
            return
        close_ok, close_timed_out = await self._run_lifecycle_step_locked(
            "close", self._safe_close_camera_sync, self._close_timeout_sec
        )
        if close_timed_out or not close_ok:
            self._mark_restart_required(
                "相机失效后资源未能安全关闭，需要重启服务 / "
                "Camera invalidation could not release resources; service restart required"
            )
            return
        self._clear_camera_state_locked(health_error=reason)

    def get_camera_instance(self):
        """兼容接口：返回全局相机实例 / Compat accessor for global camera object."""
        return self._camera

    def ensure_camera_instance_sync(self):
        """兼容旧接口：仅返回当前实例，不再在锁外触发初始化 / Compat: return existing camera only."""
        return self._camera

    def attach_camera_instance(self, camera: Any) -> None:
        """注入现有相机实例（测试/兼容）/ Attach existing camera instance (tests/compat)."""
        self._check_accepting_work()
        self._camera = camera
        self._restart_required = False
        self._health_error = None

    async def status(self) -> dict[str, Any]:
        cam = self._camera
        configured_backend = self._build_base_config()["type"]
        if cam is None:
            return {
                "connected": False,
                "streaming": False,
                "error": self._health_error or "相机未初始化 / Camera not initialized",
                "restart_required": bool(self._restart_required),
                "configured_backend": configured_backend,
                "runtime_overrides": self._runtime_overrides,
            }
        initialized = bool(getattr(cam, "is_initialized", False))
        capturing = bool(getattr(cam, "is_capturing", False))
        # 空闲相机不会持续抓帧；一次成功探测即可证明流已建立，实际使用时 ensure_started 会再次探测。
        # Idle cameras do not grab continuously; one successful probe proves stream setup,
        # while ensure_started re-probes before the next real consumer uses it.
        has_successful_capture = self._frames.health.has_frame
        within_grace = (
            self._stream_started_at > 0
            and (time.time() - self._stream_started_at) <= self._probe_timeout_sec
        )
        offline = (
            self._restart_required
            or bool(self._health_error)
            or self._frames.offline
            or (capturing and not has_successful_capture and not within_grace)
        )
        if offline:
            reason = self._health_error
            if not reason:
                if self._frames.offline:
                    reason = "相机数据流中断 / Camera stream lost"
                else:
                    reason = "相机无有效帧 / Camera produces no frames"
            return {
                "connected": False,
                "streaming": False,
                "error": reason,
                "restart_required": bool(self._restart_required),
                "configured_backend": configured_backend,
                "runtime_overrides": self._runtime_overrides,
            }
        info = await asyncio.to_thread(cam.get_camera_info)
        return {
            "connected": initialized and capturing,
            "streaming": capturing and (has_successful_capture or within_grace),
            "restart_required": False,
            "info": info,
            "configured_backend": configured_backend,
            "runtime_overrides": self._runtime_overrides,
        }

    def update_runtime_overrides(self, updates: dict[str, Any]) -> None:
        """更新运行时覆盖参数（不落盘）/ Update runtime overrides (memory only)."""
        self._runtime_overrides.update(updates)

    def get_runtime_overrides(self) -> dict[str, Any]:
        """读取运行时覆盖参数 / Read runtime overrides."""
        return dict(self._runtime_overrides)

    def clear_runtime_overrides(self) -> None:
        """清空运行时覆盖参数 / Clear runtime overrides."""
        self._runtime_overrides.clear()

    @property
    def preview_jpeg_quality(self) -> int:
        """共享预览编码质量 / Shared preview encoding quality."""
        return self._frames.preview_jpeg_quality

    @property
    def preview_target_fps(self) -> int:
        """共享预览目标帧率 / Shared preview target frame rate."""
        return self._frames.preview_target_fps

    async def get_preview_frame(
        self, since_id: int | None = None, wait_timeout_sec: float = 0.8
    ) -> tuple[int, SharedFrame | None]:
        """取得设备后读取共享预览 / Acquire the device before reading shared preview."""
        await self.ensure_started(start_grabber=True)
        return await self._frames.get_preview_frame(since_id, wait_timeout_sec)

    async def get_raw_frame(self) -> tuple[Any, int, float]:
        """直读期间保持分析占用 / Hold analysis ownership during direct capture."""
        self._ownership.acquire("analysis")
        try:
            await self.ensure_started()
            return await self._frames.get_raw_frame()
        finally:
            self._ownership.release("analysis")
            self._schedule_idle_shutdown()

    async def reset_temporal_history(self, camera: Any) -> bool:
        """时间域重置仍使用共享帧身份屏障 / Temporal reset preserves the shared frame identity barrier."""
        return await self._frames.reset_temporal_history(camera)

    def get_current_capture_sequence(self) -> int:
        """只读取序号，不触发抓帧 / Read sequence without capturing."""
        return self._frames.get_current_capture_sequence()

    async def get_cached_frame_snapshot(self) -> SharedFrame | None:
        """读取缓存，不唤醒相机 / Read cache without waking the camera."""
        return await self._frames.get_cached_frame_snapshot()

    async def get_stream_jpeg(self, snap: SharedFrame, quality: int) -> bytes | None:
        """同帧质量变体仍由同一流水线编码 / Encode same-frame variants in one pipeline."""
        return await self._frames.get_stream_jpeg(snap, quality)

    async def encode_image(
        self, raw_frame: Any, image_format: str = "jpeg", quality: int = 75
    ) -> bytes | None:
        """非预览编码同样受统一资源管理 / Non-preview encoding shares resource ownership."""
        return await self._frames.encode_image(raw_frame, image_format, quality)

    @staticmethod
    def encode_frame(
        raw_frame: Any, image_format: str = "jpeg", quality: int = 75
    ) -> bytes | None:
        """兼容纯图像编码入口 / Preserve the pure image encoding entry."""
        return CameraFramePipeline.encode_frame(raw_frame, image_format, quality)

    def set_preview_fps(self, fps: int) -> int:
        """设置流水线节奏 / Set pipeline pacing."""
        return self._frames.set_preview_fps(fps)

    async def stream_metrics(self) -> dict[str, Any]:
        """组合占用与流水线遥测 / Compose ownership and pipeline telemetry."""
        return await self._frames.stream_metrics(
            {
                "preview_consumers": self._ownership.counts["preview"],
                "analysis_consumers": self._ownership.counts["analysis"],
                "recording_consumers": self._ownership.counts["recording"],
            }
        )


_camera_manager = CameraManager()


def get_camera_manager() -> CameraManager:
    """获取同一设备协调器 / Get the shared device coordinator."""
    return _camera_manager
