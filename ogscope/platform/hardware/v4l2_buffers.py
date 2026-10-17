"""有界 Linux V4L2 MMAP 队列 / Bounded Linux V4L2 MMAP queues."""

from __future__ import annotations

import ctypes as c
import errno
import mmap
import os
import select
import sys
import time
from pathlib import Path

import numpy as np


class Capability(c.Structure):
    """Linux v4l2_capability ABI / Linux v4l2_capability ABI。"""

    _fields_ = [
        ("driver", c.c_char * 16),
        ("card", c.c_char * 32),
        ("bus_info", c.c_char * 32),
        ("version", c.c_uint32),
        ("capabilities", c.c_uint32),
        ("device_caps", c.c_uint32),
        ("reserved", c.c_uint32 * 3),
    ]


class PixelFormat(c.Structure):
    """单平面像素格式 ABI / Single-plane pixel-format ABI."""

    _fields_ = [
        (name, c.c_uint32)
        for name in (
            "width",
            "height",
            "pixelformat",
            "field",
            "bytesperline",
            "sizeimage",
            "colorspace",
            "priv",
            "flags",
            "ycbcr_enc",
            "quantization",
            "xfer_func",
        )
    ]


class _FormatUnion(c.Union):
    _fields_ = [
        ("pix", PixelFormat),
        ("raw", c.c_uint8 * 200),
        ("pointer_alignment", c.c_void_p),
    ]


class _PlaneFormat(c.Structure):
    _pack_ = 1
    _fields_ = [
        ("sizeimage", c.c_uint32),
        ("bytesperline", c.c_uint32),
        ("reserved", c.c_uint16 * 6),
    ]


class _MultiPixelFormat(c.Structure):
    _pack_ = 1
    _fields_ = [
        ("width", c.c_uint32),
        ("height", c.c_uint32),
        ("pixelformat", c.c_uint32),
        ("field", c.c_uint32),
        ("colorspace", c.c_uint32),
        ("planes", _PlaneFormat * 8),
        ("num_planes", c.c_uint8),
        ("flags", c.c_uint8),
        ("ycbcr_enc", c.c_uint8),
        ("quantization", c.c_uint8),
        ("xfer_func", c.c_uint8),
        ("reserved", c.c_uint8 * 7),
    ]


class _Plane(c.Structure):
    _fields_ = [
        ("bytesused", c.c_uint32),
        ("length", c.c_uint32),
        ("m", c.c_ulong),
        ("data_offset", c.c_uint32),
        ("reserved", c.c_uint32 * 11),
    ]


class Format(c.Structure):
    """32/64 位对齐的 v4l2_format / Pointer-aligned v4l2_format on 32/64-bit Linux."""

    _fields_ = [("type", c.c_uint32), ("fmt", _FormatUnion)]


class _RequestBuffers(c.Structure):
    _fields_ = [
        ("count", c.c_uint32),
        ("type", c.c_uint32),
        ("memory", c.c_uint32),
        ("capabilities", c.c_uint32),
        ("flags", c.c_uint8),
        ("reserved", c.c_uint8 * 3),
    ]


class _Timeval(c.Structure):
    _fields_ = [("seconds", c.c_long), ("microseconds", c.c_long)]


class _BufferMemory(c.Union):
    _fields_ = [
        ("offset", c.c_uint32),
        ("userptr", c.c_ulong),
        ("planes", c.c_void_p),
        ("fd", c.c_int32),
    ]


class Buffer(c.Structure):
    """包含本机 timeval 的 v4l2_buffer / v4l2_buffer with native timeval layout."""

    _fields_ = [
        ("index", c.c_uint32),
        ("type", c.c_uint32),
        ("bytesused", c.c_uint32),
        ("flags", c.c_uint32),
        ("field", c.c_uint32),
        ("timestamp", _Timeval),
        ("timecode", c.c_uint8 * 16),
        ("sequence", c.c_uint32),
        ("memory", c.c_uint32),
        ("m", _BufferMemory),
        ("length", c.c_uint32),
        ("reserved2", c.c_uint32),
        ("request_fd", c.c_int32),
    ]


def fourcc(value: str) -> int:
    """严格转换四字符格式 / Convert an exact four-character format."""
    if len(value) != 4:
        raise ValueError("FourCC must contain four characters / FourCC 必须为四字符")
    return sum(ord(char) << (8 * i) for i, char in enumerate(value))


