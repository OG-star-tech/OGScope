#!/usr/bin/env python3
"""回放 V4L2 AE 诊断轨迹 / Replay a V4L2 AE diagnostic trace."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# 允许直接从任意当前目录运行仓库脚本 / Allow direct checkout execution from any cwd.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from ogscope.domain.camera.ae_diagnostics import (
        load_trace_events,
        replay_trace_events,
        verify_raw_samples,
    )
    from ogscope.domain.camera.auto_exposure import AutoExposureLimits

    parser = argparse.ArgumentParser(
        description="Replay OGScope V4L2 night-sky AE observations"
    )
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--target-background", type=float)
    parser.add_argument("--target-highlight", type=float)
    parser.add_argument("--verify-raw", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(
        (args.session_dir / "manifest.json").read_text(encoding="utf-8")
    )
    metadata = manifest["metadata"]
    configured = metadata["auto_exposure_limits"]
    limits = AutoExposureLimits(
        **{
            **configured,
            **(
                {"target_background": args.target_background}
                if args.target_background is not None
                else {}
            ),
            **(
                {"target_highlight": args.target_highlight}
                if args.target_highlight is not None
                else {}
            ),
        }
    )
    events = load_trace_events(args.session_dir)
    decisions = replay_trace_events(events, limits)
    summary: dict[str, object] = {
        "session_dir": str(args.session_dir),
        "event_count": len(events),
        "limits": asdict(limits),
        "final_decision": asdict(decisions[-1]) if decisions else None,
        "state_counts": {},
        "note": (
            "Recorded observations validate controller decisions; they do not fully "
            "simulate sensor response under different exposure settings."
        ),
    }
    state_counts: dict[str, int] = {}
    for decision in decisions:
        state_counts[decision.state] = state_counts.get(decision.state, 0) + 1
    summary["state_counts"] = state_counts
    if args.verify_raw:
        levels = metadata["signal_levels"]
        summary["raw_verification"] = verify_raw_samples(
            args.session_dir,
            bit_depth=int(metadata["bit_depth"]),
            black_level=int(levels["black_level"]),
            white_level=int(levels["white_level"]),
            highlight_percentile=float(limits.highlight_percentile),
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
