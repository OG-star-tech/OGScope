"""开发者解算快照测试 / Developer solve snapshot tests."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import numpy as np
import pytest

from ogscope.web.api.analysis.services import AnalysisService


def _service_with_encoder(encoder: object) -> AnalysisService:
    """构造不触碰文件系统的最小服务 / Build a minimal service without filesystem setup."""
    service = AnalysisService.__new__(AnalysisService)
    service._solve_snapshot_lock = threading.Lock()
    service._solve_snapshot_token = ""
    service._solve_snapshot_bytes = None
    service._solve_snapshot_meta = {}
    service._solve_snapshot_encoder = encoder
    service._solve_snapshot_quality = 70
    return service


@pytest.mark.unit
def test_debug_snapshot_keeps_only_the_latest_compressed_frame() -> None:
    """只保留当前压缩帧且旧令牌失效 / Keep one compressed frame and expire old tokens."""

    class Encoder:
        def encode_jpeg(self, _frame, **_kwargs):
            return SimpleNamespace(data=b"jpeg", encoder="test")

    service = _service_with_encoder(Encoder())
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    first = service._encode_debug_solve_snapshot(frame, 10)
    second = service._encode_debug_solve_snapshot(frame, 11)

    assert first["token"] != second["token"]
    assert service.get_debug_solve_snapshot(second["token"])[0] == b"jpeg"
    with pytest.raises(FileNotFoundError):
        service.get_debug_solve_snapshot(first["token"])


@pytest.mark.unit
def test_debug_snapshot_failure_is_non_fatal() -> None:
    """编码器异常仅让快照降级 / Encoder failure only degrades the snapshot."""

    class Encoder:
        def encode_jpeg(self, _frame, **_kwargs):
            raise RuntimeError("encoder unavailable")

    service = _service_with_encoder(Encoder())
    result = service._encode_debug_solve_snapshot(
        np.zeros((24, 32, 3), dtype=np.uint8),
        12,
    )

    assert result == {"available": False, "reason": "encode_failed"}
    with pytest.raises(FileNotFoundError):
        service.get_debug_solve_snapshot("missing")
