# V4L2 夜空自动曝光 / V4L2 Night-Sky Auto Exposure

## 产品边界 / Product boundary

- 默认相机后端保持 `imx327_mipi`，使用 Picamera2/libcamera 的 ISP 与 AEC/AGC。
- `v4l2` 是显式选择的 RAW 后端，不得在缺少曝光和模拟增益控件时启动。
- `auto_exposure=true` 在 V4L2 下表示 OGScope 软件闭环，不代表内核或 OpenCV 提供 AE。

- The default backend remains `imx327_mipi`, using Picamera2/libcamera ISP and AEC/AGC.
- `v4l2` is an explicit RAW backend and must fail initialization without exposure and analogue-gain controls.
- With V4L2, `auto_exposure=true` means the OGScope software loop, not kernel or OpenCV AE.

显式启用：

```bash
OGSCOPE_CAMERA_TYPE=v4l2
```

## 算法 / Algorithm

每帧从 RAW Bayer 平面抽样，计算三个信号：

1. `background`：中位数，约束天空背景不要被拉成灰白。
2. `highlight`：默认 99.8 分位，代表稀疏星点而不是单个热像素。
3. `saturation_fraction`：保护亮星和地面灯光，超过阈值立即降曝光。

The loop samples the RAW Bayer plane and tracks background median, a configurable
upper percentile for sparse stars, and saturated-pixel fraction.

统计和去马赛克都会先使用同一组 `black_level` / `white_level` 去除 RAW
pedestal 并归一化。默认优先读取 V4L2 控件，控件缺失时黑电平回退为 0、
白电平按位深推导；板端可显式设置
`OGSCOPE_CAMERA_V4L2_BLACK_LEVEL` 与 `OGSCOPE_CAMERA_V4L2_WHITE_LEVEL`。
状态中的 `signal_levels.sources` 会标明每个值来自控件、配置还是回退值。

Both metering and debayer preview use the same black/white-level normalization.
Telemetry exposes each value and its source so a fallback is never mistaken for a
sensor-calibrated value.

控制误差使用摄影 EV（log2）表示，并执行：

- 增亮：先延长曝光，达到时长上限后再增加模拟增益。
- 变暗：先降低模拟增益，再缩短曝光。
- 每次最多移动 1 EV，带亮度滤波、滞回和控制生效等待帧。
- AE 状态为 `starting`、`adjusting`、`settling`、`converged`、
  `limited_dark`、`limited_bright`、`control_error` 或 `manual`。

The controller works in photographic stops. It lengthens exposure before adding
analogue gain for SNR, removes gain before shortening exposure for dynamic range,
limits each update to one stop, and exposes an explicit convergence state.

## 硬件换算 / Hardware conversion

- 首选通过 `pixel_rate` 与 `horizontal_blanking` 推导行周期。
- 仅当驱动不暴露这些只读控件时，才使用 `OGSCOPE_CAMERA_V4L2_LINE_DURATION_US`；
  未配置时的 8µs 只是 IMX327 回退值，状态会标记 `line_duration_source=fallback`。
- 长曝光先提高 `vertical_blanking`，再写 `exposure`。曝光最大值会随 vblank
  动态变化，因此不能缓存启动时的 `exposure.max`。
- 模拟增益按 dB 步进换算，默认 `0.3 dB/step`，板端必须用实际传感器验证。
- 每次写入曝光和模拟增益后批量回读控件。只有回读成功时才填写
  `actual_exposure_us` / `actual_analogue_gain`；否则这两个字段为 `null`，
  推算值仍在 `exposure_us` / `analogue_gain`，错误见 `control_readback`。

- Line time is derived from `pixel_rate` and `horizontal_blanking` when available.
- Long exposure raises `vertical_blanking` before writing `exposure`; the stale
  pre-vblank exposure maximum must not clamp the request.
