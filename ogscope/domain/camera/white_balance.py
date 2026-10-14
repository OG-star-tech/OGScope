"""线性 Bayer 白平衡；暗场保持颜色稳定 / Linear Bayer WB with dark-scene hold."""

from __future__ import annotations

import numpy as np

BAYER_CHANNELS = {
    "RGGB": ((0, 1), (1, 2)),
    "BGGR": ((2, 1), (1, 0)),
    "GRBG": ((1, 0), (2, 1)),
    "GBRG": ((1, 2), (0, 1)),
}
COLOR_PIPELINE_VERSION = "linear-raw-awb-v1"


class RawAutoWhiteBalance:
    """对低成本 Bayer 网格做稳健灰世界估计 / Robust gray-world on a small Bayer grid."""

    def __init__(self) -> None:
        self.gains = (1.1, 1.0, 0.9)
        self.state = "waiting_for_signal"
        self.samples = 0

    def observe(
        self,
        raw: np.ndarray,
        *,
        pattern: str,
        black: float,
        white: float,
        exposure_product: float,
        ready: bool,
    ) -> None:
        """仅用有效明亮帧更新；黑场、饱和帧和旧帧保持原值 / Update only on valid lit frames."""
        if not ready:
            self.state = "waiting_for_exposure"
            return
        height, width = raw.shape[:2]
        height -= height % 2
        width -= width % 2
        if height < 2 or width < 2:
            self.state = "insufficient_samples"
            return
        span = max(1.0, white - black)
        channels: list[list[np.ndarray]] = [[], [], []]
        for y in range(2):
            for x in range(2):
                values = (
                    raw[y:height:16, x:width:16].astype(np.float32) - black
                ) / span
                channels[BAYER_CHANNELS[pattern][y][x]].append(values)
        r = channels[0][0].reshape(-1)
        g = ((channels[1][0] + channels[1][1]) * 0.5).reshape(-1)
        b = channels[2][0].reshape(-1)
        signal = float(np.median(g))
        # 不靠暗空、星点或黑电平噪声估计照明颜色。
        # Do not estimate illuminant color from dark sky, stars or black-level noise.
        if signal < 0.015 or signal / max(1.0, exposure_product) < 2e-7:
            self.state = "held_low_light"
            return
        valid = (np.minimum(np.minimum(r, g), b) > 0.005) & (
            np.maximum(np.maximum(r, g), b) < 0.90
        )
        self.samples = int(np.count_nonzero(valid))
        if self.samples < 32:
            self.state = "insufficient_samples"
            return
        # 使用较亮样本的中位比值，减少暗部噪声和小块彩色物体的影响。
        # Median ratios of brighter samples reduce shadow noise and small colored outliers.
        threshold = np.percentile(g[valid], 50)
        valid &= g >= threshold
        target_r = float(np.clip(np.median(g[valid] / r[valid]), 0.5, 3.0))
        target_b = float(np.clip(np.median(g[valid] / b[valid]), 0.5, 3.0))
        old_r, _, old_b = self.gains
        next_r = old_r + 0.4 * (target_r - old_r)
        next_b = old_b + 0.4 * (target_b - old_b)
        self.gains = (round(next_r, 3), 1.0, round(next_b, 3))
        self.state = (
            "converged"
            if max(abs(target_r - next_r), abs(target_b - next_b)) < 0.03
            else "adjusting"
        )
