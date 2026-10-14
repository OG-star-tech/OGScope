"""BCM2835 硬件 RAW 处理，保留软件 AE / BCM2835 hardware RAW processing with software AE."""

from __future__ import annotations

import ctypes as c
import math
import re
import subprocess
import time
from pathlib import Path

import numpy as np

from ogscope.platform.hardware.v4l2_buffers import V4L2Queue, ioctl, require_frame_token


def verify_isp_pair(input_device: str, output_device: str) -> None:
    """输入输出必须属于同一 ISP 实例 / Input and output must belong to the same ISP instance."""
    for media in sorted(Path("/dev").glob("media*")):
        result = subprocess.run(
            ["media-ctl", "-d", str(media), "-p"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode or "bcm2835-isp" not in result.stdout:
            continue
        nodes = set(re.findall(r"device node name\s+(\S+)", result.stdout))
        if input_device in nodes and output_device in nodes:
            return
    raise OSError(
        "ISP nodes are not paired in one media graph / ISP 节点不属于同一媒体实例"
    )


class _ControlValue(c.Union):
    _fields_ = [("value", c.c_int32), ("value64", c.c_int64), ("ptr", c.c_void_p)]


class _Control(c.Structure):
    _pack_ = 1
    _fields_ = [
        ("id", c.c_uint32),
        ("size", c.c_uint32),
        ("reserved", c.c_uint32),
        ("data", _ControlValue),
    ]


class _Controls(c.Structure):
    _fields_ = [
        ("which", c.c_uint32),
        ("count", c.c_uint32),
        ("error_idx", c.c_uint32),
        ("request_fd", c.c_int32),
        ("reserved", c.c_uint32),
        ("controls", c.POINTER(_Control)),
    ]


def set_controls(fd: int, settings: dict[int, int | bytes]) -> None:
    """发送整数或 UAPI 负载控件 / Send integer or UAPI-payload controls."""
    # 镜头阴影需要有效 DMA 表；禁用也不能传零负载，否则部分内核会解引用错误指针。
    # Lens shading requires a valid DMA table even when disabling; zero payloads can crash affected kernels.
    if 0x009819E2 in settings:
        raise ValueError(
            "Lens shading requires a separately validated DMA table / 镜头阴影需单独验证 DMA 表"
        )
    controls = (_Control * len(settings))()
    payloads = []
    for ctrl, (key, value) in zip(controls, settings.items()):
        ctrl.id = key
        if isinstance(value, bytes):
            payload = c.create_string_buffer(value)
            payloads.append(payload)
            ctrl.size, ctrl.data.ptr = len(value), c.addressof(payload)
        else:
            if not -(1 << 31) <= value < (1 << 31):
                raise ValueError(
                    "Control integer would overflow the ABI / 控件整数超出 ABI 范围"
                )
            ctrl.data.value = value
    ioctl(fd, 72, _Controls(count=len(settings), controls=controls))


class Bcm2835Isp:
    """显式选择的 ISP：单帧输入、独立 RGB 输出 / Opt-in ISP with one-frame input and owned RGB output."""

    def __init__(
        self,
        width: int,
        height: int,
        *,
        pattern: str,
        bit_depth: int,
        black: int,
        white: int,
        gamma: float,
        input_device: str,
        output_device: str,
        timeout: float = 2.0,
    ):
        self.input = self.output = None
        self.timeout = timeout
        self._gains = None
        self.frames = 0
        self.last_process_ms = 0.0
        if (
            not math.isfinite(gamma)
            or gamma <= 0
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Invalid gamma or timeout / Gamma 或超时无效")
        if (
            bit_depth not in {10, 12, 14, 16}
            or not 0 <= black < white <= (1 << bit_depth) - 1
        ):
            raise ValueError("Unsupported RAW signal range / 不支持的 RAW 信号范围")
        prefix = {"RGGB": "RG", "BGGR": "BG", "GBRG": "GB", "GRBG": "BA"}[pattern]
        if bit_depth == 16:
            prefix = {"RGGB": "RG", "BGGR": "BY", "GBRG": "GB", "GRBG": "GR"}[pattern]
        pixel_format = prefix + str(bit_depth)
        if pattern == "BGGR" and bit_depth == 16:
            pixel_format = "BYR2"
        verify_isp_pair(input_device, output_device)
        try:
            self.input = V4L2Queue(input_device, 2, "bcm2835-isp")
            self.output = V4L2Queue(output_device, 1, "bcm2835-isp")
            self.input.configure(width, height, pixel_format)
            self.output.configure(width, height, "RGB3")
            self._configure_signal(bit_depth, black, white, gamma)
            self.input.allocate()
            self.output.allocate()
            for i in range(len(self.output.buffers)):
                self.output.queue(i)
            self.output.start()
        except Exception:
            self.close()
            raise

    def _configure_signal(
        self, depth: int, black: int, white: int, gamma: float
    ) -> None:
        """显式重置 ISP，避免继承上个用户的颜色与降噪 / Reset ISP controls instead of inheriting prior tuning."""
        import struct

        scale = 1 << (16 - depth)
        black_payload = struct.pack(
            "=IHHH2x", 1, black * scale, black * scale, black * scale
        )
        # ISP 控件使用 16 位信号域，不直接复制 12 位黑电平 / ISP controls use 16-bit signal units.
        points = np.linspace(0, 1, 33) ** 2.5
        x = np.rint(points * 65535).astype(np.uint16)
        y = np.rint(points ** (1 / gamma) * 65535).astype(np.uint16)
        gamma_payload = struct.pack("=I", 1) + x.tobytes() + y.tobytes()
        matrix = struct.pack("=I", 1)
        matrix += b"".join(
            struct.pack("=iI", int(i == j), 1) for i in range(3) for j in range(3)
        )
        matrix += bytes(12)
        set_controls(
            self.input.fd,
            {
                0x009819E1: matrix,
                0x009819E3: black_payload,
                0x009819E4: struct.pack("=IIiI", 0, 0, 0, 1),
                0x009819E5: gamma_payload,
                0x009819E6: struct.pack("=IIiIiI", 0, 0, 0, 1, 0, 1),
                0x009819E7: struct.pack("=IiIiIiI", 0, 0, 1, 0, 1, 0, 1),
                0x009819E8: bytes(8),
                0x009819E9: bytes(8),
                0x009F0905: round(1000 * ((1 << depth) - 1) / (white - black)),
            },
        )

    def process(self, raw: np.ndarray, gains: tuple[float, float, float]) -> np.ndarray:
        """对当前帧同步处理，绝不返回历史输出 / Process this frame synchronously, never a historical output."""
        started = time.monotonic()
        if raw.dtype != np.uint16:
            raise ValueError(
                "ISP requires uint16 RAW containers / ISP 需要 uint16 RAW 容器"
            )
        if gains != self._gains:
            if gains[1] != 1.0 or not all(
                math.isfinite(gain) and 0.001 <= gain <= 65.535 for gain in gains
            ):
                raise ValueError("Invalid ISP color gains / ISP 颜色增益无效")
            set_controls(
                self.input.fd,
                {
                    0x0098090E: round(gains[0] * 1000),
                    0x0098090F: round(gains[2] * 1000),
                },
            )
            self._gains = gains
        size = self.input.write(raw, 1)
        token = max(time.monotonic_ns() // 1000, getattr(self, "_last_token", 0) + 1)
        self._last_token = token
        self.input.queue(0, size, timestamp_us=token)
        if not self.input.streaming:
            self.input.start()
        deadline = started + self.timeout
        result = self.output.dequeue(deadline)
        self.input.dequeue(deadline)
        require_frame_token(result, token)
        fmt = self.output.format
        stride = fmt.bytesperline
        if result.bytesused < stride * fmt.height:
            raise OSError("Short ISP output / ISP 输出不足一帧")
        view = np.ndarray(
            (fmt.height, fmt.width, 3),
            dtype=np.uint8,
            buffer=self.output.buffers[result.index],
            strides=(stride, 3, 1),
        )
        # 出队缓冲将被复用；对外必须交付独立像素 / Own the pixels before requeuing reusable DMA buffers.
        rgb = view.copy()
        self.output.queue(result.index)
        self.frames += 1
        self.last_process_ms = (time.monotonic() - started) * 1000
        return rgb

    def close(self) -> None:
        """释放两个节点，包括半初始化失败 / Release both nodes, including partial initialization."""
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
