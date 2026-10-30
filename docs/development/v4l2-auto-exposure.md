# V4L2 自动曝光与颜色 / V4L2 Auto Exposure and Color

## 产品边界 / Product boundary

- 新安装默认 `v4l2` + CPU；已有 Picamera2 部署显式保留 `imx327_mipi`，使用 libcamera 的 ISP 与 AEC/AGC。参见[三种部署方案](camera-deployment-profiles.md)。
- `v4l2` 不得在缺少曝光和模拟增益控件时启动；ISP 是独立选择的处理方式。
- `auto_exposure=true` 在 V4L2 下表示 OGScope 软件闭环，不代表内核或 OpenCV 提供 AE。

- New installations default to `v4l2` + CPU. Existing Picamera2 installations explicitly retain `imx327_mipi` and libcamera ISP/AEC/AGC. See [deployment profiles](camera-deployment-profiles.md).
- V4L2 must fail initialization without exposure and analogue-gain controls; ISP processing is selected independently.
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
业务路径，也不要求上层调用方识别驱动名。

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

Picamera2 主流配置使用 libcamera 的 `BGR888` 格式，它在 ndarray 中对应 RGB
字节排列。相机帧进入解算器时转换一次 RGB→BGR；上传图片和视频的 OpenCV
解码结果原本就是 BGR，不重复转换。产品 `imx327.json` 的 Long 曝光曲线从
10µs 开始，由传感器实际范围限制，避免长曝光模式把白天快门限制在 1ms。

The Picamera2 main stream uses libcamera `BGR888`, which supplies RGB array bytes.
Camera frames are converted once to BGR at the solver boundary; OpenCV-decoded
uploads and videos already use BGR. The product `imx327.json` Long exposure curve
starts at 10µs and is clamped to the sensor range, allowing sub-millisecond daytime
exposure without changing the remaining night-exposure curve.

## 算法 / Algorithm

每帧从 RAW Bayer 平面抽样，计算三个信号：

1. `background`：中位数，约束天空背景不要被拉成灰白。
2. `highlight`：默认 99.8 分位，代表稀疏星点而不是单个热像素。
3. `saturation_fraction`：保护亮星和地面灯光，超过阈值立即降曝光。

The loop samples the RAW Bayer plane and tracks background median, a configurable
upper percentile for sparse stars, and saturated-pixel fraction.

抽样步长保持奇数，均衡覆盖 Bayer 四种相位，避免只测到一种颜色；这仍是
RAW 信号统计，不等同于经过 ISP 处理的亮度值。
The sampling stride is odd to cover all four Bayer phases rather than one colour.
These remain RAW signal statistics, not ISP-processed luminance values.

统计和去马赛克都会先使用同一组 `black_level` / `white_level` 去除 RAW
pedestal 并归一化。默认优先读取 V4L2 控件，控件缺失时使用已测暗场的黑电平比例
（12 位时约 240），白电平按位深推导；这不是每台设备的独立标定，板端可显式设置
`OGSCOPE_CAMERA_V4L2_BLACK_LEVEL` 与 `OGSCOPE_CAMERA_V4L2_WHITE_LEVEL`。
状态中的 `signal_levels.sources` 会标明每个值来自控件、配置还是回退值。

Both metering and debayer preview use the same black/white-level normalization.
When controls are absent, black level uses the measured dark-frame fallback ratio
(about 240 at 12 bits), not zero; white level follows bit depth. This is not per-device
calibration. Telemetry exposes each value and source so the fallback remains identifiable.

控制误差使用摄影 EV（log2）。`adaptive-raw-v2` 把快速搜索与稳定拍摄分开：

