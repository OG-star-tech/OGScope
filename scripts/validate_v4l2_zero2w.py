#!/usr/bin/env python3
"""Board-specific hardware validation for the V4L2 RAW backend on a real Zero2W.

板端验证脚本：在真实 Zero2W 硬件上验证 V4L2 RAW 后端 - 媒体管线配置、控件回读、
实际抓帧与内存占用。配置来自本设备（IP 192.168.0.41）用 `media-ctl -p -d
/dev/media0` 与 `v4l2-ctl --list-ctrls`/`--list-formats-ext` 实测发现，*不是*照抄
docs/development/v4l2-auto-exposure.md 的 CM0 示例 - 详见
docs/development/v4l2-zero2w-board-validation.md 的完整对比与结果。

Board-discovered config below (NOT a copy of the doc's CM0 example - this board
differs on bit depth, subdev numbering, and receiver pad configurability). See
docs/development/v4l2-zero2w-board-validation.md for the full discovery process
and results.

Usage (on-device, service stopped first so /dev/video0 is free):
    systemctl stop ogscope.service
    python3 scripts/validate_v4l2_zero2w.py init       # media pipeline + control discovery only
    python3 scripts/validate_v4l2_zero2w.py exposure   # exposure sweep with readback
    python3 scripts/validate_v4l2_zero2w.py capture    # real RAW capture -> debayer -> RGB888
    python3 scripts/validate_v4l2_zero2w.py memory      # capture loop + peak RSS/CMA report
    systemctl start ogscope.service
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run from the repo root or with the package already on PYTHONPATH; this is
# only a convenience fallback for `python3 scripts/validate_v4l2_zero2w.py`
# invoked directly from a checkout.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np  # noqa: E402

from ogscope.platform.hardware.v4l2_camera import V4L2RawCamera  # noqa: E402

# Real, live-discovered topology for the Zero2W at 192.168.0.41 - see the
# module docstring and docs/development/v4l2-zero2w-board-validation.md.
# Differs from docs/development/v4l2-auto-exposure.md's CM0-validated example:
# 12-bit RAW (not 10-bit), sink-only Unicam receiver (pads -1), and different
# subdev node numbering.
CONFIG = {
    "device": "/dev/video0",
    "v4l2_sensor_subdev": "/dev/v4l-subdev1",
    "v4l2_media_device": "/dev/media0",
    "v4l2_configure_media_pipeline": True,
    "v4l2_sensor_entity": "imx327 10-001a",
    "v4l2_receiver_entity": "unicam-image",
    "v4l2_sensor_pad": 0,
    "v4l2_receiver_sink_pad": -1,
    "v4l2_receiver_source_pad": -1,
    "v4l2_media_bus_format": "SRGGB12_1X12",
    "v4l2_pixel_format": "RG12",
    "v4l2_bit_depth": 12,
    "v4l2_bayer_pattern": "RGGB",
    "v4l2_active_width": 1280,
    "v4l2_active_height": 720,
    "width": 1280,
    "height": 720,
    "fps": 5,
    "exposure_us": 10_000,
    "analogue_gain": 1.0,
    "sampling_mode": "native",
    "v4l2_ae_trace_enabled": True,
    "v4l2_ae_trace_dir": "/tmp/ogscope-v4l2-ae-traces",
}


def _print_camera_info(cam: V4L2RawCamera) -> None:
    info = cam.get_camera_info()
    for key in (
        "driver",
        "backend",
        "media_pipeline",
        "control_readback",
        "signal_levels",
        "line_duration_us",
        "line_duration_source",
        "actual_exposure_us",
        "actual_analogue_gain",
        "ae_state",
    ):
        if key in info:
            print(f"  {key}: {info[key]}")


def stage_init() -> V4L2RawCamera | None:
    print("=== init ===")
    cam = V4L2RawCamera(dict(CONFIG))
    ok = cam.initialize()
    print(f"initialize() -> {ok}")
    _print_camera_info(cam)
    if not ok:
        return None
    return cam


def stage_capture(num_frames: int = 3) -> None:
    print("=== capture ===")
    cam = stage_init()
    if cam is None:
        print("FAIL: init failed, cannot capture")
        return
    try:
        started = cam.start_capture()
        print(f"start_capture() -> {started}")
        if not started:
            return
        for i in range(num_frames):
            frame = cam.capture_image()
            if frame is None:
                print(f"frame {i}: None (capture failed)")
                continue
            arr = np.asarray(frame)
            print(
                f"frame {i}: shape={arr.shape} dtype={arr.dtype} "
                f"min={arr.min()} max={arr.max()} mean={arr.mean():.2f}"
            )
    finally:
        cam.close()


def stage_exposure() -> None:
    print("=== exposure sweep ===")
    cam = stage_init()
    if cam is None:
        print("FAIL: init failed, cannot test exposure")
        return
    try:
        for exposure_us in (1_000, 10_000, 50_000, 200_000):
            ok = cam.set_exposure(exposure_us)
            info = cam.get_camera_info()
            print(
                f"set_exposure({exposure_us}) -> {ok}  "
                f"actual_exposure_us={info.get('actual_exposure_us')} "
                f"control_readback={info.get('control_readback')}"
            )
    finally:
        cam.close()


def stage_memory(num_frames: int = 40) -> None:
    """报告长时间抓帧下的峰值 RSS 与 CMA 占用，便于与 picamera2 基线对比 /
    Report peak RSS/CMA under sustained capture, for comparison against the
    picamera2 baseline (see the board validation doc for that measurement)."""
    print("=== memory (capture loop + /proc/self/status + /proc/meminfo) ===")
    cam = stage_init()
    if cam is None:
        print("FAIL: init failed, cannot measure")
        return
    try:
        started = cam.start_capture()
        print(f"start_capture() -> {started}")
        if not started:
            return
        for _ in range(num_frames):
            cam.capture_image()
        pid = None
        try:
            import os

            pid = os.getpid()
        except Exception:  # noqa: BLE001
            pass
        if pid is not None:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith(("VmRSS", "VmHWM")):
                        print(f"  {line.strip()}")
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("Cma"):
                    print(f"  {line.strip()}")
    finally:
        cam.close()


STAGES = {
    "init": lambda: (stage_init() and None),
    "capture": stage_capture,
    "exposure": stage_exposure,
    "memory": stage_memory,
}


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "init"
    fn = STAGES.get(stage)
    if fn is None:
        print(f"unknown stage {stage!r}, choose from {list(STAGES)}")
        sys.exit(2)
    try:
        fn()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
