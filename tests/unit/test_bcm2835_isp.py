"""bcm2835-isp 驱动单元测试（无需硬件）/ bcm2835-isp driver unit tests (no hardware).

载荷测试需要已构建的内核头文件绑定，未构建时跳过（见 _bcm2835_isp_build.py）。
Payload tests need the built kernel header bindings and are skipped without
them (see _bcm2835_isp_build.py).
"""

from __future__ import annotations

import errno

import pytest

from ogscope.platform.hardware import bcm2835_isp as isp_module
from ogscope.platform.hardware.bcm2835_isp import (
    GAMMA_POINTS,
    Bcm2835Isp,
    IspError,
    gamma_curve,
)


@pytest.mark.unit
def test_missing_bindings_leave_the_isp_unavailable(monkeypatch) -> None:
    """未构建绑定时不打开任何节点 / Without bindings no node is opened."""
    monkeypatch.setattr(
        isp_module, "_BINDINGS_ERROR", "bcm2835-isp bindings not built: x"
    )
    monkeypatch.setattr(isp_module.os, "open", lambda *_a: pytest.fail("node opened"))
    with pytest.raises(IspError, match="bindings not built"):
        Bcm2835Isp(1280, 720, output_node="/dev/video13", capture_node="/dev/video14")


@pytest.mark.unit
def test_gamma_curve_is_strictly_increasing_and_dense_near_black() -> None:
    xs, ys = gamma_curve(2.2)
    assert len(xs) == len(ys) == GAMMA_POINTS
    assert xs[0] == 0 and xs[-1] == 65535 and ys[-1] == 65535
    assert all(b > a for a, b in zip(xs, xs[1:]))
    # Faint stars live in the first few percent: most points sit there.
    # 暗星集中在最暗的几个百分点，大部分取点落在这里。
    assert sum(x < 65535 * 0.05 for x in xs) >= 10
    assert ys[1] == round(65535 * (xs[1] / 65535) ** (1 / 2.2))


def _bindings():
    return pytest.importorskip("ogscope.platform.hardware._bcm2835_isp_cffi")


class _RecordingIsp(Bcm2835Isp):
    """不打开设备、只记录控件载荷 / Records control payloads without a device."""

    def __init__(self) -> None:  # noqa: D107 - no hardware
        self.sent: list[tuple[int, object]] = []

    def _set_controls(self, controls):  # type: ignore[override]
        self.sent.extend(controls)


@pytest.mark.unit
def test_controls_fill_the_kernel_structures() -> None:
    lib = _bindings().lib
    isp = _RecordingIsp()
    isp.disable_enhancements()
    isp.set_black_level(240 << 4)
    xs, ys = gamma_curve(2.2)
    isp.set_gamma(xs, ys)
    isp.set_identity_ccm()
    isp.set_white_balance(1.5, 0.75)
    sent = dict(isp.sent)

    # Enhancements off; black level enabled on all three channels.
    # 增强关闭；三个通道都启用黑电平。
    assert sent[lib.V4L2_CID_USER_BCM2835_ISP_DENOISE].enabled == 0
    assert sent[lib.V4L2_CID_USER_BCM2835_ISP_SHARPEN].enabled == 0
    assert sent[lib.V4L2_CID_USER_BCM2835_ISP_DPC].enabled == 0
    assert sent[lib.V4L2_CID_USER_BCM2835_ISP_CDN].enabled == 0
    black = sent[lib.V4L2_CID_USER_BCM2835_ISP_BLACK_LEVEL]
    assert (
        black.enabled,
        black.black_level_r,
        black.black_level_g,
        black.black_level_b,
    ) == (
        1,
        3840,
        3840,
        3840,
    )
    gamma = sent[lib.V4L2_CID_USER_BCM2835_ISP_GAMMA]
    assert gamma.enabled == 1 and list(gamma.x) == xs and list(gamma.y) == ys
    ccm = sent[lib.V4L2_CID_USER_BCM2835_ISP_CC_MATRIX].ccm
    assert [[(c.num, c.den) for c in row] for row in ccm.ccm] == [
        [(1, 1), (0, 1), (0, 1)],
        [(0, 1), (1, 1), (0, 1)],
        [(0, 1), (0, 1), (1, 1)],
    ]
    assert sent[lib.V4L2_CID_RED_BALANCE] == 1500
    assert sent[lib.V4L2_CID_BLUE_BALANCE] == 750