- 过暗且偏差大时，最多增加 4 EV，先使用 100ms 探测曝光和临时增益；达到增益限制后才继续拉长探测曝光。
- 大面积过曝时立即撤掉增益、把快门缩至最多 100ms，再重新测光。
- 接近目标后恢复快门优先的低噪声分配，并使用细步进与滞回。最大自动曝光仍是 3s，模拟增益仍受硬件与配置上限约束。
- 按单位曝光信号选择 `daylight` / `starfield`；日间中位数/高光目标为 0.12/0.8，星空沿用配置目标。允许少量高光，避免一盏路灯压黑背景。
- V4L2 控件回读不包含帧元数据。每次写入后丢弃两帧排队数据，并等待旧帧周期加新帧周期；未通过这个保守门限的帧不参与曝光或 AWB。不能简单按预览帧率减少等待。
- `ae_state` 保留兼容值；新增 `ae_phase`、`ae_scene_mode` 和带版本的 `ae_policy`。达到限制不等于成功收敛。

`adaptive-raw-v2` separates acquisition from steady capture. Dark acquisition uses up to
4 EV steps, a 100ms probe and temporary gain before longer exposures. Broad clipping
immediately removes gain and caps the next shutter at 100ms. Near convergence it returns
to shutter-first low-noise allocation, smaller steps and hysteresis, within the existing
3-second/hardware gain limits. Signal per exposure distinguishes daylight from starfield;
small clipped highlights must not black out the background.

Control readback is **not per-frame metadata**. The driver discards two queued frames and
waits the previous plus next frame duration before re-metering. This conservative gate
also protects AWB. Recorded traces include `frame_ready` for faithful replay. Status keeps
existing `ae_state` values and adds policy version, scene mode and acquisition phase.

## 颜色处理 / Color processing

`linear-raw-awb-v1` 的顺序是：黑电平 → 线性 RAW 白平衡 → 16 位去马赛克 → gamma → 8 位 RGB888。
不再对 Bayer 先做 gamma，也不在线性处理后重复施加白平衡。整数 RAW 使用缓存查找表，默认增强直接复用缓冲，避免整幅 float RGB 临时数组。

- `auto` 真正执行软件 AWB；采样四种 Bayer 排列，使用较亮有效样本的中位颜色比值。
- 严重过曝、欠曝、旧帧和低照度时保持现有增益；夜空不会靠稀疏星点或噪声追逐颜色。
- `manual` 使用指定线性 R/B 增益；`night` 使用固定线性 1.1/0.9。两者不运行 AWB。
- `color_pipeline` 报告版本、处理域、有效增益与 AWB 状态。这是通用灰世界估计，不是色卡标定，也不包含已验证的相机颜色矩阵；单一颜色场景可能产生偏差。

The pipeline is black subtraction → linear Bayer WB → 16-bit demosaic → gamma → RGB888.
Integer RAW uses cached lookup tables and avoids full-frame float RGB temporaries. Auto
WB uses robust ratios from a small Bayer grid; clipped, dark and stale frames hold gains.
Manual/night remain explicit fixed modes. This is gray-world AWB, **not** a calibrated
color matrix; single-color scenes remain a limitation. `color_pipeline` reports effective
mode/gains and algorithm version. Old gamma-domain manual gains may need re-tuning.

完整 16 位 gamma 查表最多由四个工作线程分担，每帧独立输出，所有分块完成后才返回。
不分块去马赛克、不降低位深、不积压帧；小图和单核采用普通查表，相机关闭时释放线程。
90°/180°/270° 使用 OpenCV 旋转，与原 NumPy 旋转和翻转逐像素一致。

The full 16-bit gamma lookup uses at most four workers and independently owned frame
outputs, joining all slices before returning. Demosaicing stays whole-frame; precision is
unchanged and no frame queue is added. Small images/single-core machines use ordinary
lookup; camera close releases workers. OpenCV rotation preserves original pixel geometry.

## 打包、升级和回退 / Packaging, upgrade and rollback

