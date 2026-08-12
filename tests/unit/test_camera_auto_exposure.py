"""夜空软件自动曝光单元测试 / Night-sky software auto-exposure unit tests."""

import numpy as np
import pytest

from ogscope.domain.camera.auto_exposure import (
    AutoExposureLimits,
    LuminanceStats,
    NightSkyAutoExposure,
    measure_luminance,
)


@pytest.mark.unit
def test_measure_luminance_uses_sparse_star_highlights() -> None:
    raw = np.full((240, 320), 20, dtype=np.uint16)
    raw.reshape(-1)[::200] = 700

    stats = measure_luminance(raw, bit_depth=10, highlight_percentile=99.7)

    assert stats.background == pytest.approx(20 / 1023, rel=0.05)
    assert stats.highlight > 0.5
    assert stats.saturation_fraction == 0.0


@pytest.mark.unit
def test_dark_scene_increases_exposure_before_gain() -> None:
    ae = NightSkyAutoExposure(
        AutoExposureLimits(max_exposure_us=2_000_000, max_gain=16.0, settle_frames=0)
    )
    dark = LuminanceStats(0.002, 0.01, 0.0, 10_000)

    decision = ae.observe(dark, exposure_us=10_000, analogue_gain=1.0)

    assert decision.changed is True
    assert decision.exposure_us == 20_000
    assert decision.analogue_gain == 1.0
    assert decision.state == "adjusting"


@pytest.mark.unit
def test_dark_scene_uses_gain_after_exposure_limit() -> None:
    ae = NightSkyAutoExposure(
        AutoExposureLimits(max_exposure_us=500_000, max_gain=16.0, settle_frames=0)
    )
    dark = LuminanceStats(0.002, 0.01, 0.0, 10_000)

    decision = ae.observe(dark, exposure_us=500_000, analogue_gain=2.0)

    assert decision.exposure_us == 500_000
    assert decision.analogue_gain == pytest.approx(4.0)


@pytest.mark.unit
def test_saturation_reduces_gain_before_exposure() -> None:
    ae = NightSkyAutoExposure(AutoExposureLimits(settle_frames=0))
    saturated = LuminanceStats(0.2, 1.0, 0.05, 10_000)

    decision = ae.observe(saturated, exposure_us=200_000, analogue_gain=8.0)

    assert decision.analogue_gain < 8.0
    assert decision.exposure_us == 200_000


@pytest.mark.unit
def test_hysteresis_holds_converged_scene() -> None:
    ae = NightSkyAutoExposure(AutoExposureLimits(settle_frames=0))
    balanced = LuminanceStats(0.035, 0.45, 0.0, 10_000)

    decision = ae.observe(balanced, exposure_us=200_000, analogue_gain=4.0)

    assert decision.changed is False
    assert decision.state == "converged"


@pytest.mark.unit
def test_disabled_controller_reports_manual_without_changes() -> None:
    ae = NightSkyAutoExposure(AutoExposureLimits(settle_frames=0))
    ae.set_enabled(False)

    decision = ae.observe(
        LuminanceStats(0.0, 0.0, 0.0, 10_000),
        exposure_us=40_000,
        analogue_gain=3.0,
    )

    assert decision.changed is False
    assert decision.state == "manual"
    assert decision.exposure_us == 40_000
    assert decision.analogue_gain == 3.0
