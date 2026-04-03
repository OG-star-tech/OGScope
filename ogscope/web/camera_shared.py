"""
统一相机管理与共享帧总线 / Unified camera manager and shared frame bus.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable


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
        self._frame_id = 0
        self._latest_raw = None
        self._latest_jpeg: bytes | None = None
        self._latest_ts = 0.0
        self._latest_w = 0
        self._latest_h = 0
        self._runtime_overrides: dict[str, Any] = {}
        self._jpeg_quality = int(os.getenv("OGSCOPE_PREVIEW_JPEG_QUALITY", "75"))
        self._target_fps = max(1, int(os.getenv("OGSCOPE_SHARED_PREVIEW_FPS", "8")))
        # 是否常驻 raw 帧缓存；默认关闭以降低内存占用（分析路径可同步抓帧）
        # Whether to retain raw frame cache; default off to reduce RAM (analysis can sync-grab).
        self._keep_raw_cache = bool(
            int(os.getenv("OGSCOPE_KEEP_RAW_CACHE", "0") or "0")
        )
        self._logger = logging.getLogger(__name__)

    def _build_base_config(self) -> dict[str, Any]:
        from ogscope.config import get_settings

        settings = get_settings()
        base = {
            "type": "imx327_mipi",
            "width": settings.camera_width,
            "height": settings.camera_height,
            "fps": max(1, int(getattr(settings, "camera_fps", 5) or 5)),
            "exposure_us": settings.camera_exposure,
            "analogue_gain": settings.camera_gain,
            "auto_exposure": True,
            "ae_polar_preset": settings.camera_ae_polar_preset,
            "ae_exposure_value": settings.camera_ae_exposure_value,
            "rotation": 180,
            "sampling_mode": getattr(settings, "camera_sampling_mode", "native"),
            "noise_reduction": 0,
            "white_balance_mode": "auto",
            "white_balance_gain_r": 1.0,
            "white_balance_gain_b": 1.0,
            "contrast": 1.0,
            "brightness": 0.0,
            "saturation": 1.0,
            "sharpness": 1.0,
            "night_mode": False,
            "color_mode": "color",
        }
        return {**base, **self._runtime_overrides}

    def _create_camera_sync(self):
        from ogscope.hardware.camera import create_camera

        config = self._build_base_config()
        camera = create_camera(config)
        if camera and camera.initialize():
            return camera
        return None

    def _encode_preview_jpeg_sync(self, frame) -> bytes | None:
        try:
            import cv2

            ok, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(self._jpeg_quality)]
            )
            if not ok:
                return None
            return buf.tobytes()
        except Exception:
            return None

    def _read_frame_sync(self):
        with self._read_lock:
            if self._camera is None or not getattr(self._camera, "is_capturing", False):
                return None
            return self._camera.get_video_frame()

    async def ensure_started(self) -> None:
        """确保单相机进入采集并启动共享帧抓取 / Ensure capture and shared frame grabber."""
        async with self._control_lock:
            if self._camera is None:
                self._camera = await asyncio.to_thread(self._create_camera_sync)
                if self._camera is None:
                    raise RuntimeError("相机初始化失败 / Camera init failed")
            if not getattr(self._camera, "is_capturing", False):
                ok = await asyncio.to_thread(self._camera.start_capture)
                if not ok:
                    raise RuntimeError("相机启动失败 / Camera start failed")
            await self._ensure_grabber_locked()

    async def stop(self) -> None:
        """停止相机采集 / Stop camera capture."""
        async with self._control_lock:
            await self._stop_grabber_locked()
            if self._camera is not None and getattr(
                self._camera, "is_capturing", False
            ):
                await asyncio.to_thread(self._camera.stop_capture)

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
        interval = 1.0 / float(self._target_fps)
        loop = asyncio.get_running_loop()
        try:
            while True:
                t0 = time.time()
                try:
                    frame = await asyncio.to_thread(self._read_frame_sync)
                    if frame is not None:
                        jpeg = await loop.run_in_executor(
                            None, self._encode_preview_jpeg_sync, frame
                        )
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
                except Exception as e:
                    self._logger.error(f"共享抓帧循环异常 / Shared grabber error: {e}")
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
                "runtime_overrides": self._runtime_overrides,
            }
        info = await asyncio.to_thread(cam.get_camera_info)
        return {
            "connected": bool(getattr(cam, "is_initialized", False)),
            "streaming": bool(getattr(cam, "is_capturing", False)),
            "info": info,
            "runtime_overrides": self._runtime_overrides,
        }

    async def get_preview_frame(
        self, since_id: int | None = None, wait_timeout_sec: float = 0.8
    ) -> tuple[int, SharedFrame | None]:
        """读取预览帧；如未更新则返回 304 / Get preview frame; return 304 if unchanged."""
        await self.ensure_started()
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
        await self.ensure_started()
        with self._frame_lock:
            if self._latest_raw is not None:
                try:
                    frame = self._latest_raw.copy()
                except Exception:
                    frame = self._latest_raw
                return frame, self._frame_id, self._latest_ts
        # 无常驻 raw 时同步抓一帧，供解算使用（不写入 _latest_raw，除非开启 keep cache）
        # Sync-grab when raw cache is disabled; avoids breaking analysis while saving RAM.
        frame = await asyncio.to_thread(self._read_frame_sync)
        if frame is None:
            raise RuntimeError("无可用视频帧 / No frame available")
        with self._frame_lock:
            fid = self._frame_id
            ts = self._latest_ts
        try:
            out = frame.copy()
        except Exception:
            out = frame
        return out, fid, ts

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
            import cv2

            if image_format.lower() == "png":
                ok, buf = cv2.imencode(".png", raw_frame)
            else:
                ok, buf = cv2.imencode(
                    ".jpg",
                    raw_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, int(max(10, min(100, quality)))],
                )
            if not ok:
                return None
            return buf.tobytes()
        except Exception:
            return None

    def update_runtime_overrides(self, updates: dict[str, Any]) -> None:
        """更新运行时覆盖参数（不落盘）/ Update runtime overrides (memory only)."""
        self._runtime_overrides.update(updates)

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
