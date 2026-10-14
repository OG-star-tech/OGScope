"""VideoCore 硬件 ISP（bcm2835-isp）/ VideoCore hardware ISP (bcm2835-isp).

ISP 是 V4L2 内存到内存设备：Bayer 帧送入其输出节点，处理后的图像从采集节点
取回（节点从 V4L2 设备列表中查找）。去马赛克、黑电平、白平衡、颜色矩阵和 gamma
都在硬件里完成，这些工作在 RAW V4L2 路径里原本由 CPU 承担。只用 ctypes 调用
V4L2 ioctl，不依赖 libcamera：RAW 路径存在的意义就是避开 libcamera 的内存占用。
The ISP is a V4L2 memory-to-memory device: Bayer frames are queued on its
output node, processed images come back on its capture node (both looked up in
the V4L2 device list). Demosaic, black level, white balance, colour matrix and gamma
run in hardware - work the RAW V4L2 path otherwise does on the CPU. Plain V4L2
ioctls through ctypes, no libcamera: the RAW path exists to avoid libcamera's
memory footprint.
"""

from __future__ import annotations

import ctypes
import fcntl
import mmap
import os
import re
import select
import struct
from collections.abc import Sequence
from pathlib import Path

import numpy as np

# V4L2 接口常量（64 位 ABI）/ V4L2 ABI constants (64-bit)
V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
V4L2_BUF_TYPE_VIDEO_OUTPUT = 2
V4L2_MEMORY_MMAP = 1
V4L2_FIELD_NONE = 1
V4L2_COLORSPACE_SRGB = 8
V4L2_COLORSPACE_RAW = 11

# ISP 控件 / ISP controls (include/uapi/linux/bcm2835-isp.h)
V4L2_CID_RED_BALANCE = 0x0098090E
V4L2_CID_BLUE_BALANCE = 0x0098090F
V4L2_CID_DIGITAL_GAIN = 0x009F0905
_ISP_CID_BASE = 0x009819E0
CID_CC_MATRIX = _ISP_CID_BASE + 0x1
CID_BLACK_LEVEL = _ISP_CID_BASE + 0x3
CID_GAMMA = _ISP_CID_BASE + 0x5
CID_DENOISE = _ISP_CID_BASE + 0x6
CID_SHARPEN = _ISP_CID_BASE + 0x7
CID_DPC = _ISP_CID_BASE + 0x8
CID_CDN = _ISP_CID_BASE + 0x9
GAMMA_POINTS = 33

# V4L2 设备列表与 ISP 节点名 / V4L2 device list and ISP node names
V4L2_SYSFS = "/sys/class/video4linux"
ISP_OUTPUT_NAME = "bcm2835-isp-output0"
ISP_CAPTURE_NAME = "bcm2835-isp-capture0"

# Bayer 排列 -> 16 位 Bayer 格式 / Bayer pattern -> 16-bit Bayer format
BAYER_16BIT = {"RGGB": "RG16", "BGGR": "BYR2", "GRBG": "GR16", "GBRG": "GB16"}


def find_isp_nodes(
    sysfs_root: str | os.PathLike[str] = V4L2_SYSFS, dev_root: str = "/dev"
) -> list[tuple[str, str]]:
    """在 V4L2 设备列表中查找各 ISP 实例的（输出节点，采集节点）。

    每个实例以相同名字注册一组节点，且 ``index`` 从 0 重新计数，故按设备号排序后
    以 index 0 划分实例。
    Finds (output node, capture node) of every ISP instance in the V4L2 device
    list. Each instance registers the same node names with ``index`` restarting
    at 0, so instances are split at index 0 in device-number order.
    """
    root = Path(sysfs_root)
    try:
        entries = [e for e in root.iterdir() if re.fullmatch(r"video\d+", e.name)]
    except OSError:
        return []
    instances: list[dict[str, str]] = []
    for entry in sorted(entries, key=lambda e: int(e.name[5:])):
        try:
            name = (entry / "name").read_text().strip()
            index = int((entry / "index").read_text().strip())
        except (OSError, ValueError):
            continue
        if not name.startswith("bcm2835-isp-"):
            continue
        if index == 0 or not instances:
            instances.append({})
        instances[-1].setdefault(name, f"{dev_root}/{entry.name}")
    return [
        (nodes[ISP_OUTPUT_NAME], nodes[ISP_CAPTURE_NAME])
        for nodes in instances
        if ISP_OUTPUT_NAME in nodes and ISP_CAPTURE_NAME in nodes
    ]


def fourcc(code: str) -> int:
    """四字符码 / FourCC value."""
    return sum(ord(character) << (8 * index) for index, character in enumerate(code))


