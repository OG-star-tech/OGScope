"""共享 MJPEG 质量变体回归测试 / Shared MJPEG quality-variant regression tests."""

from __future__ import annotations

import asyncio
import time
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import cv2
import numpy as np
import pytest

from ogscope.domain.camera.encoding import OpenCVEncoder
from ogscope.web.api.debug import services as debug_services
from ogscope.web.camera_shared import CameraManager


def _red_jpeg() -> bytes:
    bgr = np.zeros((16, 24, 3), dtype=np.uint8)
    bgr[:, :, 2] = 240
    ok, encoded = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 55])
    assert ok
    return encoded.tobytes()


def _publish(manager: CameraManager, frame_id: int, *, raw=None, source="RGB888"):
    manager._frame_id = frame_id
    manager._latest_jpeg = _red_jpeg()
    manager._latest_raw = raw
    manager._latest_w = 24
    manager._latest_h = 16
    manager._last_jpeg_source_format = source
    manager._stream_jpeg_variants.clear()


@pytest.fixture
def manager(monkeypatch):
    instance = CameraManager()
    instance._jpeg_quality = 55
    instance._preview_encoder = OpenCVEncoder()
    instance.ensure_started = AsyncMock()
    instance.get_raw_frame = AsyncMock(side_effect=AssertionError("extra camera read"))
    instance._read_frame_sync = Mock(side_effect=AssertionError("extra camera read"))
    _publish(instance, 1)
    monkeypatch.setattr(debug_services, "get_camera_manager", lambda: instance)
    yield instance
    instance._jpeg_executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_default_quality_reuses_original_jpeg_without_encoding(manager):
    manager._encode_stream_jpeg_sync = Mock(side_effect=AssertionError("extra encode"))

    code, encoded, frame_id = (
        await debug_services.DebugCameraService.get_stream_frame_bytes("jpeg", 55)
    )

    assert (code, frame_id) == (200, 1)
    assert encoded is manager._latest_jpeg
    manager._encode_stream_jpeg_sync.assert_not_called()
    manager.get_raw_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_custom_quality_shares_encode_without_raw_capture(manager):
    original_encode = manager._encode_stream_jpeg_sync
    manager._encode_stream_jpeg_sync = Mock(wraps=original_encode)

    results = await asyncio.gather(
        *(
            debug_services.DebugCameraService.get_stream_frame_bytes("jpeg", 75)
            for _ in range(8)
        )
    )
    cached = await debug_services.DebugCameraService.get_stream_frame_bytes("jpeg", 75)

    assert all(result == cached for result in results)
    assert cached[0] == 200
    assert cached[2] == 1
    assert manager._encode_stream_jpeg_sync.call_count == 1
    assert manager._latest_raw is None
    manager.get_raw_frame.assert_not_awaited()
    manager._read_frame_sync.assert_not_called()
    assert await debug_services.DebugCameraService.get_stream_frame_bytes(
        "jpeg", 75, since_frame_id=1
    ) == (304, None, 1)


@pytest.mark.asyncio
async def test_transcoded_jpeg_preserves_red_blue_order_and_requested_quality(
    manager, monkeypatch
):
    seen = []
    encode = manager._preview_encoder.encode_jpeg

    def record_encode(frame, *, quality, source_format):
        seen.append((quality, source_format))
        return encode(frame, quality=quality, source_format=source_format)

    monkeypatch.setattr(manager._preview_encoder, "encode_jpeg", record_encode)
    _, encoded, _ = await debug_services.DebugCameraService.get_stream_frame_bytes(
        "jpeg", 75
    )
    decoded = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert seen == [(75, "BGR888")]
    assert float(decoded[:, :, 2].mean()) > 220
    assert float(decoded[:, :, 0].mean()) < 20


@pytest.mark.asyncio
@pytest.mark.parametrize("source_format", ["RGB888", "BGR888"])
async def test_existing_raw_snapshot_is_used_before_jpeg_decode(
    manager, monkeypatch, source_format
):
    blue = np.zeros((16, 24, 3), dtype=np.uint8)
    blue[:, :, 2 if source_format == "RGB888" else 0] = 240
    _publish(manager, 2, raw=blue, source=source_format)
    original_decode = cv2.imdecode
    monkeypatch.setattr(
        cv2, "imdecode", Mock(side_effect=AssertionError("RAW was ignored"))
    )

    code, encoded, frame_id = (
        await debug_services.DebugCameraService.get_stream_frame_bytes("jpeg", 75)
    )
    decoded = original_decode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert (code, frame_id) == (200, 2)
    assert float(decoded[:, :, 0].mean()) > 220
    assert float(decoded[:, :, 2].mean()) < 20
    manager.get_raw_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_cancellation_does_not_duplicate_shared_encode(manager):
    started, release = Event(), Event()
    calls = []

    def encode(snap, quality):
        calls.append((snap.frame_id, quality))
        started.set()
        assert release.wait(2)
        return b"encoded"

    manager._encode_stream_jpeg_sync = encode
    snap = await manager.get_cached_frame_snapshot()
    first = asyncio.create_task(manager.get_stream_jpeg(snap, 75))
    assert await asyncio.to_thread(started.wait, 2)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(manager.get_stream_jpeg(snap, 75))
    release.set()

    assert await second == b"encoded"
    assert calls == [(1, 75)]
    assert await manager.get_stream_jpeg(snap, 75) == b"encoded"


