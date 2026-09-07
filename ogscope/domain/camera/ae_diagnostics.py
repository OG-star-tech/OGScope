"""自动曝光诊断记录与回放 / Auto-exposure diagnostic recording and replay."""

from __future__ import annotations

import json
import logging
import math
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from ogscope.domain.camera.auto_exposure import (
    AutoExposureDecision,
    AutoExposureLimits,
    LuminanceStats,
    NightSkyAutoExposure,
    measure_luminance,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class AutoExposureTraceLimits:
    """有界诊断写盘配置 / Bounded diagnostic persistence settings."""

    max_events: int = 2_000
    raw_sample_interval: int = 10
    max_raw_samples: int = 100
    raw_max_side: int = 320


class AutoExposureTraceRecorder:
    """写入有上限的 JSONL 轨迹和降采样 RAW / Write bounded JSONL traces and sampled RAW."""

    def __init__(
        self,
        *,
        enabled: bool,
        root_dir: str | Path,
        limits: AutoExposureTraceLimits | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.root_dir = Path(root_dir)
        self.limits = limits or AutoExposureTraceLimits()
        self.session_dir: Path | None = None
        self.event_count = 0
        self.raw_sample_count = 0
        self.limit_reached = False
        self.error: str | None = None
        self._trace_file: Any | None = None
        self._lock = threading.Lock()

    def start(self, metadata: dict[str, Any]) -> None:
        """创建一次诊断会话 / Create one diagnostic session."""
        if not self.enabled or self.session_dir is not None or self.error:
            return
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            self.session_dir = self.root_dir / f"{timestamp}-{uuid4().hex[:8]}"
            (self.session_dir / "raw").mkdir(parents=True, exist_ok=False)
            manifest = {
                "schema_version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "trace_limits": asdict(self.limits),
                "metadata": metadata,
            }
            (self.session_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._trace_file = (self.session_dir / "events.jsonl").open(
                "a", encoding="utf-8"
            )
        except (OSError, TypeError, ValueError) as exc:
            self.error = str(exc)
            logger.warning("创建 AE 诊断会话失败 / Failed to create AE trace: %s", exc)
            self.close()

    def record(self, event: dict[str, Any], raw: np.ndarray | None = None) -> None:
        """记录一帧，达到上限后停止写入 / Record one frame and stop at configured bounds."""
        if not self.enabled or self._trace_file is None or self.error:
            return
        with self._lock:
            if self.event_count >= max(1, int(self.limits.max_events)):
                self.limit_reached = True
                return
            sequence = self.event_count + 1
            payload = {
                "schema_version": 1,
                "sequence": sequence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **event,
            }
            try:
                raw_name = self._save_raw_sample(sequence, raw)
                if raw_name is not None:
                    payload["raw_sample"] = raw_name
                self._trace_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
                self._trace_file.flush()
                self.event_count = sequence
            except (OSError, TypeError, ValueError) as exc:
                self.error = str(exc)
                logger.warning("写入 AE 诊断失败 / Failed to write AE trace: %s", exc)
                self.close()

    def _save_raw_sample(self, sequence: int, raw: np.ndarray | None) -> str | None:
        if raw is None or self.session_dir is None:
            return None
        interval = max(1, int(self.limits.raw_sample_interval))
        if (sequence - 1) % interval != 0:
            return None
        if self.raw_sample_count >= max(0, int(self.limits.max_raw_samples)):
            return None
        source = np.asarray(raw)
        max_side = max(16, int(self.limits.raw_max_side))
        stride = max(1, int(math.ceil(max(source.shape[:2]) / max_side)))
        sampled = np.ascontiguousarray(source[::stride, ::stride])
        filename = f"raw/frame-{sequence:06d}.npz"
        # 诊断模式优先降低 Pi 上的压缩 CPU 干扰，容量由样本数量和尺寸双重限制。
        # Diagnostic mode avoids compression CPU jitter on Pi; count and size bounds cap storage.
        np.savez(
            self.session_dir / filename,
            raw=sampled,
            stride=np.asarray(stride, dtype=np.int32),
            original_shape=np.asarray(source.shape, dtype=np.int32),
        )
        self.raw_sample_count += 1
        return filename

    def status(self) -> dict[str, Any]:
        """返回不伪装成功的诊断状态 / Return truthful diagnostic status."""
        return {
            "enabled": self.enabled,
            "session_dir": str(self.session_dir) if self.session_dir else None,
            "event_count": self.event_count,
            "raw_sample_count": self.raw_sample_count,
            "max_events": int(self.limits.max_events),
            "max_raw_samples": int(self.limits.max_raw_samples),
            "limit_reached": self.limit_reached,
            "error": self.error,
        }

    def close(self) -> None:
        """关闭轨迹文件 / Close the trace file."""
        trace_file = self._trace_file
        self._trace_file = None
        if trace_file is not None:
            try:
                trace_file.close()
            except OSError:
                pass


def load_trace_events(session_dir: str | Path) -> list[dict[str, Any]]:
    """加载 JSONL 诊断事件 / Load JSONL diagnostic events."""
    path = Path(session_dir) / "events.jsonl"
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as trace_file:
        for line in trace_file:
            if line.strip():
                events.append(json.loads(line))
    return events


def replay_trace_events(
    events: Iterable[dict[str, Any]], limits: AutoExposureLimits
) -> list[AutoExposureDecision]:
    """用记录观测重放控制器，不模拟传感器响应 / Replay decisions without simulating sensor response."""
    controller = NightSkyAutoExposure(limits)
    decisions: list[AutoExposureDecision] = []
    for event in events:
        stats = LuminanceStats(**event["stats"])
        observed = event["observed"]
        decisions.append(
            controller.observe(
                stats,
                exposure_us=int(observed["exposure_us"]),
                analogue_gain=float(observed["analogue_gain"]),
            )
        )
    return decisions


def verify_raw_samples(
    session_dir: str | Path,
    *,
    bit_depth: int,
    black_level: int,
    white_level: int,
    highlight_percentile: float,
) -> list[dict[str, Any]]:
    """重新计算采样 RAW 统计用于校验 / Recompute sampled-RAW statistics for verification."""
    root = Path(session_dir)
    results: list[dict[str, Any]] = []
    resolved_root = root.resolve()
    for event in load_trace_events(root):
        raw_name = event.get("raw_sample")
        if not raw_name:
            continue
        raw_path = (root / str(raw_name)).resolve()
        if not raw_path.is_relative_to(resolved_root):
            raise ValueError("RAW sample path escapes session directory")
        with np.load(raw_path, allow_pickle=False) as sample:
            stats = measure_luminance(
                sample["raw"],
                bit_depth=bit_depth,
                black_level=black_level,
                white_level=white_level,
                highlight_percentile=highlight_percentile,
            )
        results.append({"sequence": event["sequence"], "stats": asdict(stats)})
    return results
