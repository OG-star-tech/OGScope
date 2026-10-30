"""共享帧、采集身份及编码流水线 / Shared frames, capture identity and encoding pipeline."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from ogscope.application.camera_resources import CameraResources
from ogscope.domain.camera.encoding import (
    EncodedImage,
    OpenCVEncoder,
    create_preview_encoder,
)
from ogscope.domain.camera.readiness import CaptureReadiness
from ogscope.domain.camera.runtime import SharedFrame

_STREAM_JPEG_VARIANT_LIMIT = 4
_STREAM_JPEG_VARIANT_BYTE_LIMIT = 1024 * 1024


@dataclass
class CaptureHealth:
    """采集健康独立于设备生命周期和占用 / Capture health is separate from device lifetime and ownership."""

    last_success_mono: float = 0.0
    has_frame: bool = False
    consecutive_failures: int = 0


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """Pixel identity travels with its timing, before encoding / 图像与采集身份、时间绑定，早于编码。"""

    frame: Any
    sequence: int
    timestamp: float
    monotonic: float
    epoch: int


class CameraFramePipeline:
    """持有帧与编码状态，硬件释放交给协调器 / Own frame/encoding state; delegate hardware release to the coordinator."""

    def __init__(
        self,
        *,
        settings: Any,
        resources: CameraResources,
        get_camera: Callable[[], Any],
        read_lock: Any,
        readiness: CaptureReadiness,
        check_accepting_work: Callable[[], None],
        quarantine: Callable[[str], None],
        invalidate: Callable[[str], Awaitable[None]],
    ) -> None:
        self.resources = resources
        self._get_camera = get_camera
        self._read_lock = read_lock
        self.analysis_readiness = readiness
        self._check_accepting_work = check_accepting_work
        self._mark_restart_required = quarantine
        self._invalidate = invalidate
        self._logger = logging.getLogger(__name__)
        self.health = CaptureHealth()
        self._frame_lock = Lock()
        self._grabber_task: asyncio.Task | None = None
        self._inflight_read_future: asyncio.Future | None = None
        self._inflight_encode_future: asyncio.Future | None = None
        self._frame_id = 0
        self._capture_sequence = 0
        self._capture_epoch = 0
        self._reset_pending = 0
        self._latest_raw_capture: CapturedFrame | None = None
        self._last_frame_duration_s = 0.0
        self._latest_raw = None
        self._latest_jpeg: bytes | None = None
        self._latest_ts = 0.0
        self._latest_w = 0
        self._latest_h = 0
        self._stream_jpeg_variants: dict[tuple[int, int], bytes] = {}
        self._stream_jpeg_tasks: dict[tuple[int, int], asyncio.Task] = {}
        self._jpeg_quality = int(settings.preview_jpeg_quality)
        self._preview_encoder = create_preview_encoder(
            getattr(settings, "preview_encoder", "auto"),
            hardware_device=getattr(settings, "preview_hardware_encoder_device", ""),
        )
        self._preview_encoder_requested = getattr(settings, "preview_encoder", "auto")
        self._preview_pipeline_enabled = bool(
            getattr(settings, "preview_pipeline_enabled", False)
        )
        self._last_jpeg_encoder = getattr(self._preview_encoder, "name", "opencv")
        self._last_jpeg_source_format = "RGB888"
        self._jpeg_encode_failures = 0
        self._target_fps = max(1, int(settings.shared_preview_fps))
        self._grabber_drain_timeout_sec = (
            max(0.5, float(settings.camera_capture_timeout_sec)) + 1.0
        )
        self._max_grab_failures = max(1, int(settings.camera_grab_failures_offline))
        self._capture_timestamps: deque[float] = deque(maxlen=120)
        self._jpeg_timestamps: deque[float] = deque(maxlen=120)
        self._jpeg_encode_ms: deque[float] = deque(maxlen=60)
        self._camera_read_ms: deque[float] = deque(maxlen=60)
        self._jpeg_variant_encode_ms: deque[float] = deque(maxlen=60)
        self._keep_raw_cache = bool(settings.keep_raw_cache)

    @property
    def preview_jpeg_quality(self) -> int:
        """共享抓帧 JPEG 质量（与缓存一致）/ Shared grabber JPEG quality (matches cache)."""
        return int(self._jpeg_quality)

    @property
    def preview_target_fps(self) -> int:
        """共享预览目标帧率 / Shared preview target FPS."""
        return int(self._target_fps)

    def _encode_preview_jpeg_sync(
        self, frame, *, quality: int | None = None, source_format: str | None = None
    ) -> EncodedImage | None:
        source_format = source_format or str(
            getattr(self._get_camera(), "output_pixel_format", None)
            or getattr(self._get_camera(), "pixel_format", None)
            or "RGB888"
        )
        jpeg_quality = int(self._jpeg_quality if quality is None else quality)
        try:
            encoded = self._preview_encoder.encode_jpeg(
                frame, quality=jpeg_quality, source_format=source_format
            )
            if encoded is not None:
                return encoded
        except Exception as exc:
            self._logger.debug("预览编码失败 / Preview encode failed: %s", exc)
        # TurboJPEG 或首选编码器异常时，当前帧回退 OpenCV；下次仍保留首选项便于热安装后生效
        # Fall back to OpenCV for this frame if the preferred encoder fails.
        try:
            return OpenCVEncoder().encode_jpeg(
                frame, quality=jpeg_quality, source_format=source_format
            )
        except Exception as exc:
            self._logger.debug(
                "OpenCV 回退编码失败 / OpenCV fallback encode failed: %s", exc
            )
            return None

    def _read_frame_sync(self):
        with self._read_lock:
            if self._get_camera() is None or not getattr(
                self._get_camera(), "is_capturing", False
            ):
                return None
            read_started = time.perf_counter()
            try:
                frame = self._get_camera().get_video_frame()
            finally:
                with self._frame_lock:
                    self._camera_read_ms.append(
                        (time.perf_counter() - read_started) * 1000.0
                    )
            if frame is not None:
                now = time.monotonic()
                self._capture_sequence += 1
                self.health.last_success_mono = now
                self.health.has_frame = True
                self._capture_timestamps.append(now)
                try:
                    info = self._get_camera().get_camera_info()
                except (
                    Exception
                ):  # Readiness can fall back to fresh frames / 就绪判断可降级为新帧证据。
                    info = {}
                duration = info.get("frame_duration_us") or info.get("exposure_us") or 0
                if isinstance(duration, (int, float)) and 0 < duration <= 60_000_000:
                    self._last_frame_duration_s = duration / 1_000_000
                self.analysis_readiness.observe(self._capture_sequence, info)
            return frame

    async def start(self) -> None:
        self._check_accepting_work()
        if self._grabber_task and not self._grabber_task.done():
            return
        self._grabber_task = self.resources.spawn(self._grabber_loop())

    async def stop(self) -> bool:
        if not self._grabber_task:
            return await self.drain()
        task = self._grabber_task
        if task is asyncio.current_task():
            self._grabber_task = None
            return await self.drain()
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=2.0)
        if not done:
            self._mark_restart_required(
                "抓帧任务未退出 / Capture task did not stop; service restart required"
            )
            return False
        drained = await self.drain()
        self._grabber_task = None
        return drained

    async def drain(self) -> bool:
        """关闭原生资源前收回所有工作线程 / Drain every worker before closing native resources."""
        inflight = self._inflight_read_future
        if inflight is not None and not inflight.done():
            try:
                # shield 防止 wait_for 取消仍在工作线程中收尾的读请求。
                # shield keeps wait_for from cancelling the read that is draining in a worker thread.
                await asyncio.wait_for(
                    asyncio.shield(inflight), timeout=self._grabber_drain_timeout_sec
                )
            except asyncio.TimeoutError:
                self._mark_restart_required(
                    "相机抓帧线程未能在超时内退出，需要重启服务 / "
                    "Camera read worker did not drain; service restart required"
                )
                self._grabber_task = None
                return False
            except Exception:
                pass
        if self._inflight_read_future is inflight:
            self._inflight_read_future = None
        encode = self._inflight_encode_future
        if encode is not None and not encode.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(encode), timeout=self._grabber_drain_timeout_sec
                )
            except asyncio.TimeoutError:
                self._mark_restart_required(
                    "编码线程未能退出 / Encoder worker did not drain"
                )
                self._grabber_task = None
                return False
            except Exception:
                pass
        self._inflight_encode_future = None
        # 普通停止同样不能越过取消后的启动、探测或直读工作 / Reusable stop must also drain cancelled startup, probes and direct reads.
        if self.resources.worker_futures:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *(
                            asyncio.shield(f)
                            for f in tuple(self.resources.worker_futures)
                        ),
                        return_exceptions=True,
                    ),
                    timeout=self._grabber_drain_timeout_sec,
                )
            except asyncio.TimeoutError:
                self._mark_restart_required(
                    "原生工作未完成 / Native workers did not drain; restart required"
                )
                return False
        close_encoder = getattr(self._preview_encoder, "close", None)
        if callable(close_encoder):
            # 关闭操作排在已提交编码后面，避免释放使用中的硬件缓冲。
            # Queue close after submitted encodes to avoid freeing buffers still in use.
            closed = self.resources.submit(self.resources.jpeg_executor, close_encoder)
            try:
                await asyncio.wait_for(
                    asyncio.shield(closed), timeout=self._grabber_drain_timeout_sec
                )
            except asyncio.TimeoutError:
                self._mark_restart_required(
                    "硬件编码器关闭超时 / Hardware encoder close timed out"
                )
                self._grabber_task = None
                return False
            except (OSError, BufferError) as exc:
                self._mark_restart_required(
                    f"Hardware encoder close failed / 硬件编码器关闭失败: {exc}"
                )
                self._grabber_task = None
                return False
        self._grabber_task = None
        return True

    def _read_preview_frame_sync(self):
        """在读帧完成时刻取时间，不使用晚到的编码时间 / Timestamp read completion, never delayed encoding completion."""
        with self._frame_lock:
            epoch = self._capture_epoch
        frame = self._read_frame_sync()
        # All reads run on the same capture executor / 所有读帧均使用同一个采集线程。
        return CapturedFrame(
            frame, self._capture_sequence, time.time(), time.monotonic(), epoch
        )

    async def reset_temporal_history(self, camera: Any) -> bool:
        """Invalidate cached/in-flight frames and serialize the driver reset / 失效缓存及在途图像，串行重置驱动。"""
        self._check_accepting_work()
        with self._frame_lock:
            self._capture_epoch += 1
            self._reset_pending += 1
            self._latest_raw = None
            self._latest_raw_capture = None

        def reset() -> bool:
            try:
                hook = getattr(camera, "begin_fresh_capture_epoch", None)
                return bool(hook()) if callable(hook) else False
            finally:
                with self._frame_lock:
                    # Also reject reads queued ahead of the reset / 同时拒绝排在重置前的读帧。
                    self._capture_epoch += 1
                    self._reset_pending -= 1
                    self._latest_raw = None
                    self._latest_raw_capture = None

        return await asyncio.shield(
            self.resources.submit(self.resources.capture_executor, reset)
        )

    async def _grabber_loop(self) -> None:
        prefetched = None
        try:
            while True:
                interval = 1.0 / float(max(1, self._target_fps))
                t0 = time.time()
                try:
                    read_future = prefetched or self.resources.submit(
                        self.resources.capture_executor, self._read_preview_frame_sync
                    )
                    prefetched = None
                    self._inflight_read_future = read_future
                    try:
                        captured = await asyncio.shield(read_future)
                        frame, capture_completed_ts = captured.frame, captured.timestamp
                    finally:
                        if (
                            read_future.done()
                            and self._inflight_read_future is read_future
                        ):
                            self._inflight_read_future = None
                    if frame is not None:
                        # Timestamp the completed sensor read before JPEG work so cached raw
                        # frames retain capture time rather than encoder completion time. /
                        # 在 JPEG 编码前记录传感器读帧完成时刻，避免缓存 raw 帧误用编码完成时间。
                        self.health.consecutive_failures = 0
                        if self._preview_pipeline_enabled:
                            read_ms = (
                                self._camera_read_ms[-1] if self._camera_read_ms else 0
                            )
                            jpeg_ms = (
                                self._jpeg_encode_ms[-1] if self._jpeg_encode_ms else 0
                            )
                            if read_ms + jpeg_ms >= interval * 1000:
                                # 最多预读一帧，不建立无界队列 / Prefetch at most one frame, never an unbounded queue.
                                prefetched = self.resources.submit(
                                    self.resources.capture_executor,
                                    self._read_preview_frame_sync,
                                )
                                self._inflight_read_future = prefetched
                        encode_t0 = time.perf_counter()
                        encode_future = self.resources.submit(
                            self.resources.jpeg_executor,
                            self._encode_preview_jpeg_sync,
                            frame,
                        )
                        self._inflight_encode_future = encode_future
                        encoded = await asyncio.shield(encode_future)
                        if self._inflight_encode_future is encode_future:
                            self._inflight_encode_future = None
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
                            current_epoch = (
                                captured.epoch == self._capture_epoch
                                and not self._reset_pending
                            )
                            self._latest_raw = (
                                frame
                                if self._keep_raw_cache and current_epoch
                                else None
                            )
                            self._latest_raw_capture = (
                                captured if self._latest_raw is not None else None
                            )
                            self._latest_jpeg = jpeg
                            self._stream_jpeg_variants.clear()
                            self._latest_ts = capture_completed_ts
                            self._latest_w = w
                            self._latest_h = h
                            self._last_jpeg_encoder = encoded.encoder
                            self._last_jpeg_source_format = encoded.source_format
                        now_mono = time.monotonic()
                        self._jpeg_timestamps.append(now_mono)
                        self._jpeg_encode_ms.append(encode_ms)
                    else:
                        self.health.consecutive_failures += 1
                        if self.health.consecutive_failures >= self._max_grab_failures:
                            self._logger.warning(
                                "连续抓帧失败，标记相机离线 / Consecutive grab failures, mark camera offline"
                            )
                            await self._invalidate(
                                "相机数据流中断 / Camera stream lost"
                            )
                            return
                except Exception as e:
                    self.health.consecutive_failures += 1
                    self._logger.error(f"共享抓帧循环异常 / Shared grabber error: {e}")
                    if self.health.consecutive_failures >= self._max_grab_failures:
                        await self._invalidate("相机数据流中断 / Camera stream lost")
                        return
                spent = time.time() - t0
                await asyncio.sleep(max(0.0, interval - spent))
        except asyncio.CancelledError:
            raise

    async def get_preview_frame(
        self, since_id: int | None = None, wait_timeout_sec: float = 0.8
    ) -> tuple[int, SharedFrame | None]:
        """读取预览帧；如未更新则返回 304 / Get preview frame; return 304 if unchanged."""
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
                        source_format=self._last_jpeg_source_format,
                    )
                    return 200, snap
            if time.time() >= deadline:
                return 503, None
            await asyncio.sleep(0.02)

    async def get_raw_frame(self) -> tuple[Any, int, float]:
        """读取带原始身份的共享或直读帧 / Read a shared or direct frame with its original identity."""
        with self._frame_lock:
            cached = self._latest_raw_capture
            max_age = max(
                0.5, 2 / max(1, self._target_fps), 2 * self._last_frame_duration_s
            )
            if (
                cached is not None
                and not self._reset_pending
                and cached.epoch == self._capture_epoch
                and 0 <= time.monotonic() - cached.monotonic <= max_age
            ):
                return cached.frame.copy(), cached.sequence, cached.timestamp
        # Preserve identity before another preview read can advance the global counter.
        # 在下一次预览读帧更新全局序号前保留当前图像身份。
        captured = await self.resources.run(
            self.resources.capture_executor, self._read_preview_frame_sync
        )
        with self._frame_lock:
            if (
                captured.frame is None
                or self._reset_pending
                or captured.epoch != self._capture_epoch
            ):
                raise RuntimeError("No fresh frame available / 尚无新鲜图像")
        return captured.frame, captured.sequence, captured.timestamp

    def get_current_capture_sequence(self) -> int:
        """当前抓帧序号，只读、绝不触发新抓帧 / Current capture sequence,
        read-only, never triggers a new capture.

        用于分析会话启动时建立新鲜度基线：get_raw_frame() 在没有常驻 raw
        缓存时（默认）会同步抓一整帧，可能要等到硬件抓帧循环当前正持有的
        那次曝光完成之后再抓一次全新的——曝光越长这个等待就越长，实测能
        把 analysis/start 拖到 8-10 秒以上，超过调用方的读超时，导致反复
        "启动失败又重试"，会话永远撑不到真正解算一帧。后台抓帧循环本来就
        在持续推进这个序号，只读它本身完全不需要等待任何硬件操作。
        Used to establish a freshness baseline when an analysis session
        starts. get_raw_frame() synchronously grabs a whole frame when
        there is no resident raw cache (the default) - it can end up
        waiting for whatever exposure the background grabber loop is
        currently holding, then grabbing another fresh one after that;
        longer exposures make this wait longer, and it was measured to
        stretch analysis/start past 8-10 seconds, past the caller's own
        read timeout, causing repeated start-failed-then-retry cycles that
        never let a session live long enough to actually solve a frame.
        The background grabber loop is already advancing this number on
        its own, so reading it needs no hardware operation at all.
        """
        return self._capture_sequence

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
                source_format=self._last_jpeg_source_format,
            )

    def _encode_stream_jpeg_sync(self, snap: SharedFrame, quality: int) -> bytes | None:
        """同一帧的 RAW 可用时优先使用，否则转码共享 JPEG；绝不重新抓帧。
        Use the same frame's RAW when retained, otherwise transcode its shared JPEG;
        never read the camera. A higher output quality cannot recover source JPEG detail.
        JPEG 源的细节上限不因提高输出质量而恢复。
        """
        frame = snap.raw_frame
        source_format = snap.source_format
        if frame is None:
            if snap.jpeg_frame is None:
                return None
            import cv2
            import numpy as np

            frame = cv2.imdecode(
                np.frombuffer(snap.jpeg_frame, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            source_format = "BGR888"
        if frame is None:
            return None
        encode_variant = getattr(self._preview_encoder, "encode_variant", None)
        if callable(encode_variant):
            encoded = encode_variant(
                frame, quality=quality, source_format=source_format
            )
        else:
            encoded = self._encode_preview_jpeg_sync(
                frame, quality=quality, source_format=source_format
            )
        return encoded.data if encoded is not None else None

    async def _encode_and_cache_stream_jpeg(
        self, snap: SharedFrame, quality: int
    ) -> bytes | None:
        key = (snap.frame_id, quality)
        try:
            self._check_accepting_work()
            started = time.perf_counter()
            encoded: bytes | None = await self.resources.run(
                self.resources.jpeg_executor,
                self._encode_stream_jpeg_sync,
                snap,
                quality,
            )
            self._jpeg_variant_encode_ms.append(
                (time.perf_counter() - started) * 1000.0
            )
            with self._frame_lock:
                if (
                    encoded is not None
                    and len(encoded) <= _STREAM_JPEG_VARIANT_BYTE_LIMIT
                    and snap.frame_id == self._frame_id
                    and snap.jpeg_frame is self._latest_jpeg
                ):
                    while self._stream_jpeg_variants and (
                        len(self._stream_jpeg_variants) >= _STREAM_JPEG_VARIANT_LIMIT
                        or sum(map(len, self._stream_jpeg_variants.values()))
                        + len(encoded)
                        > _STREAM_JPEG_VARIANT_BYTE_LIMIT
                    ):
                        self._stream_jpeg_variants.pop(
                            next(iter(self._stream_jpeg_variants))
                        )
                    self._stream_jpeg_variants[key] = encoded
            return encoded
        except Exception as exc:
            self._logger.debug(
                "共享 JPEG 转码失败 / Shared JPEG transcode failed: %s", exc
            )
            return None
        finally:
            self._stream_jpeg_tasks.pop(key, None)

    async def get_stream_jpeg(self, snap: SharedFrame, quality: int) -> bytes | None:
        """同帧同质量共享一次转码，断连不会取消其他消费者的编码。
        Share one encode per frame/quality; a disconnect cannot cancel another consumer's work.
        """
        self._check_accepting_work()
        quality = max(10, min(100, int(quality)))
        if quality == self.preview_jpeg_quality:
            return snap.jpeg_frame
        key = (snap.frame_id, quality)
        with self._frame_lock:
            encoded = self._stream_jpeg_variants.get(key)
        if encoded is not None:
            return encoded
        task = self._stream_jpeg_tasks.get(key)
        if task is None:
            task = self.resources.spawn(
                self._encode_and_cache_stream_jpeg(snap, quality)
            )
            self._stream_jpeg_tasks[key] = task
        return await asyncio.shield(task)

    async def encode_image(
        self, raw_frame: Any, image_format: str = "jpeg", quality: int = 75
    ) -> bytes | None:
        """非预览编码也由同一线程池收尾 / Drain non-preview encodes through the same owned pool."""
        self._check_accepting_work()
        encoded: bytes | None = await self.resources.run(
            self.resources.jpeg_executor,
            self.encode_frame,
            raw_frame,
            image_format,
            quality,
        )
        return encoded

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

    async def stream_metrics(self, consumers: dict[str, int]) -> dict[str, Any]:
        """返回预览运行指标 / Return preview runtime metrics."""
        cam = self._get_camera()
        info: dict[str, Any] = {}
        if cam is not None:
            info = await asyncio.to_thread(cam.get_camera_info)
        actual_capture_fps = self._rate(self._capture_timestamps)
        actual_preview_fps = self._rate(self._jpeg_timestamps)
        sensor_target_fps = float(info.get("fps", 0) or 0)
        exposure_us = int(
            info.get("actual_exposure_us", info.get("exposure_us", 0)) or 0
        )
        frame_duration_us = int(info.get("frame_duration_us", 0) or 0)
        preview_target_fps = float(self.preview_target_fps)
        effective_target_fps = (
            min(sensor_target_fps, preview_target_fps)
            if sensor_target_fps > 0
            else preview_target_fps
        )
        throttle_reason = None
        if actual_capture_fps > 0 and actual_capture_fps < effective_target_fps * 0.75:
            # 按有效预览目标核对真实曝光/周期，不把主动限帧误报为处理瓶颈。
            # Check duration against the effective target; intentional pacing is not a processing limit.
            long_frame = max(exposure_us, frame_duration_us) > (
                1_000_000.0 / (effective_target_fps * 0.75)
            )
            throttle_reason = (
                "auto_exposure_long"
                if bool(info.get("auto_exposure")) and long_frame
                else "processing_limit"
            )
        elif actual_capture_fps > 0 and preview_target_fps < sensor_target_fps:
            throttle_reason = "preview_rate_limit"
        with self._frame_lock:
            read_times = list(self._camera_read_ms)
            variant_bytes = sum(map(len, self._stream_jpeg_variants.values()))
        memory = self._memory_metrics()
        return {
            "sensor_target_fps": sensor_target_fps,
            "preview_target_fps": int(self._target_fps),
            "actual_capture_fps": round(actual_capture_fps, 2),
            "actual_preview_fps": round(actual_preview_fps, 2),
            "actual_exposure_us": exposure_us,
            "frame_duration_us": frame_duration_us,
            "preview_consumers": consumers["preview_consumers"],
            "analysis_consumers": consumers["analysis_consumers"],
            "recording_consumers": consumers["recording_consumers"],
            "jpeg_average_encode_ms": (
                round(sum(self._jpeg_encode_ms) / len(self._jpeg_encode_ms), 2)
                if self._jpeg_encode_ms
                else 0.0
            ),
            "jpeg_cached_bytes": len(self._latest_jpeg or b""),
            "camera_read_average_ms": (
                round(sum(read_times) / len(read_times), 2) if read_times else 0.0
            ),
            "jpeg_variant_average_encode_ms": (
                round(
                    sum(self._jpeg_variant_encode_ms)
                    / len(self._jpeg_variant_encode_ms),
                    2,
                )
                if self._jpeg_variant_encode_ms
                else 0.0
            ),
            "jpeg_variant_cached_bytes": variant_bytes,
            "preview_encoder": self._last_jpeg_encoder,
            "preview_encoder_requested": self._preview_encoder_requested,
            "preview_pipeline_enabled": self._preview_pipeline_enabled,
            "hardware_encoder_error": getattr(self._preview_encoder, "error", None),
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

    @property
    def has_grabber(self) -> bool:
        """是否仍持有抓帧任务 / Whether a capture task is still owned."""
        return self._grabber_task is not None

    @property
    def offline(self) -> bool:
        """连续失败达到原有离线阈值 / Consecutive failures reached the existing offline threshold."""
        return self.health.consecutive_failures >= self._max_grab_failures

    def clear_preview(self) -> None:
        """最后一个预览消费者离开后清空 JPEG / Clear JPEG after the last preview consumer leaves."""
        with self._frame_lock:
            self._latest_jpeg = None

    def clear_after_close(self) -> None:
        """只在确认原生关闭后清理缓存与新鲜度 / Reset caches and freshness only after confirmed native closure."""
        self.health = CaptureHealth()
        self.analysis_readiness.reset()
        with self._frame_lock:
            self._capture_epoch += 1
            self._latest_raw_capture = None
            self._latest_raw = None
            self._latest_jpeg = None
            self._stream_jpeg_variants.clear()
            self._latest_ts = 0.0
            self._latest_w = 0
            self._latest_h = 0
