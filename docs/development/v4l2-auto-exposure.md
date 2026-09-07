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

典型配置如下；设备节点、实体名和格式不是跨系统常量，必须用目标系统的
`media-ctl -p`、`v4l2-ctl --list-devices` 与 `v4l2-ctl --list-formats-ext`
结果替换：

```bash
OGSCOPE_CAMERA_DEVICE=/dev/video0
OGSCOPE_CAMERA_V4L2_SENSOR_SUBDEV=/dev/v4l-subdev1
OGSCOPE_CAMERA_V4L2_MEDIA_DEVICE=/dev/media0
OGSCOPE_CAMERA_V4L2_CONFIGURE_MEDIA_PIPELINE=true
OGSCOPE_CAMERA_V4L2_SENSOR_ENTITY="imx327 10-001a"
OGSCOPE_CAMERA_V4L2_RECEIVER_ENTITY=unicam
OGSCOPE_CAMERA_V4L2_SENSOR_PAD=0
OGSCOPE_CAMERA_V4L2_RECEIVER_SINK_PAD=0
OGSCOPE_CAMERA_V4L2_RECEIVER_SOURCE_PAD=1
OGSCOPE_CAMERA_V4L2_MEDIA_BUS_FORMAT=SRGGB10_1X10
OGSCOPE_CAMERA_V4L2_PIXEL_FORMAT=RG10
OGSCOPE_CAMERA_V4L2_BIT_DEPTH=10
OGSCOPE_CAMERA_V4L2_BAYER_PATTERN=RGGB
OGSCOPE_CAMERA_V4L2_ACTIVE_WIDTH=1920
OGSCOPE_CAMERA_V4L2_ACTIVE_HEIGHT=1080
```

若 `media-ctl -p` 显示 CSI 接收端只是视频节点、没有可配置的 subdev source pad，
可将相应 pad 设为 `-1` 跳过。已在 Raspberry Pi Unicam 的 sink-only 拓扑验证过的
覆盖配置为：

```bash
OGSCOPE_CAMERA_V4L2_SENSOR_SUBDEV=/dev/v4l-subdev0
OGSCOPE_CAMERA_V4L2_MEDIA_DEVICE=/dev/media2
OGSCOPE_CAMERA_V4L2_RECEIVER_ENTITY=unicam-image
OGSCOPE_CAMERA_V4L2_RECEIVER_SINK_PAD=-1
OGSCOPE_CAMERA_V4L2_RECEIVER_SOURCE_PAD=-1
```

When the CSI receiver is represented only by a video node and has no configurable
subdevice pads, set the absent receiver pads to `-1`. OGScope will configure the
sensor pad and let the video-node `S_FMT` call select the capture format.

The device nodes, media entities, bus code, FourCC, bit depth, and Bayer order are
board-discovered values rather than portable defaults. Initialization fails when
the requested media graph, RAW format/size, or required exposure controls cannot
be verified.

## 与当前分析链路的兼容性 / Compatibility with the current analysis pipeline

V4L2 后端在边界处输出与 Picamera2 路径相同的连续 `RGB888` ndarray；共享帧总线、
JPEG 预览、精确 `session_id + frame_id` 解算帧、常规星图解算，以及最近加入的
明暗混合结构干扰判定都继续复用同一套代码。驱动切换不改变 `/api/core/v1/*`
业务路径，也不要求 ZenitAPA 识别驱动名。

兼容成立依赖以下条件：

- RAW 必须按真实黑/白电平归一化，并按正确 Bayer 排列转成 RGB。
- `native` / `crop` 从 1920×1080 中心裁出 1280×720，继续报告产品标定的
  `13.01° × 7.34°`；`supersample` 缩放全幅并报告约 `19.41° × 11.00°`。
- 上层始终读取 `info.optics.effective_fov_deg`，不能把名义全幅视场硬编码给所有模式。
- 控件回读失败时 actual 字段保持 `null`。这会使依赖实际曝光的环境亮度提示安全降级，
  但不会用请求值伪造硬件状态。

The adapter preserves the RGB/frame/solve contracts used by exact-frame analysis
and structural-obstruction fallback. Compatibility still depends on verified RAW
normalization, Bayer order, output geometry, effective FOV, and truthful control
readback.

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
- 产品自动曝光上限仍为 1 秒；即使旧配置或硬件范围更大，也不会放宽当前分析和
  交互的时间预算。手动范围仍按硬件控件报告。
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

