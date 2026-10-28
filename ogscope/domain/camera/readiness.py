"""Frame-based capture readiness, independent of star matching / 基于新帧判断就绪，不依赖星图匹配。"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from typing import Any, Callable


class CaptureReadiness:
    """Share exposure evidence across preview and analysis / 预览与分析共用曝光证据。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """A restarted camera cannot inherit ready state / 重启相机不得继承就绪状态。"""
        with self._lock:
            self._last_frame = -1
            self._last_seen = 0.0
            self._product: float | None = None
            self._stable_frames = 0
            self._ready = False
            self._reason = "waiting_for_frame"

    def observe(self, sequence: int, info: dict[str, Any]) -> None:
        """Count completed frames, not repeated status polls / 只统计完成帧，不统计重复状态轮询。"""
        with self._lock:
            if sequence == self._last_frame:
                return
            self._last_frame, self._last_seen = sequence, time.monotonic()
            try:
                exposure = float(
                    info.get("actual_exposure_us") or info.get("exposure_us") or 0
                )
                gain = float(
                    info.get("actual_analogue_gain") or info.get("analogue_gain") or 1
                )
                product = exposure * gain
                if not math.isfinite(product) or product <= 0:
                    product = None
            except (TypeError, ValueError):
                product = None
            state = str(info.get("ae_state") or "")
            phase = str(info.get("ae_phase") or "")
            if state == "control_error":
                self._ready, self._reason = False, "control_error"
                self._stable_frames = 0
                return
            pending = (
                state in {"starting", "settling", "no_signal"}
                or info.get("ae_exposure_mode_status") == "awaiting_metadata"
            )
            searching = state == "adjusting" and phase in {
                "searching_dark",
                "recovering_highlights",
            }
            stable = (
                product is None
                or self._product is None
                or abs(math.log2(product / self._product)) <= 0.15
            )
            self._stable_frames = (
                self._stable_frames + 1
                if stable and not pending and not searching
                else 0
            )
            self._product = product
            manual = info.get("auto_exposure") is False
            explicit = state in {
                "converged",
                "limited_dark",
                "limited_bright",
                "manual",
            }
            self._ready = not pending and (
                manual
                or (explicit and self._stable_frames >= 1)
                or self._stable_frames >= 3
            )
            self._reason = (
                state
                if self._ready and explicit
                else (
                    "manual"
                    if self._ready and manual
                    else (
                        "stable_frames"
                        if self._ready and product is not None
                        else (
                            "metadata_unavailable"
                            if self._ready
                            else (
                                "exposure_settling" if pending else "exposure_adjusting"
                            )
                        )
                    )
                )
            )

    def snapshot(self) -> dict[str, Any]:
        """Report evidence without promising star visibility / 报告证据，不承诺能看到星点。"""
        with self._lock:
            return {
                "ready": self._ready,
                "reason": self._reason,
                "stable_frames": self._stable_frames,
                "frame_sequence": self._last_frame,
                "last_frame_age_s": (
                    round(time.monotonic() - self._last_seen, 3)
                    if self._last_seen
                    else None
                ),
            }


async def wait_capture_ready(
    manager: Any,
    *,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    should_continue: Callable[[], bool] = lambda: True,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Common Core/lab preparation, outside solver deadlines / Core 与分析台共用准备，独立于解算时限。"""
    tracker = getattr(manager, "analysis_readiness", None)
    if tracker is None:
        return {"ready": True, "reason": "legacy_camera_manager"}
    started, previous = monotonic(), -1
    while should_continue():
        readiness = {
            **tracker.snapshot(),
            "elapsed_ms": int((monotonic() - started) * 1000),
            "timeout_seconds": 30,
        }
        if on_progress:
            on_progress(readiness)
        if readiness.get("ready"):
            return readiness
        if readiness.get("reason") == "control_error":
            raise RuntimeError(
                "CAMERA_NOT_READY: exposure control failed / 曝光控制失败"
            )
        if monotonic() - started >= 30:
            raise RuntimeError(
                "CAMERA_NOT_READY: exposure did not settle / 相机曝光未在准备时限内就绪"
            )
        try:
            frame, sequence, _ = await asyncio.wait_for(
                manager.get_raw_frame(), timeout=max(0.01, 30 - (monotonic() - started))
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                "CAMERA_NOT_READY: capture preparation timed out / 相机抓帧准备超时"
            ) from exc
        if frame is None or sequence == previous:
            await asyncio.sleep(0.05)
        previous = sequence
    raise asyncio.CancelledError