def ioctl(fd: int, number: int, value, direction: int = 3) -> None:
    """根据 ABI 大小构造 ioctl / Build ioctl requests from the native ABI size."""
    import fcntl

    request = (direction << 30) | (c.sizeof(value) << 16) | (ord("V") << 8) | number
    fcntl.ioctl(fd, request, value, True)


class V4L2Queue:
    """单所有者、最多两缓冲的流队列 / Single-owner stream queue with at most two buffers."""

    def __init__(
        self, device: str, queue_type: int, driver: str, *, shared_fd: int | None = None
    ):
        if sys.platform != "linux":
            raise OSError("V4L2 requires Linux / V4L2 需要 Linux")
        tainted = Path("/proc/sys/kernel/tainted")
        if tainted.exists() and int(tainted.read_text().strip()) & 128:
            raise OSError(
                "Kernel has recorded an Oops; reboot before hardware acceleration / 内核曾异常，重启后再使用硬件加速"
            )
        self.device, self.type = device, queue_type
        self.multiplane = queue_type in {9, 10}
        self.capture = queue_type in {1, 9}
        self.fd = (
            os.dup(shared_fd)
            if shared_fd is not None
            else os.open(device, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        )
        self.buffers: list[mmap.mmap] = []
        self.streaming = False
        try:
            self.capability = Capability()
            ioctl(self.fd, 0, self.capability, 2)
            actual_driver = self.capability.driver.decode()
            caps = self.capability.device_caps or self.capability.capabilities
            required = 0x04000000 | (
                0x4000 if self.multiplane else 1 if self.capture else 2
            )
            if actual_driver != driver or caps & required != required:
                raise OSError(
                    f"Unsupported V4L2 node / 不支持的节点: {device} {actual_driver}"
                )
        except Exception:
            os.close(self.fd)
            self.fd = -1
            raise

    def configure(self, width: int, height: int, pixel_format: str) -> PixelFormat:
        """协商后严格核对格式与尺寸 / Negotiate and strictly verify format and dimensions."""
        fmt = Format(type=self.type)
        actual = (
            _MultiPixelFormat.from_buffer(fmt.fmt) if self.multiplane else fmt.fmt.pix
        )
        actual.width, actual.height = width, height
        actual.pixelformat, actual.field = fourcc(pixel_format), 1
        if self.multiplane:
            actual.num_planes = 1
        ioctl(self.fd, 5, fmt)
        if (actual.width, actual.height, actual.pixelformat) != (
            width,
            height,
            fourcc(pixel_format),
        ):
            raise OSError("V4L2 changed the requested format / V4L2 改变了请求格式")
        if self.multiplane:
            if actual.num_planes != 1:
                raise OSError(
                    "Only contiguous single-plane layouts are supported / 仅支持连续单平面布局"
                )
            self.format = PixelFormat(
                width=width,
                height=height,
                pixelformat=actual.pixelformat,
                bytesperline=actual.planes[0].bytesperline,
                sizeimage=actual.planes[0].sizeimage,
            )
        else:
            self.format = PixelFormat.from_buffer_copy(actual)
        return self.format

    def _buffer(self, index: int = 0, bytesused: int = 0) -> Buffer:
        """保持平面指针活到 ioctl 返回 / Keep plane pointers alive through ioctl completion."""
        buf = Buffer(index=index, type=self.type, memory=1, bytesused=bytesused)
        if self.multiplane:
            plane = _Plane(
                bytesused=bytesused,
                length=len(self.buffers[index]) if index < len(self.buffers) else 0,
            )
            buf._plane = plane
            buf.length, buf.m.planes = 1, c.addressof(plane)
        return buf

    def allocate(self) -> None:
        """最多分配两帧，不建立历史队列 / Allocate at most two frames, never a history queue."""
        req = _RequestBuffers(count=2, type=self.type, memory=1)
        ioctl(self.fd, 8, req)
        if not 1 <= req.count <= 2:
            raise OSError("Unexpected buffer count / 缓冲数量超出限制")
        for i in range(req.count):
            buf = self._buffer(i)
            ioctl(self.fd, 9, buf)
            length = buf._plane.length if self.multiplane else buf.length
            offset = buf._plane.m if self.multiplane else buf.m.offset
            self.buffers.append(
                mmap.mmap(
                    self.fd,
                    length,
                    flags=mmap.MAP_SHARED,
                    prot=mmap.PROT_READ | mmap.PROT_WRITE,
                    offset=offset,
                )
            )

    def queue(
        self, index: int, bytesused: int = 0, *, timestamp_us: int | None = None
    ) -> None:
        """排入一帧 / Queue one frame."""
        buf = self._buffer(index, bytesused)
        if timestamp_us is not None:
            if self.capture or timestamp_us < 0:
                raise ValueError(
                    "Only output frames accept a timestamp token / 仅输入处理器的帧接受时间标识"
                )
            buf.timestamp.seconds, buf.timestamp.microseconds = divmod(
                timestamp_us, 1_000_000
            )
        ioctl(self.fd, 15, buf)

    def start(self) -> None:
        """启动已配置流 / Start a configured stream."""
        ioctl(self.fd, 18, c.c_uint32(self.type), 1)
        self.streaming = True

    def dequeue(self, deadline: float) -> Buffer:
        """在统一截止时间内出队 / Dequeue within a shared monotonic deadline."""
        poll = select.poll()
        poll.register(self.fd, select.POLLIN if self.capture else select.POLLOUT)
        while True:
            buf = self._buffer()
            try:
                ioctl(self.fd, 17, buf)
                if self.multiplane:
                    if buf._plane.data_offset:
                        raise OSError(
                            "Nonzero plane data offset unsupported / 不支持非零平面数据偏移"
                        )
                    buf.bytesused = buf._plane.bytesused
                if buf.flags & 0x40:
                    raise OSError("V4L2 returned an error frame / V4L2 返回错误帧")
                if not 0 <= buf.index < len(self.buffers) or buf.bytesused > len(
                    self.buffers[buf.index]
                ):
                    raise OSError("Invalid dequeued V4L2 buffer / 出队 V4L2 缓冲无效")
                return buf
            except OSError as exc:
                if exc.errno != errno.EAGAIN:
                    raise
            remaining = deadline - time.monotonic()
            events = (
                poll.poll(max(1, int(max(0, remaining) * 1000)))
                if remaining > 0
                else []
            )
            if any(
                mask & (select.POLLERR | select.POLLHUP | select.POLLNVAL)
                for _, mask in events
            ):
                raise OSError("V4L2 queue disconnected or failed / V4L2 队列断开或失败")
            if remaining <= 0 or not events:
                raise TimeoutError("V4L2 processing timed out / V4L2 处理超时")

    def write(self, frame: np.ndarray, channels: int) -> int:
        """按驱动行间距写入，拒绝尺寸变化 / Write driver-strided rows, rejecting size changes."""
        fmt = self.format
        itemsize = frame.dtype.itemsize
        row_bytes = fmt.width * channels * itemsize
        stride = fmt.bytesperline or row_bytes
        expected = (
            (fmt.height, fmt.width)
            if channels == 1
            else (fmt.height, fmt.width, channels)
        )
        if (
            frame.shape != expected
            or stride < row_bytes
            or stride * fmt.height > len(self.buffers[0])
        ):
            raise ValueError("Frame layout does not match V4L2 / 图像布局不匹配 V4L2")
        strides = (
            (stride, itemsize)
            if channels == 1
            else (stride, channels * itemsize, itemsize)
        )
        view = np.ndarray(
            expected, dtype=frame.dtype, buffer=self.buffers[0], strides=strides
        )
        view[...] = frame
        return stride * fmt.height

    def close(self) -> None:
        """所有失败路径都释放流、映射与描述符 / Release streams, mappings and descriptors on all paths."""
        if self.fd < 0:
            return
        if self.streaming:
            try:
                ioctl(self.fd, 19, c.c_uint32(self.type), 1)
            except OSError:
                pass
            self.streaming = False
        error = None
        try:
            for buf in self.buffers:
                try:
                    buf.close()
                except (OSError, BufferError) as exc:
                    error = error or exc
            self.buffers.clear()
            try:
                ioctl(self.fd, 8, _RequestBuffers(type=self.type, memory=1))
            except OSError:
                pass
        finally:
            os.close(self.fd)
            self.fd = -1
        if error is not None:
            raise error


def require_frame_token(buffer: Buffer, expected_us: int) -> None:
    """拒绝历史输出；硬件必须回传当前输入的标识 / Reject historical output; hardware must echo this input's token."""
    actual = buffer.timestamp.seconds * 1_000_000 + buffer.timestamp.microseconds
    if buffer.flags & 0xE000 != 0x4000 or actual != expected_us:
        raise OSError(
            "Hardware output does not match the current input frame / 硬件输出不匹配当前输入帧"
        )