1. 确认内核已创建设备节点，服务用户对 `/dev/media*`、`/dev/video*`、
   `/dev/v4l-subdev*` 有读写权限，并安装提供 `media-ctl` / `v4l2-ctl` 的工具包。
2. `media-ctl -p` 核对传感器、CSI 接收器、pad 与 link；
   `v4l2-ctl --list-formats-ext` 核对 RAW FourCC、尺寸与存储布局。
3. `v4l2-ctl --list-ctrls` 确认 exposure、analogue_gain、vertical_blanking、
   pixel_rate、horizontal_blanking、可选 black_level/white_level 的真实名称和范围。
4. 用遮光帧确认 RAW pedestal；如果驱动没有黑电平控件，显式配置测得值，并确认
   `signal_levels.sources.black_level=config`。
5. 遮光暗场从 10ms/1× 开始，确认约 15 秒内进入 `converged` 或明确的
   `limited_dark`，而不是停留在固定 10ms。
6. 确认 `capture_format.actual_fourcc/width/height` 与配置一致，并确认
   `control_readback.verified=true`、写入值、回读值与帧周期一致。
7. 连续执行多轮 Core camera start/stop，确认阻塞读取可在超时预算内释放、设备节点可重开。
8. 对准真实星空，记录 RAW 背景、高分位、饱和比例、实际曝光/增益和解算成功率。
9. 用路灯或月亮进入画面，确认饱和时先降增益且不会持续振荡。
10. 对比 Picamera2/libcamera 基线：星数、FWHM、解算率、收敛时间、预览延迟和 CPU。
11. 至少覆盖无月暗夜、城市光害、薄云、月光和镜头盖五种场景，再冻结目标值。

本次改造只修改 OGScope 应用与 ZenitAPA 集成文档，不修改 `og-bsp`。因此内核驱动、
设备树、udev/group、媒体实体命名、`v4l-utils` 打包、OpenCV V4L2 支持，以及数据目录
持久化/权限都属于新系统镜像必须另行满足和实机确认的前置条件。当前本地单元测试
不构成开发板、夜空或自动机械对准验收。

Code tests do not replace IMX327 night validation. Record convergence, stars,
FWHM, solve rate, preview latency, and CPU against the Picamera2/libcamera baseline
before promoting V4L2 to a product profile. This change does not modify the BSP;
the target OS must independently provide the kernel/media graph, permissions,
`v4l-utils`, OpenCV V4L2 support, and writable persistent data paths.

### 2026-09-07 Raspberry Pi 实机探针 / Board probe

在 Raspberry Pi CM0、Debian 13、Linux 6.18.34 上完成了不改永久配置的临时验证：

- `/dev/media2` 为 Unicam，`/dev/video0` 为 RAW capture，传感器控件位于
  `/dev/v4l-subdev0`；`unicam-image` 只有 sink pad，因此接收器两个 pad 均配置为 `-1`。
- `RG10`、1920×1080 协商成功；OpenCV 返回一维 byte buffer，适配器正确重排为
  1920×1080 `uint16`，实测 RAW 为右对齐 10-bit。
- 从 `pixel_rate=148500000`、`horizontal_blanking=2020` 推导出的行周期为
  `26.532µs`；曝光与模拟增益写入后回读通过。
- 12 帧软件 AE 从约 10ms 降到产品最短约 1ms，并在现场强明场进入
  `limited_bright`；Picamera2 以相同约 1ms 曝光也接近全白。约 27µs 手动曝光无饱和，
  说明该结果是夜空 AE 最短曝光边界，不是 RAW packing 故障。
- Core v1 状态、100µs 手动调参、1280×720 MJPEG、两轮 stop/start，以及实时分析
  start/result/stop 均通过。无星明场返回 `TOO_FEW`，属于预期业务结果。
- 测试结束后原 Picamera2 服务恢复为 healthy、connected、streaming；未执行电机运动。

This probe validates the application/driver boundary on one board only. It does
not close the required dark-frame, night-sky, solve-rate, long-run, or motor-system
acceptance gates.