class v4l2_pix_format(ctypes.Structure):  # noqa: N801 - kernel name
    _fields_ = [
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("pixelformat", ctypes.c_uint32),
        ("field", ctypes.c_uint32),
        ("bytesperline", ctypes.c_uint32),
        ("sizeimage", ctypes.c_uint32),
        ("colorspace", ctypes.c_uint32),
        ("priv", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("ycbcr_enc", ctypes.c_uint32),
        ("quantization", ctypes.c_uint32),
        ("xfer_func", ctypes.c_uint32),
    ]


class _FormatUnion(ctypes.Union):
    # 内核联合体含指针，按 8 字节对齐 / The kernel union holds pointers: 8-byte aligned.
    _fields_ = [
        ("pix", v4l2_pix_format),
        ("raw_data", ctypes.c_uint8 * 200),
        ("_align", ctypes.c_void_p),
    ]


class v4l2_format(ctypes.Structure):  # noqa: N801
    _fields_ = [("type", ctypes.c_uint32), ("fmt", _FormatUnion)]


class v4l2_requestbuffers(ctypes.Structure):  # noqa: N801
    _fields_ = [
        ("count", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("memory", ctypes.c_uint32),
        ("capabilities", ctypes.c_uint32),
        ("flags", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8 * 3),
    ]


class _Timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _Timecode(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("frames", ctypes.c_uint8),
        ("seconds", ctypes.c_uint8),
        ("minutes", ctypes.c_uint8),
        ("hours", ctypes.c_uint8),
        ("userbits", ctypes.c_uint8 * 4),
    ]


class _BufferM(ctypes.Union):
    _fields_ = [
        ("offset", ctypes.c_uint32),
        ("userptr", ctypes.c_ulong),
        ("planes", ctypes.c_void_p),
        ("fd", ctypes.c_int32),
    ]


class v4l2_buffer(ctypes.Structure):  # noqa: N801
    _fields_ = [
        ("index", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("bytesused", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("field", ctypes.c_uint32),
        ("timestamp", _Timeval),
        ("timecode", _Timecode),
        ("sequence", ctypes.c_uint32),
        ("memory", ctypes.c_uint32),
        ("m", _BufferM),
        ("length", ctypes.c_uint32),
        ("reserved2", ctypes.c_uint32),
        ("request_fd", ctypes.c_int32),
    ]


class _ExtControlValue(ctypes.Union):
    _fields_ = [
        ("value", ctypes.c_int32),
        ("value64", ctypes.c_int64),
        ("ptr", ctypes.c_void_p),
    ]


class v4l2_ext_control(ctypes.Structure):  # noqa: N801
    _pack_ = 1  # uapi 中为 packed / packed in the uapi header
    _fields_ = [
        ("id", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("reserved2", ctypes.c_uint32),
        ("u", _ExtControlValue),
    ]


class v4l2_ext_controls(ctypes.Structure):  # noqa: N801
    _fields_ = [
        ("which", ctypes.c_uint32),
        ("count", ctypes.c_uint32),
        ("error_idx", ctypes.c_uint32),
        ("request_fd", ctypes.c_int32),
        ("reserved", ctypes.c_uint32),
        ("controls", ctypes.POINTER(v4l2_ext_control)),
    ]


def _ioc(direction: int, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("V") << 8) | number


_IOW, _IOWR = 1, 3
VIDIOC_S_FMT = _ioc(_IOWR, 5, ctypes.sizeof(v4l2_format))
VIDIOC_REQBUFS = _ioc(_IOWR, 8, ctypes.sizeof(v4l2_requestbuffers))
VIDIOC_QUERYBUF = _ioc(_IOWR, 9, ctypes.sizeof(v4l2_buffer))
VIDIOC_QBUF = _ioc(_IOWR, 15, ctypes.sizeof(v4l2_buffer))
VIDIOC_DQBUF = _ioc(_IOWR, 17, ctypes.sizeof(v4l2_buffer))
VIDIOC_STREAMON = _ioc(_IOW, 18, ctypes.sizeof(ctypes.c_int))
VIDIOC_STREAMOFF = _ioc(_IOW, 19, ctypes.sizeof(ctypes.c_int))
VIDIOC_S_EXT_CTRLS = _ioc(_IOWR, 72, ctypes.sizeof(v4l2_ext_controls))


class IspError(RuntimeError):
    """ISP 不可用或处理失败 / The ISP is unavailable or failed to process a frame."""


def gamma_curve(gamma: float) -> tuple[list[int], list[int]]:
    """33 点 gamma 曲线（16 位进出），暗部取点更密 / 33-point gamma curve (16-bit
    in/out), with points packed towards black where the curve is steepest.

    ISP 在黑电平之后会把信号重新拉满 16 位量程，所以这里的输入就是归一化的
    线性值，与 V4L2 RAW 路径的 gamma 查找表一致。
    The ISP rescales the signal to the full 16-bit range after the black
    level, so the input here is the normalized linear value - the same one
    the RAW path's gamma lookup table uses.
    """
    exponent = 1.0 / max(1.0, float(gamma))
    xs: list[int] = []
    for index in range(GAMMA_POINTS):
        value = round(65535 * (index / (GAMMA_POINTS - 1)) ** 3)
        xs.append(max(value, xs[-1] + 1) if xs else value)
    xs[-1] = 65535
    ys = [round(65535 * (x / 65535) ** exponent) for x in xs]
    return xs, ys


class _Queue:
    """ISP 节点上的单个 mmap 缓冲区 / One mmap'd buffer on one ISP node."""

    def __init__(self, fd: int, buf_type: int) -> None:
        self.fd = fd
        self.type = buf_type
        request = v4l2_requestbuffers(count=1, type=buf_type, memory=V4L2_MEMORY_MMAP)
        fcntl.ioctl(fd, VIDIOC_REQBUFS, request)
        if request.count < 1:
            raise IspError("ISP allocated no buffers")
        buffer = v4l2_buffer(index=0, type=buf_type, memory=V4L2_MEMORY_MMAP)
        fcntl.ioctl(fd, VIDIOC_QUERYBUF, buffer)
        self.map = mmap.mmap(
            fd,
            buffer.length,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=buffer.m.offset,
        )

    def queue(self, bytesused: int = 0) -> None:
        buffer = v4l2_buffer(
            index=0,
            type=self.type,
            memory=V4L2_MEMORY_MMAP,
            bytesused=bytesused,
            field=V4L2_FIELD_NONE,
        )
        fcntl.ioctl(self.fd, VIDIOC_QBUF, buffer)

    def dequeue(self, timeout_s: float) -> None:
        ready = (
            select.POLLIN
            if self.type == V4L2_BUF_TYPE_VIDEO_CAPTURE
            else select.POLLOUT
        )
        poller = select.poll()
        poller.register(self.fd, ready | select.POLLERR)
        if not poller.poll(int(timeout_s * 1000)):
            raise IspError("ISP did not return a buffer in time")
        buffer = v4l2_buffer(type=self.type, memory=V4L2_MEMORY_MMAP)
        fcntl.ioctl(self.fd, VIDIOC_DQBUF, buffer)

    def stream(self, enabled: bool) -> None:
        request = VIDIOC_STREAMON if enabled else VIDIOC_STREAMOFF
        fcntl.ioctl(self.fd, request, ctypes.c_int(self.type))

    def close(self) -> None:
        try:
            self.map.close()
        except BufferError:
            # 调用方仍持有该缓冲区的视图；随其释放而回收 / A caller still
            # holds a view of the buffer; it is freed along with that view.
            pass


class Bcm2835Isp:
    """在 VideoCore ISP 中把 16 位 Bayer 帧处理为 RGB888 / Turn 16-bit Bayer
    frames into RGB888 in the VideoCore ISP.

    输入为高位对齐的 Bayer（12 位传感器值 v 以 v << 4 送入），输出 H x W x 3
    RGB888；逐帧同步处理。降噪、锐化与坏点校正保持关闭：它们会抹掉或删除暗星。
    Input is MSB-aligned Bayer (a 12-bit sensor value v enters as v << 4);
    output is H x W x 3 RGB888, one frame at a time. Denoise, sharpening and
    defective-pixel correction stay off: they smear or remove faint stars.
    """

    def __init__(
        self,
        width: int,
        height: int,
        bayer_pattern: str = "RGGB",
        *,
        output_node: str,
        capture_node: str,
        timeout_s: float = 2.0,
    ) -> None:
        if bayer_pattern not in BAYER_16BIT:
            raise IspError(f"unsupported Bayer pattern {bayer_pattern}")
        self.width = int(width)
        self.height = int(height)
        self.timeout_s = float(timeout_s)
        self.nodes = (output_node, capture_node)
        self._out_fd = -1
        self._cap_fd = -1
        self._input: _Queue | None = None
        self._output: _Queue | None = None
        self._float_scratch: np.ndarray | None = None
        self._in_view: np.ndarray | None = None
        self._out_view: np.ndarray | None = None
        try:
            self._out_fd = os.open(output_node, os.O_RDWR | os.O_NONBLOCK)
            self._cap_fd = os.open(capture_node, os.O_RDWR | os.O_NONBLOCK)
            self.in_stride = self._set_format(
                self._out_fd,
                V4L2_BUF_TYPE_VIDEO_OUTPUT,
                BAYER_16BIT[bayer_pattern],
                self.width * 2,
                V4L2_COLORSPACE_RAW,
            )
            self.out_stride = self._set_format(
                self._cap_fd,
                V4L2_BUF_TYPE_VIDEO_CAPTURE,
                "RGB3",
                self.width * 3,
                V4L2_COLORSPACE_SRGB,
            )
            self._input = _Queue(self._out_fd, V4L2_BUF_TYPE_VIDEO_OUTPUT)
            self._output = _Queue(self._cap_fd, V4L2_BUF_TYPE_VIDEO_CAPTURE)
            self.disable_enhancements()
            self._input.stream(True)
            self._output.stream(True)
        except (OSError, IspError) as exc:
            self.close()
            raise IspError(f"bcm2835-isp unavailable on {output_node}: {exc}") from exc
        # 直接映射到 mmap 缓冲区，逐帧零分配 / Views onto the mmap'd buffers: no per-frame allocation.
        self._in_view = np.ndarray(
            (self.height, self.in_stride // 2), dtype=np.uint16, buffer=self._input.map
        )[:, : self.width]
        self._out_view = np.ndarray(
            (self.height, self.out_stride), dtype=np.uint8, buffer=self._output.map
        )[:, : self.width * 3].reshape(self.height, self.width, 3)

    @classmethod
    def open_first(
        cls,
        width: int,
        height: int,
        bayer_pattern: str,
        nodes: Sequence[tuple[str, str]] | None = None,
    ) -> Bcm2835Isp:
        """打开第一个可用的 ISP 实例（默认从 V4L2 设备列表查找）/ Open the first
        available ISP instance (looked up in the V4L2 device list by default)."""
        if nodes is None:
            nodes = find_isp_nodes()
        errors = []
        for output_node, capture_node in nodes:
            try:
                return cls(
                    width,
                    height,
                    bayer_pattern,
                    output_node=output_node,
                    capture_node=capture_node,
                )
            except IspError as exc:
                errors.append(str(exc))
        raise IspError("; ".join(errors) or "no bcm2835-isp in the V4L2 device list")

    def _set_format(
        self, fd: int, buf_type: int, code: str, stride: int, colorspace: int
    ) -> int:
        fmt = v4l2_format(type=buf_type)
        pix = fmt.fmt.pix
        pix.width = self.width
        pix.height = self.height
        pix.pixelformat = fourcc(code)
        pix.field = V4L2_FIELD_NONE
        pix.bytesperline = stride
        pix.colorspace = colorspace
        fcntl.ioctl(fd, VIDIOC_S_FMT, fmt)
        if (pix.width, pix.height, pix.pixelformat) != (
            self.width,
            self.height,
            fourcc(code),
        ):
            raise IspError(f"ISP refused {code} {self.width}x{self.height}")
        return int(pix.bytesperline)

    # 控件 / Controls --------------------------------------------------------

    def _set_controls(self, controls: Sequence[tuple[int, int | bytes]]) -> None:
        array = (v4l2_ext_control * len(controls))()
        payloads = []
        for slot, (cid, value) in zip(array, controls):
            slot.id = cid
            if isinstance(value, bytes):
                payload = ctypes.create_string_buffer(value, len(value))
                payloads.append(payload)
                slot.size = len(value)
                slot.u.ptr = ctypes.cast(payload, ctypes.c_void_p)
            else:
                slot.u.value = int(value)
        request = v4l2_ext_controls(which=0, count=len(controls), controls=array)
        fcntl.ioctl(self._out_fd, VIDIOC_S_EXT_CTRLS, request)

    def disable_enhancements(self) -> None:
        """关闭降噪、锐化、坏点校正与色彩降噪 / Turn off denoise, sharpening,
        defective-pixel correction and colour denoise."""
        self._set_controls(
            [
                # {enabled, constant, slope{num,den}, strength{num,den}}
                (CID_DENOISE, struct.pack("<IIiIiI", 0, 0, 0, 1, 0, 1)),
                # {enabled, threshold{num,den}, strength{num,den}, limit{num,den}}
                (CID_SHARPEN, struct.pack("<IiIiIiI", 0, 0, 1, 0, 1, 0, 1)),
                (CID_DPC, struct.pack("<II", 0, 0)),
                (CID_CDN, struct.pack("<II", 0, 0)),
            ]
        )

    def set_black_level(self, level_16bit: int) -> None:
        """16 位输入尺度上的黑电平 / Black level on the 16-bit input scale."""
        level = max(0, min(0xFFFF, int(level_16bit)))
        self._set_controls(
            [(CID_BLACK_LEVEL, struct.pack("<I3H2x", 1, level, level, level))]
        )

    def set_white_balance(self, red_gain: float, blue_gain: float) -> None:
        """线性域白平衡增益（绿通道为 1）/ Linear white-balance gains (green is 1)."""
        self._set_controls(
            [
                (V4L2_CID_RED_BALANCE, max(1, round(red_gain * 1000))),
                (V4L2_CID_BLUE_BALANCE, max(1, round(blue_gain * 1000))),
            ]
        )

    def set_digital_gain(self, gain: float) -> None:
        """黑电平之后、gamma 之前的数字增益 / Digital gain after black level, before gamma."""
        self._set_controls([(V4L2_CID_DIGITAL_GAIN, max(1, round(gain * 1000)))])

    def set_gamma(self, xs: Sequence[int], ys: Sequence[int]) -> None:
        """33 点曲线，x 严格递增 / 33-point curve, x strictly increasing."""
        if len(xs) != GAMMA_POINTS or len(ys) != GAMMA_POINTS:
            raise ValueError("gamma needs 33 points")
        payload = struct.pack(f"<I{GAMMA_POINTS}H{GAMMA_POINTS}H", 1, *xs, *ys)
        self._set_controls([(CID_GAMMA, payload)])

    def set_identity_ccm(self) -> None:
        """单位颜色矩阵：RAW 路径不使用传感器颜色模型 / Identity colour matrix:
        the RAW path applies no sensor colour model."""
        rationals: list[int] = []
        for row in range(3):
            for column in range(3):
                rationals += [1 if row == column else 0, 1]
        payload = struct.pack("<I" + "iI" * 9 + "3i", 1, *rationals, 0, 0, 0)
        self._set_controls([(CID_CC_MATRIX, payload)])

    # 帧 / Frames --------------------------------------------------------------

    def process(self, raw: np.ndarray, *, shift: int = 0) -> np.ndarray:
        """处理一帧 H x W Bayer，返回 ISP 输出缓冲区视图，下一次调用前有效
        / Process one H x W Bayer frame; returns a view of the ISP's output
        buffer, valid until the next call - copy it to keep it.

        整数输入左移 shift 位；浮点输入（时域降噪后的累加器）按 2**shift 缩放
        并四舍五入，保留其亚整数精度。
        Integer input is shifted left by `shift`; float input (the temporal-NR
        accumulator) is scaled by 2**shift and rounded, keeping its
        sub-integer precision.
        """
        if (
            self._input is None
            or self._output is None
            or self._in_view is None
            or self._out_view is None
        ):
            raise IspError("ISP is closed")
        if raw.shape != (self.height, self.width):
            raise ValueError(f"expected {self.height}x{self.width}, got {raw.shape}")
        if raw.dtype.kind == "f":
            scratch = self._float_scratch
            if scratch is None:
                scratch = np.empty((self.height, self.width), dtype=np.float32)
                self._float_scratch = scratch
            np.multiply(raw, float(1 << shift), out=scratch)
            np.rint(scratch, out=scratch)
            np.clip(scratch, 0, 0xFFFF, out=scratch)
            np.copyto(self._in_view, scratch, casting="unsafe")
        else:
            np.left_shift(raw, shift, out=self._in_view, casting="unsafe")
        try:
            self._output.queue()
            self._input.queue(bytesused=self.in_stride * self.height)
            self._output.dequeue(self.timeout_s)
            self._input.dequeue(self.timeout_s)
        except OSError as exc:
            raise IspError(f"ISP frame failed: {exc}") from exc
        return self._out_view

    def owns(self, array: np.ndarray) -> bool:
        """数组是否与 ISP 输出缓冲区共享内存 / Whether an array shares the ISP output buffer."""
        if self._out_view is None:
            return False
        return bool(np.may_share_memory(array, self._out_view))

    def close(self) -> None:
        """停止流并释放节点 / Stop streaming and release the nodes."""
        self._in_view = None
        self._out_view = None
        for queue in (self._input, self._output):
            if queue is None:
                continue
            try:
                queue.stream(False)
            except OSError:
                pass
            queue.close()
        self._input = None
        self._output = None
        for fd in (self._out_fd, self._cap_fd):
            if fd >= 0:
                os.close(fd)
        self._out_fd = -1
        self._cap_fd = -1