1. 完整交付 `ogscope` Python 包，尤其是 `domain/camera/auto_exposure.py`、新增 `domain/camera/white_balance.py`、`domain/camera/ae_diagnostics.py` 与 `platform/hardware/v4l2_camera.py`。新策略与颜色默认值内置，不依赖新外部 JSON。
2. 保留板端拓扑、黑白电平、FOV、旋转、曝光上限和用户配置。先检查 systemd 的 EnvironmentFile 顺序、实际进程 PYTHONPATH、`/data` 覆盖；安装目录版本不一定等于运行版本。
3. 使用 `OGSCOPE_CAMERA_WHITE_BALANCE_MODE=auto` 选择 AWB；显式 `manual`/`night` 保持原意。`OGSCOPE_CAMERA_V4L2_AE_MAX_STEP_STOPS` 现在约束微调；搜索上限由内置策略决定。不要把 Picamera2 `imx327.json` 当作 V4L2 的配置来源。
4. 只读系统把开发覆盖放在可写数据分区，先克隆当前完整运行包再覆盖经过核对的变更文件，保留旧包和环境文件。不要重挂载系统分区或覆盖整个 data 目录。正式镜像必须包含完整新包，并处理可能遮蔽新包的旧热修复选择器。
5. 停止正在执行的分析/录像后，在允许中断预览的维护窗口切换。先确认没有对齐、校准、固件升级和系统更新；不执行电机运动。重启相机服务后检查 Core health、开启预览、持续取帧，再读状态：只有 status 轮询不会推进 AE。
6. 核验 `ae_policy.version=adaptive-raw-v2`、`color_pipeline.version=linear-raw-awb-v1`、`white_balance_mode` 与配置一致、`control_readback.verified=true`，以及 3s 上限、FOV/旋转和时域降噪关闭状态。核对 RSS、实际 FPS、日志和双向曝光；不能只检查配置中的 fps。
7. 随运行时交付项目已声明的 `PyTurboJPEG`（当前 lock 为 1.8.3，约束 `>=1.7,<2`）
   及本机架构的 `libturbojpeg`。只有 `libturbojpeg.so` 而缺少 Python 模块时仍会走
   OpenCV 后备编码；在**服务实际 Python/PYTHONPATH** 中验证 `TurboJPEG()` 可加载。
   预览取帧后读取 `preview_encoder`，auto 会按首帧测速选择后端；可回退不等于依赖已交付。
8. 回退时恢复备份环境选择器并重启相机服务，检查旧策略、健康与预览恢复。保留原始日志与照片；如果环境文件已被别人改动，停止自动覆盖并人工核对。

Ship the complete Python package including the new `white_balance.py`; policy/color
defaults are built in and need no new external JSON. Preserve board topology, calibration,
FOV, rotation, exposure limits and user settings. Inspect actual process paths and env-file
precedence, including persistent hotfix overrides. Picamera2 tuning JSON is not consumed
by V4L2. On read-only images stage an isolated copy on writable data, retain prior package
and env selectors, and switch only during an idle maintenance window. Production images
must include the new package and retire or repoint stale selectors deliberately.

After restart, consume preview frames and verify both policy versions, WB mode, verified
control readback, geometry, limits, actual FPS and memory. Test both bright and dark
transitions. Roll back by restoring the exact previous selectors, restart and verify old
policy/preview health; refuse to overwrite env files changed by another actor.

Include the already-declared PyTurboJPEG dependency (lock 1.8.3, constraint >=1.7,<2)
and the target-architecture libturbojpeg. A native library without the Python binding still
falls back to OpenCV. Instantiate `TurboJPEG()` under the service's actual interpreter and
paths, then check `preview_encoder` after frames are consumed; auto benchmarks its first
frame. The supported fallback must not hide a packaging omission. The two JPEG backends
are lossy and need not produce identical bytes; RGB order and frame geometry must agree.

Daytime transitions, synthetic dark-scene convergence and color-reference checks do not
replace real-sky star extraction, solve success and long-exposure tracking acceptance.

## 2026-10-14 日间验收 / Daytime acceptance

IMX327 板端、1280×720 native、180°旋转、关闭时域降噪，持续消费预览测得：

