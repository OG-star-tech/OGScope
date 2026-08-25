"""星点焦点测量测试 / Star focus metric tests."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from ogscope.domain.camera.focus import FocusMetricAnalyzer


def _star_field(
    *, sigma: float, saturated: bool = False, noise_std: float = 0.0
) -> np.ndarray:
    """生成可重复的合成星场 / Build a deterministic synthetic star field."""
    height, width = 240, 320
    yy, xx = np.indices((height, width), dtype=np.float32)
    frame = np.full((height, width), 8.0, dtype=np.float32)
    stars = [(70, 62, 150.0), (160, 78, 125.0), (245, 135, 180.0), (105, 175, 110.0)]
    for x, y, amplitude in stars:
        value = 255.0 if saturated and x == 70 else amplitude
        frame += value * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2.0 * sigma**2))
    if noise_std > 0:
        rng = np.random.default_rng(42)
        frame += rng.normal(0.0, noise_std, frame.shape)
    frame = np.clip(frame, 0.0, 255.0).astype(np.uint8)
    return cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)


@pytest.mark.unit
def test_focus_hfd_increases_with_blur() -> None:
    analyzer = FocusMetricAnalyzer(min_snr=4.0)

    sharp = analyzer.analyze(_star_field(sigma=1.4), frame_id=1, timestamp=1.0)
    blurred = analyzer.analyze(_star_field(sigma=4.2), frame_id=2, timestamp=2.0)

    assert sharp["state"] == "measuring"
    assert blurred["state"] == "measuring"
    assert sharp["stars_used"] >= 3
    assert blurred["stars_used"] >= 3
    assert sharp["aggregate"]["median_hfd_px"] < blurred["aggregate"]["median_hfd_px"]
    assert (
        sharp["aggregate"]["median_concentration"]
        > blurred["aggregate"]["median_concentration"]
    )


@pytest.mark.unit
def test_focus_hfd_remains_directional_with_sensor_noise() -> None:
    analyzer = FocusMetricAnalyzer(min_snr=4.0)

    sharp = analyzer.analyze(
        _star_field(sigma=1.4, noise_std=4.0), frame_id=11, timestamp=11.0
    )
    blurred = analyzer.analyze(
        _star_field(sigma=4.2, noise_std=4.0), frame_id=12, timestamp=12.0
    )

    assert sharp["stars_used"] >= 3
    assert blurred["stars_used"] >= 3
    assert sharp["aggregate"]["median_hfd_px"] < blurred["aggregate"]["median_hfd_px"]


@pytest.mark.unit
def test_focus_reports_empty_frame_without_false_score() -> None:
    analyzer = FocusMetricAnalyzer()
    frame = np.full((120, 160, 3), 10, dtype=np.uint8)

    result = analyzer.analyze(frame, frame_id=3, timestamp=3.0)

    assert result["state"] == "no_stars"
    assert result["aggregate"] is None
    assert result["selected_star"] is None
    assert "no_stars_detected" in result["warnings"]


@pytest.mark.unit
def test_focus_selects_nearest_target_star() -> None:
    analyzer = FocusMetricAnalyzer(min_snr=4.0)
    result = analyzer.analyze(
        _star_field(sigma=1.8),
        frame_id=4,
        timestamp=4.0,
        target_x=245 / 320,
        target_y=135 / 240,
    )

    selected = result["selected_star"]
    assert selected is not None
    assert selected["x"] == pytest.approx(245, abs=3)
    assert selected["y"] == pytest.approx(135, abs=3)


@pytest.mark.unit
def test_focus_rejects_saturated_star_from_aggregate() -> None:
    analyzer = FocusMetricAnalyzer(min_snr=4.0)
    result = analyzer.analyze(
        _star_field(sigma=1.8, saturated=True), frame_id=5, timestamp=5.0
    )

    assert result["stars_used"] >= 3
    assert "saturated_stars_rejected" in result["warnings"]


@pytest.mark.unit
def test_focus_detects_undersampled_stars_with_sensor_noise() -> None:
    """默认焦点管线保留噪声中的小星点 / Default focus pipeline keeps tiny noisy stars."""
    analyzer = FocusMetricAnalyzer()

    result = analyzer.analyze(
        _star_field(sigma=0.65, noise_std=4.0),
        frame_id=6,
        timestamp=6.0,
    )

    assert result["state"] == "measuring"
    assert result["stars_used"] >= 3
    assert result["detection"]["pipeline"] == "focus_local_sigma_v1"

    undersampled = analyzer.analyze(
        _star_field(sigma=0.45), frame_id=61, timestamp=61.0
    )
    assert "undersampled_stars" in undersampled["warnings"]


@pytest.mark.unit
def test_focus_clicked_target_bypasses_global_candidate_limit() -> None:
    """点击目标直接局部测量，不受全局候选上限影响 / Clicked target bypasses auto limit."""
    height, width = 180, 260
    yy, xx = np.indices((height, width), dtype=np.float32)
    frame = np.full((height, width), 8.0, dtype=np.float32)
    frame += 180.0 * np.exp(-((xx - 70) ** 2 + (yy - 70) ** 2) / (2.0 * 2.0**2))
    frame += 70.0 * np.exp(-((xx - 200) ** 2 + (yy - 120) ** 2) / (2.0 * 0.8**2))
    rgb = cv2.cvtColor(np.clip(frame, 0.0, 255.0).astype(np.uint8), cv2.COLOR_GRAY2RGB)
    analyzer = FocusMetricAnalyzer(max_stars=1)

    automatic = analyzer.analyze(rgb, frame_id=7, timestamp=7.0)
    targeted = analyzer.analyze(
        rgb,
        frame_id=8,
        timestamp=8.0,
        target_x=200 / width,
        target_y=120 / height,
    )

    assert automatic["selected_star"]["x"] == pytest.approx(70, abs=3)
    assert targeted["selected_star"] is not None
    assert targeted["selected_star"]["source"] == "target"
    assert targeted["selected_star"]["x"] == pytest.approx(200, abs=3)
    assert targeted["detection"]["target_forced"] is True


@pytest.mark.unit
def test_focus_auto_mode_rejects_isolated_hot_pixels() -> None:
    """自动模式不把孤立热像素作为焦点星 / Auto mode rejects isolated hot pixels."""
    frame = np.full((180, 260, 3), 8, dtype=np.uint8)
    for y, x in ((40, 50), (60, 110), (90, 180), (130, 220)):
        frame[y, x, :] = 180

    result = FocusMetricAnalyzer().analyze(frame, frame_id=9, timestamp=9.0)

    assert result["stars_detected"] == 4
    assert result["stars_used"] == 0
    assert result["detection"]["quality_rejections"]["hot_pixel_like"] == 4
