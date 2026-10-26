"""显式的网络虚拟相机，不访问物理设备 / Explicit network virtual camera; never opens physical hardware."""

from __future__ import annotations

import json
import math
import struct
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np

from ogscope.domain.camera.driver import FrameBuffer


class VirtualSkyCamera:
    """从虚拟天空服务接收带来源元数据的图像 / Receive provenance-tagged virtual-sky frames."""

    output_pixel_format = "RGB888"

    def __init__(self, config: dict):
        self.config = config
        self.url = str(config.get("virtual_sky_url", "")).rstrip("/")
        self.width = int(config.get("width", 1280))
        self.height = int(config.get("height", 720))
        self.capture_timeout_sec = float(config.get("virtual_sky_timeout_sec", 3.0))
        self.max_bytes = min(8 * 1024 * 1024, max(1024, self.width * self.height * 4))
        self.is_initialized = False
        self.is_capturing = False
        self._lock = threading.Lock()
        self._stream_id = None
        self._frame_id = -1
        self._last_metadata = {}
        self._last_error = ""
        self._last_success = 0.0
        self._fresh_required = False
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def initialize(self) -> bool:
        parsed = urllib.parse.urlparse(self.url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            self._last_error = "Virtual sky URL must be an explicit HTTP(S) endpoint without credentials"
            return False
        self.is_initialized = True
        return True

    def start_capture(self) -> bool:
        if not self.is_initialized:
            return False
        self.is_capturing = True
        return True

    def stop_capture(self) -> bool:
        self.is_capturing = False
        return True

    def close(self) -> bool:
        self.stop_capture()
        self.is_initialized = False
        return True

    def get_video_frame(self) -> FrameBuffer:
        if not self.is_capturing:
            raise OSError("Virtual sky capture is stopped / 虚拟相机已停止")
        with self._lock:
            request_id = uuid.uuid4().hex
            observed = datetime.now(timezone.utc)
            query = urllib.parse.urlencode(
                {
                    "width": self.width,
                    "height": self.height,
                    "request_id": request_id,
                    "observation_time_utc": observed.isoformat(),
                }
            )
            try:
                with self._opener.open(
                    f"{self.url}/api/virtual-eye/frame?{query}",
                    timeout=self.capture_timeout_sec,
                ) as response:
                    raw_meta = response.headers.get("X-Virtual-Eye-Meta", "")
                    if not raw_meta or len(raw_meta) > 16384:
                        raise ValueError("Missing or oversized virtual-frame metadata")
                    meta = json.loads(raw_meta)
                    data = response.read(self.max_bytes + 1)
                if len(data) > self.max_bytes:
                    raise ValueError("Virtual frame exceeds the byte limit")
                if (
                    len(data) < 24
                    or data[:8] != b"\x89PNG\r\n\x1a\n"
                    or struct.unpack(">II", data[16:24]) != (self.width, self.height)
                ):
                    raise ValueError("Virtual PNG dimensions do not match capture")
                if (
                    meta.get("schema_version") != 1
                    or meta.get("source") != "virtual_sky"
                ):
                    raise ValueError("Unsupported virtual-frame contract")
                if meta.get("request_id") != request_id:
                    raise ValueError("Stale or mismatched virtual-frame request")
                timestamp = datetime.fromisoformat(
                    meta["observation_time_utc"].replace("Z", "+00:00")
                )
                if (
                    timestamp.tzinfo is None
                    or abs((timestamp - observed).total_seconds()) > 0.001
                ):
                    raise ValueError(
                        "Virtual observation time does not match this capture"
                    )
                stream, fid = meta.get("stream_id"), meta.get("frame_id")
                if (
                    not isinstance(stream, str)
                    or not stream
                    or not isinstance(fid, int)
                    or isinstance(fid, bool)
                    or fid < 1
                ):
                    raise ValueError("Invalid virtual stream identity")
                if stream == self._stream_id and fid <= self._frame_id:
                    raise ValueError("Repeated or out-of-order virtual frame")
                if meta.get("width") != self.width or meta.get("height") != self.height:
                    raise ValueError("Virtual frame dimensions do not match capture")
                frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                if frame is None or frame.shape[:2] != (self.height, self.width):
                    raise ValueError(
                        "Virtual image is corrupt or has incorrect dimensions"
                    )
                if (
                    not math.isfinite(float(meta.get("fov_width_deg", 0)))
                    or not 0 < float(meta.get("fov_width_deg", 0)) < 180
                ):
                    raise ValueError("Invalid virtual field of view")
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._stream_id, self._frame_id = stream, fid
                self._last_metadata = meta
                self._last_error = ""
                self._last_success = time.monotonic()
                self._fresh_required = False
                return FrameBuffer(
                    frame,
                    self.width,
                    self.height,
                    "RGB888",
                    time.time(),
                    {
                        "observation_time_utc": timestamp.isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "capture_source": "virtual_sky",
                        "virtual_frame": meta,
                    },
                )
            except Exception as exc:
                self._last_error = str(exc)
                # OSError 保留断源诊断；不交付旧帧，不回退物理相机 / Preserve source failure; never return old frames or fall back.
                raise OSError(
                    f"Virtual sky source unavailable / 虚拟天空源不可用: {exc}"
                ) from exc

    def capture_image(self):
        return self.get_video_frame()

    def get_camera_info(self) -> dict:
        fov = self._last_metadata.get("fov_width_deg")
        height_fov = (
            math.degrees(
                2
                * math.atan(math.tan(math.radians(fov) / 2) * self.height / self.width)
            )
            if fov
            else None
        )
        return {
            "driver": "VirtualSkyCamera",
            "backend": "virtual_sky",
            "synthetic": True,
            "width": self.width,
            "height": self.height,
            "output_width": self.width,
            "output_height": self.height,
            "output_pixel_format": "RGB888",
            "actual_exposure_us": 0,
            "fps": int(self.config.get("fps", 2)),
            "source_url": self.url,
            "source_error": self._last_error,
            "source_age_seconds": (
                time.monotonic() - self._last_success if self._last_success else None
            ),
            "virtual_frame": self._last_metadata,
            "optics": {
                "effective_fov_deg": {
                    "width": fov,
                    "height": height_fov,
                    "source": "virtual_sky",
                }
            },
            "capabilities": {
                "auto_exposure": False,
                "manual_exposure": False,
                "synthetic": True,
            },
        }

    def set_exposure(self, exposure_us: int) -> bool:
        """没有物理曝光控制；亮度由场景设置 / No physical exposure control; configure scene brightness."""
        return False

    def set_gain(self, analogue_gain: float, digital_gain: float = 1.0) -> bool:
        """没有物理增益控制 / Physical gain control is unavailable."""
        return False

    def begin_fresh_capture_epoch(self) -> bool:
        self._fresh_required = True
        return True

    def is_within_fresh_capture_epoch(self) -> bool:
        return self._fresh_required
