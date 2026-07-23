"""
大尺度背景减除单元测试 / Unit tests for large-scale background flattening.
"""

import cv2
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


@pytest.mark.unit
def test_background_optimization_matches_reference_math() -> None:
    """复用缓冲后的结果应与原公式一致 / Buffer reuse must preserve reference output."""
    rng = np.random.default_rng(42)
    bgr = rng.integers(0, 256, size=(96, 128, 3), dtype=np.uint8)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    sw, sh = 64, 48
    small = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_AREA)
    bg_small = cv2.GaussianBlur(small, (0, 0), sigmaX=2.0, sigmaY=2.0)
    bg = cv2.resize(bg_small, (128, 96), interpolation=cv2.INTER_LINEAR).astype(
        np.float32
    )
    corr = np.clip(gray - bg + float(np.mean(gray)), 1e-3, 255.0)
    ratio = np.clip(corr / np.maximum(gray, 1e-3), 0.0, 4.0)
    expected = np.clip(
        np.round(bgr.astype(np.float32) * ratio[..., np.newaxis]), 0, 255
    ).astype(np.uint8)

    actual = subtract_large_scale_background_bgr(bgr, downsample_max_side=64)
    np.testing.assert_array_equal(actual, expected)