@pytest.mark.unit
def test_failed_ioctls_raise_oserror_with_errno() -> None:
    _bindings()
    isp = object.__new__(Bcm2835Isp)
    isp._out_fd = -1
    with pytest.raises(OSError) as raised:
        isp.set_white_balance(1.0, 1.0)
    assert raised.value.errno == errno.EBADF


def _sysfs(tmp_path, nodes: dict[int, tuple[str, int]]):
    """伪造 /sys/class/video4linux / Fake /sys/class/video4linux."""
    for number, (name, index) in nodes.items():
        entry = tmp_path / f"video{number}"
        entry.mkdir()
        (entry / "name").write_text(name + "\n")
        (entry / "index").write_text(f"{index}\n")
    return tmp_path


# The Zero 2 W listing: unicam, then two ISP instances with identical names.
# Zero 2 W 的实际列表：unicam 之后是两个同名的 ISP 实例。
_BOARD = {
    0: ("unicam-image", 0),
    1: ("unicam-embedded", 1),
    13: ("bcm2835-isp-output0", 0),
    14: ("bcm2835-isp-capture0", 1),
    15: ("bcm2835-isp-capture1", 2),
    16: ("bcm2835-isp-stats2", 3),
    20: ("bcm2835-isp-output0", 0),
    21: ("bcm2835-isp-capture0", 1),
    22: ("bcm2835-isp-capture1", 2),
    23: ("bcm2835-isp-stats2", 3),
}


@pytest.mark.unit
def test_isp_nodes_come_from_the_v4l2_device_list(tmp_path) -> None:
    assert isp_module.find_isp_nodes(_sysfs(tmp_path, _BOARD)) == [
        ("/dev/video13", "/dev/video14"),
        ("/dev/video20", "/dev/video21"),
    ]


@pytest.mark.unit
def test_isp_lookup_follows_renumbered_nodes(tmp_path) -> None:
    """节点号不固定（如 video100 排在 video99 之后）/ Node numbers are not fixed."""
    renumbered = {
        2: ("bcm2835-isp-output0", 0),
        3: ("bcm2835-isp-capture0", 1),
        4: ("bcm2835-isp-stats2", 3),
        99: ("bcm2835-isp-output0", 0),
        100: ("bcm2835-isp-capture0", 1),
        101: ("bcm2835-isp-output0", 0),  # incomplete instance / 不完整实例
    }
    assert isp_module.find_isp_nodes(_sysfs(tmp_path, renumbered), "/dev") == [
        ("/dev/video2", "/dev/video3"),
        ("/dev/video99", "/dev/video100"),
    ]


@pytest.mark.unit
def test_no_isp_in_the_device_list(tmp_path) -> None:
    assert isp_module.find_isp_nodes(_sysfs(tmp_path, {0: ("unicam-image", 0)})) == []
    assert isp_module.find_isp_nodes(tmp_path / "missing") == []


@pytest.mark.unit
def test_open_first_tries_each_listed_instance(monkeypatch) -> None:
    tried: list[str] = []
    listed = [("/dev/video13", "/dev/video14"), ("/dev/video20", "/dev/video21")]
    monkeypatch.setattr(isp_module, "find_isp_nodes", lambda: listed)

    def _fake_init(
        self, width, height, bayer_pattern, *, output_node, capture_node, timeout_s=2.0
    ):
        tried.append(output_node)
        if output_node == "/dev/video13":
            raise IspError("busy")
        self.nodes = (output_node, capture_node)

    monkeypatch.setattr(Bcm2835Isp, "__init__", _fake_init)
    isp = Bcm2835Isp.open_first(1280, 720, "RGGB")
    assert tried == ["/dev/video13", "/dev/video20"] and isp.nodes == listed[1]

    monkeypatch.setattr(isp_module, "find_isp_nodes", lambda: [])
    with pytest.raises(IspError, match="no bcm2835-isp in the V4L2 device list"):
        Bcm2835Isp.open_first(1280, 720, "RGGB")