| 条件 / Condition | 观察 / Observation |
|---|---|
| 窗外场景，2s / 15.849× 手动切自动 / Window, 2s and 15.849× → auto | 旧策略约 22.4s，新策略约 8.8s 首次稳定 / Old ~22.4s, new ~8.8s to first convergence |
| 日间约 1 EV 欠曝，89µs / 1× 切自动 / Daylight ~1 EV underexposure, 89µs and 1× → auto | 约 1s 稳定 / ~1s to convergence |
| 用户遮挡后移开 / Physical cover and uncover | 黑暗达到 3s / 15.849× 上限；检测到亮场后约 7.7s 稳定 / Dark reached the 3s / 15.849× limit; ~7.7s from detected bright frame to convergence |
| 自动白平衡 / Auto white balance | 窗外白灰建筑明显偏绿消除；不是色卡验收 / Visible green cast removed from neutral window buildings; not a color-chart validation |

遮挡起点早于连续记录，不能据此给出完整变暗响应时间。上述时间分别基于手动参数
重置和实际遮挡，不能相互替代，也不能推广为所有场景保证。3s 上限处的
`limited_dark` 表示照度不足，不是已成功收敛。

第二次真实遮挡记录补到了短曝光阶段：从首个样本的 3.2ms / 1× 到 3s / 15.849×
约 3.9s；移开后从检测到亮场到稳定约 7.5s，AWB 增益保持稳定。首个样本已经
开始调节，因此 3.9s 是记录覆盖的曝光爬升区间，不是从物理遮挡瞬间计时，也不
代表真实夜空一定能在该时间完成收敛。

A second physical cover test captured the ramp from 3.2ms / 1× to 3s / 15.849× in
~3.9s, followed by ~7.5s from detected bright scene to convergence after uncovering.
WB held steady. The first recorded sample was already adjusting, so the ramp timing
does not start at the physical cover instant and is not a night-sky convergence guarantee.

颜色修复后的初始性能约 3.7–3.8fps；同日、同板、同窗口画面进一步优化后：

| 路径 / Path | 实际 fps / Actual fps | 取帧及颜色 / Read + color | JPEG |
|---|---:|---:|---:|
| 修复颜色后的基线 / Corrected-color baseline | 3.74 | 227ms | 40ms |
| 最终查表与旋转优化、补齐 JPEG 依赖 / Final LUT + rotation, JPEG dependency present | 6.16 | 128ms | 34ms |

首次启用读数来自持续消费预览、启动后 20–90s 的中位数；目标 8fps，仍有处理瓶颈，
不能宣称已达到 8fps。首次启用 RSS 约 200128KiB、进程 swap 22360KiB，总计约 217MiB；
交换页随后保持稳定，约五分钟观察内没有新增换出或 OOM。基线 RSS 约 212522KiB、
swap 0。RSS 下降不能单独证明总内存下降，长时间运行和星库同时解算仍需夜间验收。
本板 RAW 已为 1280×720，未加入全幅裁剪或缩小分辨率。
回退并再激活后的 90s 复测中位约 6.07fps、RSS 215918KiB（约 211MiB）、swap 0；
这次复测未显示持续换出。两次内存状态不同，保留原始记录，不将 RSS 变化视作节省总内存。

额外复测只改变起始曝光参数：100µs / 1× → 自动约 0.8s 收敛；2s / 15.849× → 自动
约 7.1s 收敛。后者含旧长曝光排队帧等待；这些不是真实照度突变的计时，也不替代前述
遮挡测试。可回退覆盖验证未修改的 126 个运行文件，保持上层进程、FOV/180°旋转、
用户配置和轴位置；未执行电机动作。