@pytest.mark.asyncio
async def test_new_frame_cannot_relabel_an_inflight_old_frame(manager):
    started, release = Event(), Event()

    def encode(snap, quality):
        started.set()
        assert release.wait(2)
        return f"frame-{snap.frame_id}".encode()

    manager._encode_stream_jpeg_sync = encode
    request = asyncio.create_task(
        debug_services.DebugCameraService.get_stream_frame_bytes("jpeg", 75)
    )
    assert await asyncio.to_thread(started.wait, 2)
    _publish(manager, 2)
    release.set()

    assert await request == (200, b"frame-1", 1)
    assert not manager._stream_jpeg_variants
    assert await debug_services.DebugCameraService.get_stream_frame_bytes(
        "jpeg", 75
    ) == (200, b"frame-2", 2)


@pytest.mark.asyncio
async def test_encode_failure_can_retry_the_same_frame_without_capture(manager):
    manager._encode_stream_jpeg_sync = Mock(
        side_effect=[RuntimeError("failed"), b"recovered"]
    )

    assert await debug_services.DebugCameraService.get_stream_frame_bytes(
        "jpeg", 75
    ) == (500, None, 1)
    assert await debug_services.DebugCameraService.get_stream_frame_bytes(
        "jpeg", 75
    ) == (200, b"recovered", 1)
    manager.get_raw_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_cached_jpeg_fails_then_recovers_without_capture(manager):
    manager._latest_jpeg = b"invalid jpeg"
    assert await debug_services.DebugCameraService.get_stream_frame_bytes(
        "jpeg", 75
    ) == (
        500,
        None,
        1,
    )
    manager._latest_jpeg = _red_jpeg()

    code, encoded, frame_id = (
        await debug_services.DebugCameraService.get_stream_frame_bytes("jpeg", 75)
    )

    assert (code, frame_id) == (200, 1)
    assert (
        cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
        is not None
    )
    manager.get_raw_frame.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "encoded_size, expected_count", [(10, 4), (400_000, 2), (1_048_577, 0)]
)
async def test_variant_cache_is_bounded_by_count_and_bytes(
    manager, encoded_size, expected_count
):
    manager._encode_stream_jpeg_sync = Mock(return_value=b"x" * encoded_size)
    snap = await manager.get_cached_frame_snapshot()
    for quality in range(70, 76):
        assert len(await manager.get_stream_jpeg(snap, quality)) == encoded_size

    assert len(manager._stream_jpeg_variants) == expected_count
    assert sum(map(len, manager._stream_jpeg_variants.values())) <= 1_048_576


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "auto_exposure, exposure_us, frame_duration_us, expected",
    [
        (True, 1000, 16667, "processing_limit"),
        (True, 500000, 500000, "auto_exposure_long"),
        (False, 500000, 500000, "processing_limit"),
    ],
)
async def test_low_fps_needs_duration_evidence_before_long_ae_label(
    manager, auto_exposure, exposure_us, frame_duration_us, expected
):
    manager._target_fps = 8
    manager._camera = SimpleNamespace(
        get_camera_info=lambda: {
            "fps": 8,
            "auto_exposure": auto_exposure,
            "actual_exposure_us": exposure_us,
            "frame_duration_us": frame_duration_us,
        }
    )
    now = time.monotonic()
    manager._capture_timestamps.extend([now - 1.0, now - 0.5, now])

    assert (await manager.stream_metrics())["throttle_reason"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preview_target, actual_fps, exposure_us, expected",
    [
        (2, 2, 1000, "preview_rate_limit"),
        (8, 4, 1000, "processing_limit"),
        (2, 1, 500000, "processing_limit"),
    ],
)
async def test_throughput_diagnostics_use_the_effective_preview_target(
    manager, monkeypatch, preview_target, actual_fps, exposure_us, expected
):
    """主动预览限帧与实际吞吐不足须区分 / Distinguish configured pacing from deficient throughput."""
    manager._target_fps = preview_target
    manager._camera = SimpleNamespace(
        get_camera_info=lambda: {
            "fps": 8,
            "auto_exposure": True,
            "actual_exposure_us": exposure_us,
            "frame_duration_us": max(16667, exposure_us),
        }
    )
    monkeypatch.setattr(manager, "_rate", lambda _: actual_fps)

    assert (await manager.stream_metrics())["throttle_reason"] == expected
