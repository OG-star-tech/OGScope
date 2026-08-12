"""AE 诊断轨迹和回放测试 / AE diagnostic trace and replay tests."""

import json
from dataclasses import asdict

import numpy as np
import pytest

from ogscope.domain.camera.ae_diagnostics import (
    AutoExposureTraceLimits,
    AutoExposureTraceRecorder,
    load_trace_events,
    replay_trace_events,
    verify_raw_samples,
)
from ogscope.domain.camera.auto_exposure import AutoExposureLimits, LuminanceStats


def _event(exposure_us: int = 10_000) -> dict:
    stats = LuminanceStats(0.002, 0.01, 0.0, 100)
    return {
        "stats": asdict(stats),
        "observed": {"exposure_us": exposure_us, "analogue_gain": 1.0},
        "decision": {"state": "adjusting"},
        "applied": {"readback_verified": True},
    }


@pytest.mark.unit
def test_trace_recorder_is_bounded_and_saves_downsampled_raw(tmp_path) -> None:
    recorder = AutoExposureTraceRecorder(
        enabled=True,
        root_dir=tmp_path,
        limits=AutoExposureTraceLimits(
            max_events=2, raw_sample_interval=1, max_raw_samples=1, raw_max_side=16
        ),
    )
    recorder.start({"test": True})
    raw = np.arange(64 * 32, dtype=np.uint16).reshape(32, 64)

    recorder.record(_event(), raw)
    recorder.record(_event(20_000), raw)
    recorder.record(_event(40_000), raw)
    recorder.close()

    status = recorder.status()
    assert status["event_count"] == 2
    assert status["raw_sample_count"] == 1
    assert status["limit_reached"] is True
    events = load_trace_events(recorder.session_dir)
    assert len(events) == 2
    with np.load(recorder.session_dir / events[0]["raw_sample"]) as sample:
        assert max(sample["raw"].shape) <= 16
        assert tuple(sample["original_shape"]) == (32, 64)


@pytest.mark.unit
def test_disabled_trace_does_not_create_directories(tmp_path) -> None:
    recorder = AutoExposureTraceRecorder(enabled=False, root_dir=tmp_path / "trace")

    recorder.start({"test": True})
    recorder.record(_event(), np.zeros((4, 4), dtype=np.uint16))

    assert recorder.status()["session_dir"] is None
    assert not (tmp_path / "trace").exists()


@pytest.mark.unit
def test_trace_replay_and_raw_verification(tmp_path) -> None:
    limits = AutoExposureLimits(settle_frames=0)
    recorder = AutoExposureTraceRecorder(
        enabled=True,
        root_dir=tmp_path,
        limits=AutoExposureTraceLimits(
            max_events=5, raw_sample_interval=1, max_raw_samples=1, raw_max_side=32
        ),
    )
    recorder.start(
        {
            "bit_depth": 10,
            "signal_levels": {"black_level": 64, "white_level": 1023},
            "auto_exposure_limits": asdict(limits),
        }
    )
    recorder.record(_event(), np.full((8, 8), 80, dtype=np.uint16))
    recorder.close()

    decisions = replay_trace_events(load_trace_events(recorder.session_dir), limits)
    verified = verify_raw_samples(
        recorder.session_dir,
        bit_depth=10,
        black_level=64,
        white_level=1023,
        highlight_percentile=99.8,
    )

    assert decisions[0].exposure_us == 20_000
    assert verified[0]["stats"]["background"] == pytest.approx(16 / 959, rel=0.02)


@pytest.mark.unit
def test_raw_verification_rejects_path_escape(tmp_path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    (session / "events.jsonl").write_text(
        json.dumps({"sequence": 1, "raw_sample": "../outside.npz"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes session"):
        verify_raw_samples(
            session,
            bit_depth=10,
            black_level=0,
            white_level=1023,
            highlight_percentile=99.8,
        )