- Analogue gain is converted in dB steps and requires board calibration.
- Requested values, estimated applied values, and verified control readback are
  reported separately. Failed readback never masquerades as actual telemetry.

## 遥测与交互 / Telemetry and UX

相机状态提供：

- `capabilities.auto_exposure` 与 `software_auto_exposure`
- `auto_exposure_engine=software_night_sky`
- `actual_exposure_us`、`actual_analogue_gain`
- `ae_state`、`ae_error_stops`
- `luminance_stats.background/highlight/saturation_fraction`
- `line_duration_us` 与 `line_duration_source`
- 从真实 V4L2 控件换算的 `control_ranges`
- `signal_levels`、`control_readback` 与 `ae_trace` 诊断状态

前端只能依据这些字段锁定或开放手动参数；缺失 `auto_exposure` 时不得默认显示自动模式。

The UI must use these fields as the source of truth. Missing AE telemetry must
never be interpreted as enabled auto exposure.

## 诊断轨迹与离线回放 / Diagnostic trace and offline replay

诊断默认关闭。夜测时可显式启用：

```bash
OGSCOPE_CAMERA_V4L2_AE_TRACE_ENABLED=true
```

每次相机会话写入：

- `manifest.json`：驱动、RAW 格式、信号电平及来源、AE 边界和 V4L2 控件范围。
- `events.jsonl`：逐帧亮度统计、观测曝光/增益、控制决定、写入值与硬件回读结果。
- `raw/*.npz`：按间隔保存的降采样原始 Bayer 样本，用于重新计算亮度统计。

默认每次最多记录 2000 个事件、100 个 RAW 样本，RAW 最长边 320；到达上限后
停止写入并在 `ae_trace.limit_reached` 中报告。目录默认位于
`data/camera-ae-traces` 且被 Git 忽略，也可通过配置覆盖。

回放命令：

```bash
poetry run python scripts/replay_v4l2_ae.py data/camera-ae-traces/<session> --verify-raw
poetry run python scripts/replay_v4l2_ae.py data/camera-ae-traces/<session> \
  --target-background 0.03 --target-highlight 0.50
```

回放会在相同观测序列上比较控制器决策，并可从 RAW 样本重新验证黑电平校正后的
统计；它不会模拟“换一组曝光参数后传感器本应产生什么图像”，因此不能替代硬件
闭环实测。

Tracing is opt-in and bounded. A session contains a manifest, JSONL control
events, and sparse downsampled RAW samples. Replay validates decisions and
metering against recorded observations; it does not simulate sensor response at
counterfactual exposure settings.

## 板端验收 / Board acceptance

代码测试不能替代 IMX327 夜间实测。启用 V4L2 前至少完成：

1. `v4l2-ctl --list-ctrls` 确认 exposure、analogue_gain、vertical_blanking、
   pixel_rate、horizontal_blanking、可选 black_level/white_level 的真实名称和范围。
2. 用遮光帧确认 RAW pedestal；如果驱动没有黑电平控件，显式配置测得值，并确认
   `signal_levels.sources.black_level=config`。
3. 遮光暗场从 10ms/1× 开始，确认约 15 秒内进入 `converged` 或明确的
   `limited_dark`，而不是停留在固定 10ms。
4. 确认 `control_readback.verified=true`，写入值、回读值与帧周期一致。
5. 对准真实星空，记录 RAW 背景、高分位、饱和比例、实际曝光/增益和解算成功率。
6. 用路灯或月亮进入画面，确认饱和时先降增益且不会持续振荡。
7. 对比 Picamera2/libcamera 基线：星数、FWHM、解算率、收敛时间、预览延迟和 CPU。
8. 至少覆盖无月暗夜、城市光害、薄云、月光和镜头盖五种场景，再冻结目标值。

Code tests do not replace IMX327 night validation. Record convergence, stars,
FWHM, solve rate, preview latency, and CPU against the Picamera2/libcamera baseline
before promoting V4L2 to a product profile.
