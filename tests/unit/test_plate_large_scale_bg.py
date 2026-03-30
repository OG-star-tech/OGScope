"""
大尺度背景减除单元测试 / Unit tests for large-scale background flattening.
"""

import numpy as np
import pytest

from ogscope.algorithms.plate_solve.solver import subtract_large_scale_background_bgr


@pytest.mark.unit
def test_subtract_large_scale_background_bgr_shape_and_range() -> None:
    """输出与输入同形且值域在 uint8 / Output shape matches and values in uint8 range."""
    h, w = 120, 160
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[:, :, 1] = np.linspace(0, 80, w, dtype=np.uint8)
    out = subtract_large_scale_background_bgr(bgr, downsample_max_side=64)
    assert out.shape == bgr.shape
    assert out.dtype == np.uint8
    assert int(out.min()) >= 0 and int(out.max()) <= 255


@pytest.mark.unit
def test_subtract_large_scale_background_bgr_non_bgr_passthrough() -> None:
    """非三通道图原样返回 / Non-3-channel frames pass through unchanged."""
    gray = np.zeros((10, 10), dtype=np.uint8)
    assert subtract_large_scale_background_bgr(gray, downsample_max_side=32) is gray