On the same daytime board/window, the final full-precision lookup/rotation optimization
and restored JPEG binding improved the measured median from 3.74 to 6.16fps, read/color
from 227 to 128ms, and JPEG from 40 to 34ms. These are post-startup 20–90s medians with
an active preview consumer at an 8fps target, not an 8fps acceptance claim. Final RSS was
~200128KiB plus ~22360KiB process swap (~217MiB total); swapped pages then stayed stable,
with no additional swap-out or OOM over about five minutes. Baseline RSS was ~212522KiB
with no swap. Lower RSS alone does not establish lower total memory; long runs together
with solving remain pending. RAW stayed 1280×720, with no resolution reduction.
A separate 90s run after rollback/reactivation measured a 6.07fps median, ~215918KiB
RSS (~211MiB) and zero process swap, without sustained swap-out. Keep both observations;
the changed residency does not establish a reduction in total memory.

Parameter-reset retests converged in ~0.8s from 100µs/1× and ~7.1s from 2s/15.849×,
including old long-exposure queue latency. These are not physical lighting-transition
measurements. The isolated runtime verified 126 untouched files and preserved upper-service
processes, camera geometry/settings and axes. No motor motion was used. Physical cover
results above and earlier alignment tests do not establish new-color real-sky acceptance.

## 硬件换算 / Hardware conversion

- 首选通过 `pixel_rate` 与 `horizontal_blanking` 推导行周期。
- AE 最短曝光与改变判定使用传感器曝光控件及行周期，允许合法的亚毫秒快门；
  最终行数取整、范围限制和 actual 回读由驱动负责。
- 仅当驱动不暴露这些只读控件时，才使用 `OGSCOPE_CAMERA_V4L2_LINE_DURATION_US`；
  未配置时的 8µs 只是 IMX327 回退值，状态会标记 `line_duration_source=fallback`。
- 长曝光先提高 `vertical_blanking`，再写 `exposure`。曝光最大值会随 vblank
  动态变化，因此不能缓存启动时的 `exposure.max`。
- 产品自动曝光上限为 3 秒（2026-09-20 从 1 秒放宽 - 在真实 Zero2W
  (192.168.0.41) 上验证 1s-3s 手动曝光的控件写入/回读与实际抓帧均正常后的
  产品决策，见 docs/development/v4l2-zero2w-board-validation.md）；即使旧
  配置或硬件范围更大，也不会放宽超过这一上限。手动范围仍按硬件控件报告。
- 模拟增益按 dB 步进换算，默认 `0.3 dB/step`，板端必须用实际传感器验证。
- 每次写入曝光和模拟增益后批量回读控件。只有回读成功时才填写
  `actual_exposure_us` / `actual_analogue_gain`；否则这两个字段为 `null`，
  推算值仍在 `exposure_us` / `analogue_gain`，错误见 `control_readback`。

- Line time is derived from `pixel_rate` and `horizontal_blanking` when available.
- AE minimum exposure and change detection use the sensor exposure controls and
  line time, allowing legal sub-millisecond shutters. The driver remains responsible
  for line quantization, range clamping and actual control readback.
- Long exposure raises `vertical_blanking` before writing `exposure`; the stale
  pre-vblank exposure maximum must not clamp the request.
- The product auto-exposure ceiling is 3 seconds (raised from 1s on
  2026-09-20 after validating 1s-3s manual exposure - control write/readback
  and real capture, both clean - on a real Zero2W at 192.168.0.41; see
  docs/development/v4l2-zero2w-board-validation.md). Legacy config or a
  larger hardware range never loosens this. Manual range is still reported
  straight from the hardware controls.
- Analogue gain is converted in dB steps and requires board calibration.
- Requested values, estimated applied values, and verified control readback are
  reported separately. Failed readback never masquerades as actual telemetry.

## 可选时域降噪 / Optional temporal denoising

`OGSCOPE_CAMERA_V4L2_TEMPORAL_NR_ALPHA` 默认 `1.0`，关闭跨帧累积，移动预览
直接使用新帧。静态场景可显式设为小于 `1.0`；启用后时间系数按实际处理帧间隔
计算，不使用传感器名义周期代替。`noise_reduction_mode=off` 会真正关闭累积。
状态中的 `temporal_noise_reduction` 报告实际开关和参数；移动并稳定后仍可使用
Core 的 `reset-temporal-history` 接口失效旧历史。

