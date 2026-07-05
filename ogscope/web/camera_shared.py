"""
统一相机管理与共享帧总线 / Unified camera manager and shared frame bus.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable

from ogscope.config import get_settings
from ogscope.domain.camera.encoding import (
    EncodedImage,
    OpenCVEncoder,
    create_preview_encoder,
)


@dataclass(slots=True)
class SharedFrame:
    """共享帧快照 / Shared frame snapshot."""

    frame_id: int
    timestamp: float
    raw_frame: Any | None
    jpeg_frame: bytes | None
    width: int
    height: int


class CameraManager:
    """全局单相机控制器（控制面+数据面）/ Global single-camera controller."""

    def __init__(self) -> None:
        self._camera = None
        self._control_lock = asyncio.Lock()
        self._read_lock = Lock()
        self._frame_lock = Lock()
        self._grabber_task: asyncio.Task | None = None
        self._idle_shutdown_task: asyncio.Task | None = None
        self._frame_id = 0
        self._capture_sequence = 0
        self._latest_raw = None
        self._latest_jpeg: bytes | None = None
        self._latest_ts = 0.0
        self._latest_w = 0
        self._latest_h = 0
        self._runtime_overrides: dict[str, Any] = {}
        settings = get_settings()
        self._jpeg_quality = int(settings.preview_jpeg_quality)
        self._preview_encoder = create_preview_encoder(
            getattr(settings, "preview_encoder", "auto")
        )
        self._last_jpeg_encoder = getattr(self._preview_encoder, "name", "opencv")
        self._last_jpeg_source_format = "RGB888"
        self._jpeg_encode_failures = 0
        self._target_fps = max(1, int(settings.shared_preview_fps))
        self._probe_timeout_sec = max(0.5, float(settings.camera_probe_timeout_sec))
        self._stale_timeout_sec = max(
            0.5, float(settings.camera_frame_stale_timeout_sec)
        )
        self._idle_shutdown_sec = max(0.0, float(settings.camera_idle_shutdown_sec))
        self._max_grab_failures = max(1, int(settings.camera_grab_failures_offline))
        self._health_error: str | None = None
        self._consecutive_grab_failures = 0
        self._stream_started_at = 0.0
        self._last_capture_success_mono = 0.0
        self._preview_consumers = 0
        self._analysis_consumers = 0
        self._recording_consumers = 0
        self._capture_timestamps: deque[float] = deque(maxlen=120)
        self._jpeg_timestamps: deque[float] = deque(maxlen=120)
        self._jpeg_encode_ms: deque[float] = deque(maxlen=60)
        self._jpeg_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ogscope-jpeg"
        )
        # 是否常驻 raw 帧缓存；默认关闭以降低内存占用（分析路径可同步抓帧）
        # Whether to retain raw frame cache; default off to reduce RAM (analysis can sync-grab).
        self._keep_raw_cache = bool(settings.keep_raw_cache)
        self._logger = logging.getLogger(__name__)

    @property
    def preview_jpeg_quality(self) -> int:
        """共享抓帧 JPEG 质量（与缓存一致）/ Shared grabber JPEG quality (matches cache)."""
        return int(self._jpeg_quality)

    @property
    def preview_target_fps(self) -> int:
        """共享预览目标帧率 / Shared preview target FPS."""
        return int(self._target_fps)

    def _build_base_config(self) -> dict[str, Any]:
        from ogscope.config import get_settings

        settings = get_settings()
        base = {
            "type": settings.camera_type,
            "device": getattr(settings, "camera_device", "/dev/video0"),
            "backend": getattr(settings, "camera_backend", "opencv"),
            "v4l2_sensor_subdev": getattr(settings, "camera_v4l2_sensor_subdev", "/dev/v4l-subdev1"),
            "pixel_format": getattr(settings, "camera_pixel_format", "RGB3"),
            "width": settings.camera_width,
            "height": settings.camera_height,
            "fps": max(1, int(getattr(settings, "camera_fps", 5) or 5)),
            "exposure_us": settings.camera_exposure,
            "analogue_gain": settings.camera_gain,
            "auto_exposure": True,
            "ae_polar_preset": settings.camera_ae_polar_preset,
            "ae_exposure_value": settings.camera_ae_exposure_value,
            "auto_exposure_max_us": getattr(
                settings, "camera_auto_exposure_max_us", 2_000_000
            ),
            "ae_flicker_mode": getattr(settings, "camera_ae_flicker_mode", "off"),
            "noise_reduction_mode": getattr(
                settings, "camera_noise_reduction_mode", "fast"
            ),
            "lores_enabled": bool(getattr(settings, "camera_lores_enabled", True)),
            "lores_width": int(getattr(settings, "camera_lores_width", 320)),
            "lores_height": int(getattr(settings, "camera_lores_height", 240)),
            "lores_format": getattr(settings, "camera_lores_format", "YUV420"),
            "rotation": 180,
            "flip_horizontal": bool(getattr(settings, "camera_flip_horizontal", False)),
            "flip_vertical": bool(getattr(settings, "camera_flip_vertical", False)),
            "sampling_mode": getattr(settings, "camera_sampling_mode", "native"),
            "noise_reduction": 1,
            "white_balance_mode": getattr(
                settings, "camera_white_balance_mode", "auto"
            ),
            "white_balance_gain_r": getattr(
                settings, "camera_white_balance_gain_r", 1.0
            ),
            "white_balance_gain_b": getattr(
                settings, "camera_white_balance_gain_b", 1.0
            ),
            "contrast": 1.0,
            "brightness": 0.0,
            "saturation": 1.0,
            "sharpness": 1.0,
            "night_mode": bool(getattr(settings, "camera_night_mode", False)),
            "color_mode": "color",
        }
        return {**base, **self._runtime_overrides}

    def _create_camera_sync(self):
        from ogscope.platform.hardware.camera import create_camera

        config = self._build_base_config()
        camera = create_camera(config)
        if camera and camera.initialize():
            return camera
        return None

    def _encode_preview_jpeg_sync(self, frame) -> EncodedImage | None:
        source_format = str(
            getattr(self._camera, "output_pixel_format", None)
            or getattr(self._camera, "pixel_format", None)
            or "RGB888"
        )
        try:
            encoded = self._preview_encoder.encode_jpeg(
                frame, quality=int(self._jpeg_quality), source_format=source_format
            )
            if encoded is not None:
                return encoded
        except Exception as exc:
            self._logger.debug("预览编码失败 / Preview encode failed: %s", exc)
        # TurboJPEG 或首选编码器异常时，当前帧回退 OpenCV；下次仍保留首选项便于热安装后生效
        # Fall back to OpenCV for this frame if the preferred encoder fails.
        try:
            return OpenCVEncoder().encode_jpeg(
                frame, quality=int(self._jpeg_quality), source_format=source_format
            )
        except Exception as exc:
            self._logger.debug("OpenCV 回退编码失败 / OpenCV fallback encode failed: %s", exc)
            return None

    def _read_frame_sync(self):
        with self._read_lock:
            if self._camera is None or not getattr(self._camera, "is_capturing", False):
                return None
            frame = self._camera.get_video_frame()
            if frame is not None:
                now = time.monotonic()
                self._capture_sequence += 1
                self._last_capture_success_mono = now
                self._capture_timestamps.append(now)
            return frame

    def _camera_is_fresh(self) -> bool:
        """判断运行中的相机是否仍有新鲜帧 / Check whether a running camera is still fresh."""
        if self._camera is None or not getattr(self._camera, "is_capturing", False):
            return False
        if self._last_capture_success_mono <= 0:
            return False
        return (
            time.monotonic() - self._last_capture_success_mono
        ) <= self._stale_timeout_sec

    def _has_consumers(self) -> bool:
        return (
            self._preview_consumers
            + self._analysis_consumers
            + self._recording_consumers
        ) > 0

    def _cancel_idle_shutdown(self) -> None:
        task = self._idle_shutdown_task
        if task is not None and not task.done():
            task.cancel()
        self._idle_shutdown_task = None

    async def ensure_started(self, *, start_grabber: bool = False) -> None:
        """确保单相机进入采集并启动共享帧抓取 / Ensure capture and shared frame grabber."""
        self._cancel_idle_shutdown()
        if self._camera_is_fresh():
            if start_grabber:
                async with self._control_lock:
                    await self._ensure_grabber_locked()
            return
        async with self._control_lock:
            if self._camera_is_fresh():
                if start_grabber:
                    await self._ensure_grabber_locked()
                return
            if self._camera is None:
                self._health_error = None
                self._camera = await asyncio.to_thread(self._create_camera_sync)
                if self._camera is None:
                    self._health_error = "相机初始化失败 / Camera init failed"
                    raise RuntimeError(self._health_error)
            if not getattr(self._camera, "is_capturing", False):
                ok = await asyncio.to_thread(self._camera.start_capture)
                if not ok:
                    await self._invalidate_camera_locked(
                        "相机启动失败 / Camera start failed"
                    )
                    raise RuntimeError(self._health_error or "相机启动失败")
                self._stream_started_at = time.time()
            probe_ok = await asyncio.to_thread(
                self._probe_stream_health_sync, self._probe_timeout_sec
            )
            if not probe_ok:
                await self._invalidate_camera_locked(
                    "相机无有效帧 / Camera produces no frames"
                )
                raise RuntimeError(self._health_error or "相机无有效帧")
            self._health_error = None
            self._consecutive_grab_failures = 0
            if start_grabber:
                await self._ensure_grabber_locked()

    async def acquire_preview_consumer(self) -> None:
        """注册预览消费者并启动共享编码 / Register a preview consumer."""
        self._preview_consumers += 1
        try:
            await self.ensure_started(start_grabber=True)
        except Exception:
            self._preview_consumers = max(0, self._preview_consumers - 1)
            raise

    async def release_preview_consumer(self) -> None:
        """释放预览消费者；最后一路离开时停止JPEG流水线 / Release preview consumer."""
        self._preview_consumers = max(0, self._preview_consumers - 1)
        if self._preview_consumers == 0:
            async with self._control_lock:
                await self._stop_grabber_locked()
                with self._frame_lock:
                    self._latest_jpeg = None
            self._schedule_idle_shutdown()

    async def acquire_recording_consumer(self) -> None:
        """注册录像消费者 / Register a recording consumer."""
        self._recording_consumers += 1
        try:
            await self.ensure_started()
        except Exception:
            self._recording_consumers = max(0, self._recording_consumers - 1)
            raise

    async def release_recording_consumer(self) -> None:
        """释放录像消费者 / Release a recording consumer."""
        self._recording_consumers = max(0, self._recording_consumers - 1)
        self._schedule_idle_shutdown()

    def _schedule_idle_shutdown(self) -> None:
        if self._has_consumers():
            return
        self._cancel_idle_shutdown()
        self._idle_shutdown_task = asyncio.create_task(self._idle_shutdown_after_delay())

    async def _idle_shutdown_after_delay(self) -> None:
        """热驻留结束后释放相机 / Release camera after the warm-idle period."""
        try:
            if self._idle_shutdown_sec > 0:
                await asyncio.sleep(self._idle_shutdown_sec)
            if not self._has_consumers():
                await self.stop()
        except asyncio.CancelledError:
            raise
        finally:
            if asyncio.current_task() is self._idle_shutdown_task:
                self._idle_shutdown_task = None

    async def stop(self) -> None:
        """停止相机采集 / Stop camera capture."""
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
            await self._stop_grabber_locked()
            if self._camera is None:
                return
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(self._safe_stop_capture_sync), timeout=4.0
                )
            except asyncio.TimeoutError:
                self._logger.warning(
                    "相机停止超时，继续执行退出流程 / Camera stop timed out, continue shutdown"
                )
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(self._safe_close_camera_sync), timeout=2.5
                )
            except asyncio.TimeoutError:
                self._logger.warning(
                    "相机关闭超时，继续执行退出流程 / Camera close timed out, continue shutdown"
                )
            self._camera = None
            self._last_capture_success_mono = 0.0
            with self._frame_lock:
                self._latest_raw = None
                self._latest_jpeg = None
                self._latest_ts = 0.0
                self._latest_w = 0
                self._latest_h = 0
        finally:
            if acquired:
                self._control_lock.release()

    def _safe_stop_capture_sync(self) -> None:
        camera = self._camera
        if camera is None:
            return
        if not getattr(camera, "is_capturing", False):
            return
        try:
            camera.stop_capture()
        except Exception as e:
            self._logger.warning(
                "停止相机捕获异常 / Failed to stop camera capture: %s", e
            )

    def _safe_close_camera_sync(self) -> None:
        camera = self._camera
        if camera is None:
            return
        try:
            inner_camera = getattr(camera, "camera", None)
            if inner_camera is not None and hasattr(inner_camera, "close"):
                inner_camera.close()
        except Exception as e:
            self._logger.warning("关闭相机资源异常 / Failed to close camera: %s", e)

    async def pause_grabber(self) -> None:
        """暂停共享抓帧任务（保留采集）/ Pause shared frame grabber only."""
        async with self._control_lock:
            await self._stop_grabber_locked()

    async def resume_grabber(self) -> None:
        """恢复共享抓帧任务 / Resume shared frame grabber."""
        async with self._control_lock:
            if self._camera is not None and getattr(
                self._camera, "is_capturing", False
            ):
                await self._ensure_grabber_locked()

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
        async with self._control_lock:
            t0 = time.time()
            await self._stop_grabber_locked()
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._call_with_read_lock, fn),
                    timeout=timeout_sec,
                )
                return result
            finally:
                if self._camera is not None and getattr(
                    self._camera, "is_capturing", False
                ):
                    await self._ensure_grabber_locked()
                self._logger.info(
                    "camera_reconfigure_done op=%s cost_ms=%.2f",
                    operation_name,
                    (time.time() - t0) * 1000.0,
                )

    def _probe_stream_health_sync(self, timeout_sec: float) -> bool:
        """启动后探测是否能读到至少一帧 / Probe at least one frame after start."""
        deadline = time.time() + max(0.1, float(timeout_sec))
        while time.time() < deadline:
            frame = self._read_frame_sync()
            if frame is not None:
                return True
            time.sleep(0.05)
        return False

    async def _invalidate_camera_locked(self, reason: str) -> None:
        """标记相机离线并释放资源（需持有控制锁）/ Mark camera offline and release resources."""
        self._health_error = reason
        current = asyncio.current_task()
        if self._grabber_task and self._grabber_task is not current:
            await self._stop_grabber_locked()
        elif self._grabber_task is current:
            self._grabber_task = None
        await asyncio.to_thread(self._safe_stop_capture_sync)
        await asyncio.to_thread(self._safe_close_camera_sync)
        self._camera = None
        self._consecutive_grab_failures = 0
        self._stream_started_at = 0.0
        with self._frame_lock:
            self._latest_raw = None
            self._latest_jpeg = None
            self._latest_ts = 0.0
            self._latest_w = 0
            self._latest_h = 0

    async def _ensure_grabber_locked(self) -> None:
        if self._grabber_task and not self._grabber_task.done():
            return
        self._grabber_task = asyncio.create_task(self._grabber_loop())

    async def _stop_grabber_locked(self) -> None:
        if not self._grabber_task:
            return
        self._grabber_task.cancel()
        try:
            await asyncio.wait_for(self._grabber_task, timeout=2.0)
        except asyncio.CancelledError:
            # 抓帧任务被取消属于正常停止流程，不应向上抛出
            # Task cancellation is expected during graceful stop.
            pass
        except Exception:
            pass
        self._grabber_task = None

    async def _grabber_loop(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                interval = 1.0 / float(max(1, self._target_fps))
                t0 = time.time()
                try:
                    frame = await asyncio.to_thread(self._read_frame_sync)
                    if frame is not None:
                        self._consecutive_grab_failures = 0
                        encode_t0 = time.perf_counter()
                        encoded = await loop.run_in_executor(
                            self._jpeg_executor, self._encode_preview_jpeg_sync, frame
                        )
                        encode_ms = (time.perf_counter() - encode_t0) * 1000.0
                        if encoded is None:
                            self._jpeg_encode_failures += 1
                            await asyncio.sleep(max(0.0, interval - (time.time() - t0)))
                            continue
                        jpeg = encoded.data
                        h = int(getattr(frame, "shape", [0, 0])[0] or 0)
                        w = int(getattr(frame, "shape", [0, 0])[1] or 0)
                        with self._frame_lock:
                            self._frame_id += 1
                            # 默认不保留 raw，避免与 JPEG 双份常驻；需要时设 OGSCOPE_KEEP_RAW_CACHE=1
                            # By default do not retain raw to avoid dual large buffers; set env to keep.
                            self._latest_raw = frame if self._keep_raw_cache else None
                            self._latest_jpeg = jpeg
                            self._latest_ts = time.time()
                            self._latest_w = w
                            self._latest_h = h
                            self._last_jpeg_encoder = encoded.encoder
                            self._last_jpeg_source_format = encoded.source_format
                        now_mono = time.monotonic()
                        self._jpeg_timestamps.append(now_mono)
                        self._jpeg_encode_ms.append(encode_ms)
                    else:
                        self._consecutive_grab_failures += 1
                        if self._consecutive_grab_failures >= self._max_grab_failures:
                            self._logger.warning(
                                "连续抓帧失败，标记相机离线 / Consecutive grab failures, mark camera offline"
                            )
                            async with self._control_lock:
                                await self._invalidate_camera_locked(
                                    "相机数据流中断 / Camera stream lost"
                                )
                            return
                except Exception as e:
                    self._consecutive_grab_failures += 1
                    self._logger.error(f"共享抓帧循环异常 / Shared grabber error: {e}")
                    if self._consecutive_grab_failures >= self._max_grab_failures:
                        async with self._control_lock:
                            await self._invalidate_camera_locked(
                                "相机数据流中断 / Camera stream lost"
                            )
                        return
                spent = time.time() - t0
                await asyncio.sleep(max(0.0, interval - spent))
        except asyncio.CancelledError:
            raise

    def get_camera_instance(self):
        """兼容接口：返回全局相机实例 / Compat accessor for global camera object."""
        return self._camera

    def ensure_camera_instance_sync(self):
        """兼容旧接口：仅返回当前实例，不再在锁外触发初始化 / Compat: return existing camera only."""
        return self._camera

    def attach_camera_instance(self, camera: Any) -> None:
        """注入现有相机实例（测试/兼容）/ Attach existing camera instance (tests/compat)."""
        self._camera = camera

    async def status(self) -> dict[str, Any]:
        cam = self._camera
        if cam is None:
            return {
                "connected": False,
                "streaming": False,
                "error": self._health_error or "相机未初始化 / Camera not initialized",
                "runtime_overrides": self._runtime_overrides,
            }
        initialized = bool(getattr(cam, "is_initialized", False))
        capturing = bool(getattr(cam, "is_capturing", False))
        has_frames = self._frame_id > 0
        within_grace = (
            self._stream_started_at > 0
            and (time.time() - self._stream_started_at) <= self._probe_timeout_sec
        )
        offline = (
            bool(self._health_error)
            or self._consecutive_grab_failures >= self._max_grab_failures
            or (capturing and not has_frames and not within_grace)
        )
        if offline:
            reason = self._health_error
            if not reason:
                if self._consecutive_grab_failures >= self._max_grab_failures:
                    reason = "相机数据流中断 / Camera stream lost"
                else:
                    reason = "相机无有效帧 / Camera produces no frames"
            return {
                "connected": False,
                "streaming": False,
                "error": reason,
                "runtime_overrides": self._runtime_overrides,
            }
        info = await asyncio.to_thread(cam.get_camera_info)
        return {
            "connected": initialized and capturing,
            "streaming": capturing and (has_frames or within_grace),
            "info": info,
            "runtime_overrides": self._runtime_overrides,
        }

    async def get_preview_frame(
        self, since_id: int | None = None, wait_timeout_sec: float = 0.8
    ) -> tuple[int, SharedFrame | None]:
        """读取预览帧；如未更新则返回 304 / Get preview frame; return 304 if unchanged."""
        await self.ensure_started(start_grabber=True)
        deadline = time.time() + max(0.0, float(wait_timeout_sec))
        while True:
            with self._frame_lock:
                if self._frame_id > 0 and self._latest_jpeg is not None:
                    if since_id is not None and since_id == self._frame_id:
                        return 304, None
                    snap = SharedFrame(
                        frame_id=self._frame_id,
                        timestamp=self._latest_ts,
                        raw_frame=self._latest_raw,
                        jpeg_frame=self._latest_jpeg,
                        width=self._latest_w,
                        height=self._latest_h,
                    )
                    return 200, snap
            if time.time() >= deadline:
                return 503, None
            await asyncio.sleep(0.02)

    async def get_raw_frame(self) -> tuple[Any, int, float]:
        """读取分析帧 / Get frame for analysis."""
        self._analysis_consumers += 1
        try:
            await self.ensure_started()
            with self._frame_lock:
                if self._latest_raw is not None:
                    return (
                        self._latest_raw.copy(),
                        self._capture_sequence,
                        self._latest_ts,
                    )
            # 无常驻 raw 时同步抓一帧，供解算使用 / Sync-grab without retaining raw.
            frame = await asyncio.to_thread(self._read_frame_sync)
            if frame is None:
                raise RuntimeError("无可用视频帧 / No frame available")
            with self._frame_lock:
                fid = self._capture_sequence
                ts = time.time()
            return frame, fid, ts
        finally:
            self._analysis_consumers = max(0, self._analysis_consumers - 1)
            self._schedule_idle_shutdown()

    async def get_cached_frame_snapshot(self) -> SharedFrame | None:
        """读取当前缓存帧快照（不触发 ensure）/ Read cached snapshot without ensure."""
        with self._frame_lock:
            if self._frame_id <= 0:
                return None
            return SharedFrame(
                frame_id=self._frame_id,
                timestamp=self._latest_ts,
                raw_frame=self._latest_raw,
                jpeg_frame=self._latest_jpeg,
                width=self._latest_w,
                height=self._latest_h,
            )

    @staticmethod
    def encode_frame(
        raw_frame: Any, image_format: str = "jpeg", quality: int = 75
    ) -> bytes | None:
        """将原始帧编码为图像字节 / Encode raw frame to image bytes."""
        try:
            if image_format.lower() == "png":
                return OpenCVEncoder().encode_png(raw_frame, source_format="RGB888")
            encoded = create_preview_encoder("auto").encode_jpeg(
                raw_frame,
                quality=int(max(10, min(100, quality))),
                source_format="RGB888",
            )
            return encoded.data if encoded is not None else None
        except Exception:
            return None

    def update_runtime_overrides(self, updates: dict[str, Any]) -> None:
        """更新运行时覆盖参数（不落盘）/ Update runtime overrides (memory only)."""
        self._runtime_overrides.update(updates)

    def set_preview_fps(self, fps: int) -> int:
        """独立更新共享预览帧率 / Independently update shared preview FPS."""
        self._target_fps = max(1, min(30, int(fps)))
        return self._target_fps

    @staticmethod
    def _rate(values: deque[float], window_sec: float = 3.0) -> float:
        now = time.monotonic()
        recent = [v for v in values if now - v <= window_sec]
        if len(recent) < 2:
            return 0.0
        span = recent[-1] - recent[0]
        return 0.0 if span <= 0 else (len(recent) - 1) / span

    async def stream_metrics(self) -> dict[str, Any]:
        """返回预览运行指标 / Return preview runtime metrics."""
        cam = self._camera
        info: dict[str, Any] = {}
        if cam is not None:
            info = await asyncio.to_thread(cam.get_camera_info)
        actual_capture_fps = self._rate(self._capture_timestamps)
        actual_preview_fps = self._rate(self._jpeg_timestamps)
        sensor_target_fps = float(info.get("fps", 0) or 0)
        exposure_us = int(info.get("actual_exposure_us", info.get("exposure_us", 0)) or 0)
        frame_duration_us = int(info.get("frame_duration_us", 0) or 0)
        throttle_reason = None
        if (
            bool(info.get("auto_exposure"))
            and sensor_target_fps > 0
            and actual_capture_fps > 0
            and actual_capture_fps < sensor_target_fps * 0.75
        ):
            throttle_reason = "auto_exposure_long"
        memory = self._memory_metrics()
        return {
            "sensor_target_fps": sensor_target_fps,
            "preview_target_fps": int(self._target_fps),
            "actual_capture_fps": round(actual_capture_fps, 2),
            "actual_preview_fps": round(actual_preview_fps, 2),
            "actual_exposure_us": exposure_us,
            "frame_duration_us": frame_duration_us,
            "preview_consumers": int(self._preview_consumers),
            "analysis_consumers": int(self._analysis_consumers),
            "recording_consumers": int(self._recording_consumers),
            "jpeg_average_encode_ms": round(
                sum(self._jpeg_encode_ms) / len(self._jpeg_encode_ms), 2
            )
            if self._jpeg_encode_ms
            else 0.0,
            "jpeg_cached_bytes": len(self._latest_jpeg or b""),
            "preview_encoder": self._last_jpeg_encoder,
            "jpeg_encode_failures": int(self._jpeg_encode_failures),
            "jpeg_source_format": self._last_jpeg_source_format,
            "camera_driver": str(info.get("driver", "")),
            "camera_backend": str(info.get("backend", "")),
            "lores_enabled": bool(info.get("lores_enabled", False)),
            "lores_available": bool(info.get("lores_available", False)),
            "lores_width": int(info.get("lores_width", 0) or 0),
            "lores_height": int(info.get("lores_height", 0) or 0),
            "lores_format": str(info.get("lores_format", "")),
            "throttle_reason": throttle_reason,
            **memory,
        }

    @staticmethod
    def _memory_metrics() -> dict[str, int]:
        """读取轻量进程与CMA指标 / Read lightweight process and CMA metrics."""
        rss_kb = 0
        swap_kb = 0
        cma_free_kb = 0
        try:
            with open(f"/proc/{os.getpid()}/status", encoding="utf-8") as status_file:
                for line in status_file:
                    if line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
                    elif line.startswith("VmSwap:"):
                        swap_kb = int(line.split()[1])
        except (OSError, ValueError, IndexError):
            pass
        try:
            with open("/proc/meminfo", encoding="utf-8") as meminfo_file:
                for line in meminfo_file:
                    if line.startswith("CmaFree:"):
                        cma_free_kb = int(line.split()[1])
                        break
        except (OSError, ValueError, IndexError):
            pass
        return {
            "process_rss_kb": rss_kb,
            "process_swap_kb": swap_kb,
            "cma_free_kb": cma_free_kb,
        }

    def get_runtime_overrides(self) -> dict[str, Any]:
        """读取运行时覆盖参数 / Read runtime overrides."""
        return dict(self._runtime_overrides)

    def clear_runtime_overrides(self) -> None:
        """清空运行时覆盖参数 / Clear runtime overrides."""
        self._runtime_overrides.clear()


_camera_manager = CameraManager()


def get_camera_manager() -> CameraManager:
    """获取全局相机管理器 / Get global camera manager."""
    return _camera_manager
