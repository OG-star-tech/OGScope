"""RAW 白平衡的颜色与暗场回归 / RAW WB color and dark-scene regressions."""

import numpy as np
import pytest

from ogscope.domain.camera.white_balance import BAYER_CHANNELS, RawAutoWhiteBalance
from ogscope.platform.hardware.v4l2_camera import V4L2RawCamera


@pytest.mark.parametrize("pattern", list(BAYER_CHANNELS))
def test_neutral_reference_converges_without_channel_swap(pattern):
    """相同中性色在四种 CFA 下都恢复灰色 / Recover neutral color with each CFA order."""
    raw = np.empty((240, 320), dtype=np.uint16)
    for y in range(2):
        for x in range(2):
            raw[y::2, x::2] = [640, 1040, 740][BAYER_CHANNELS[pattern][y][x]]
    camera = V4L2RawCamera(
        {
            "v4l2_bit_depth": 12,
            "v4l2_bayer_pattern": pattern,
            "white_balance_mode": "auto",
            "v4l2_black_level": 240,
        }
    )
    camera.black_level = 240
    for _ in range(12):
        camera._awb.observe(
            raw,
            pattern=pattern,
            black=240,
            white=4095,
            exposure_product=1000,
            ready=True,
        )
    rgb = camera._debayer(raw)[4:-4, 4:-4].mean(axis=(0, 1))
    assert max(rgb) - min(rgb) <= 2
    assert camera._awb.state == "converged"


@pytest.mark.parametrize(
    "level,product,ready",
    [
        (240, 1000, True),
        (4095, 1000, True),
        (500, 48_000_000, True),
        (1000, 1000, False),
    ],
)
def test_dark_saturated_and_stale_frames_do_not_change_white_balance(
    level, product, ready
):
    """无可信颜色信号时保持增益 / Hold gains when color information is unreliable."""
    wb = RawAutoWhiteBalance()
    initial = wb.gains
    for _ in range(5):
        wb.observe(
            np.full((240, 320), level, dtype=np.uint16),
            pattern="RGGB",
            black=240,
            white=4095,
            exposure_product=product,
            ready=ready,
        )
    assert wb.gains == initial


def test_white_balance_manual_and_night_modes_do_not_autoadjust():
    """显式模式不会偷偷运行 AWB / Explicit modes never silently enable AWB."""
    camera = V4L2RawCamera({"white_balance_mode": "manual"})
    assert camera.set_white_balance("manual", 1.8, 1.4)
    assert camera._white_balance_gains() == (1.8, 1.0, 1.4)
    assert camera.set_white_balance("night")
    assert camera._white_balance_gains() == (1.1, 1.0, 0.9)
    assert camera.set_white_balance("auto")
    assert camera.get_camera_info()["white_balance_mode"] == "auto"
    assert "auto" in camera.get_camera_info()["capabilities"]["awb_modes"]