`OGSCOPE_CAMERA_V4L2_TEMPORAL_NR_ALPHA` defaults to `1.0`, disabling cross-frame
accumulation so moving previews use fresh frames. Static scenes may explicitly use
a value below `1.0`; time-based weighting then uses actual processed-frame intervals,
not nominal sensor periods. `noise_reduction_mode=off` disables accumulation.
`temporal_noise_reduction` reports the effective state and parameters. The Core
`reset-temporal-history` hook still invalidates old history after movement settles.

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

本次改造只修改 OGScope 应用；联合部署文档由集成方维护，不修改 `og-bsp`。因此内核驱动、
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


## BSP 打包与配置验收 / BSP packaging and configuration acceptance

打包时必须一起更新 OGScope Python 包（含 `domain/camera/auto_exposure.py`、
`platform/hardware/v4l2_camera.py`、`application/camera_manager.py`、兼容转发 `web/camera_shared.py`、`config.py`），不要只复制前端。
RPi 后端还必须包含 `platform/hardware/tuning/imx327.json`；V4L2 软件 AE 不读取这个
libcamera tuning 文件，复制该 JSON 不能替代软件 AE 更新。

Ship the complete OGScope Python package, not only frontend assets. Include the product
`platform/hardware/tuning/imx327.json` for Picamera2. V4L2 does not consume libcamera tuning;
copying that JSON alone cannot update its software AE.

发布配置保持以下值；节点、位深与 Bayer 顺序仍按具体板型配置：
Keep these release settings; discover device nodes, bit depth and Bayer order per board:

```ini
OGSCOPE_CAMERA_AUTO_EXPOSURE_MAX_US=3000000
OGSCOPE_CAMERA_V4L2_AE_MAX_STEP_STOPS=2.0
OGSCOPE_CAMERA_V4L2_TEMPORAL_NR_ALPHA=1.0
```

现场发现旧 BSP 的 `ogscope-camera.conf` 仍设 500000µs，旧 env 示例也残留 1s。
更新镜像默认值，同时保留用户已有显式偏好；不要依赖调试机 `/data` 下的临时覆盖。
检查 systemd 的全部 `Environment` / `EnvironmentFile`：环境文件可覆盖 unit 中的值，
多个环境文件后加载者优先，尤其注意最后的 `build.env` 可能固定相机后端。

Older BSP drop-ins cap exposure at 500000µs and older env examples used 1s. Update image
defaults while preserving explicit user preferences. Do not rely on a development board's
temporary data-partition overrides. Audit every systemd Environment and EnvironmentFile;
environment files override unit values and later files win, including a build.env backend pin.

重启后打开预览并持续取帧，通过 Core `GET /api/core/v1/camera/status` 检查：
Restart, open a preview and keep consuming frames, then check Core camera status:

- `info.driver=v4l2-imx327-software-ae`（仅 V4L2 板型 / V4L2 boards only）。
- `effective_auto_exposure_max_us=3000000`（硬件支持时 / when hardware supports it）。
- `ae_policy.max_step_stops=2`、`settle_frames=2`、`filter_reset_on_control_change=true`。
- `control_readback.verified=true`，实际曝光/增益随场景收敛 / actual controls converge with the scene。
- 确认 `signal_levels`、`capture_format` 和 Bayer 配置一致 / verify signal levels and RAW format。

仅轮询 status 不会主动取帧；`streaming=true` 不能单独证明 AE 正在推进。3s 曝光时
真实帧率仍受曝光时间限制，快速 AE 不会让长曝光达到 8fps。
Polling status alone does not acquire frames; streaming=true alone does not prove AE progress.
Three-second exposure still limits physical frame rate; faster AE does not make it 8fps.
