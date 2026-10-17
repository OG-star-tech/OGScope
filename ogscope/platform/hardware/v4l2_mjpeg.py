"""可选 BCM2835 硬件 MJPEG，不改变帧标识 / Optional BCM2835 hardware MJPEG preserving frame identity."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from ogscope.platform.hardware.bcm2835_isp import set_controls
from ogscope.platform.hardware.v4l2_buffers import V4L2Queue, require_frame_token


def discover_mjpeg_device() -> str:
    """按驱动名字发现，绝不把 ISP 当编码器 / Discover by driver name, never mistake ISP for an encoder."""
    for node in sorted(Path("/sys/class/video4linux").glob("video*")):
        try:
            if (node / "name").read_text().strip() == "bcm2835-codec-encode":
                return f"/dev/{node.name}"
        except OSError:
            continue
    raise OSError(
        "BCM2835 hardware encoder node unavailable / BCM2835 硬件编码节点不可用"
    )


class HardwareMjpeg:
    """单个 mem2mem 上下文，串行编码当前帧 / One mem2mem context encoding the current frame serially."""

    def __init__(
        self,
        width: int,
        height: int,
        *,
        source_format: str,
        quality: int,
        device: str = "",
        timeout: float = 2.0,
    ):
        self.input = self.output = None
        self.timeout = timeout
        self.device = device or discover_mjpeg_device()
        try:
            self.input = V4L2Queue(self.device, 10, "bcm2835-codec")
            self.output = V4L2Queue(
                self.device, 9, "bcm2835-codec", shared_fd=self.input.fd
            )
            self.output.configure(width, height, "MJPG")
            self.input.configure(
                width,
                height,
                "BGR3" if source_format in {"BGR888", "BGR", "BGR24"} else "RGB3",
            )
            # 硬件采用码率，质量值只用于选择预算 / Hardware bitrate budget is not identical to software JPEG quality.
            bitrate = max(
                1_000_000,
                min(25_000_000, round(width * height * 30 * (0.2 + quality / 100))),
            )
            set_controls(self.input.fd, {0x009909CF: bitrate})
            self.input.allocate()
            self.output.allocate()
            for i in range(len(self.output.buffers)):
                self.output.queue(i)
            self.output.start()
        except Exception:
            self.close()
            raise

    def encode(self, frame: np.ndarray) -> bytes:
        """同步收回当前 JPEG，拒绝损坏或截断输出 / Retrieve this JPEG synchronously, rejecting corrupt/truncated output."""
        if frame.dtype != np.uint8:
            raise ValueError("MJPEG requires uint8 RGB / MJPEG 需要 uint8 RGB")
        size = self.input.write(frame, 3)
        token = max(time.monotonic_ns() // 1000, getattr(self, "_last_token", 0) + 1)
        self._last_token = token
        self.input.queue(0, size, timestamp_us=token)
        if not self.input.streaming:
            self.input.start()
        deadline = time.monotonic() + self.timeout
        result = self.output.dequeue(deadline)
        self.input.dequeue(deadline)
        require_frame_token(result, token)
        buffer = self.output.buffers[result.index]
        if not 4 <= result.bytesused <= len(buffer):
            raise OSError("Invalid MJPEG size / MJPEG 长度无效")
        data = buffer[: result.bytesused]
        if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
            raise OSError("Incomplete hardware JPEG / 硬件 JPEG 不完整")
        self.output.queue(result.index)
        return data

    def close(self) -> None:
        """释放同一上下文上的两个队列 / Release both queues on the shared context."""
        queues = self.input, self.output
        self.input = self.output = None
        error = None
        for queue in queues:
            if queue is not None:
                try:
                    queue.close()
                except (OSError, BufferError) as exc:
                    error = error or exc
        if error is not None:
            raise error
