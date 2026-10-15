# 相机硬件加速实验 / Camera Hardware Acceleration Experiment

部署选择、升级保留策略及配置优先级见[相机部署与验收](camera-deployment-profiles.md)。以下为硬件实现与测量记录。 / See [deployment and acceptance](camera-deployment-profiles.md) for profiles, upgrade preservation and configuration precedence. Below are implementation and measurement records.

本实现保留两个相机后端及既有 RGB888、视场、精确解算帧契约。ISP、传感器硬件变换和采集编码重叠均为显式实验配置，默认关闭。软件处理仍可独立使用。

Both backends preserve RGB888, effective FOV and exact solve-frame contracts. ISP processing, sensor transforms and capture/encode overlap are explicit experiments disabled by default. The software path remains independently usable.

## 配置与打包 / Configuration and packaging

| 环境变量 / Environment variable | 默认 / Default | 含义 / Meaning |
|---|---|---|
| `OGSCOPE_CAMERA_ROTATION` | `180` | 逆时针 0/90/180/270 度 / Counterclockwise quarter turns |
| `OGSCOPE_CAMERA_HARDWARE_TRANSFORM` | `false` | 两个后端尝试传感器硬件翻转 / Both backends attempt sensor flips |
| `OGSCOPE_CAMERA_V4L2_PROCESSING` | `software` | `software`、`auto`、`bcm2835_isp` |
| `OGSCOPE_CAMERA_V4L2_ISP_INPUT_DEVICE` | `/dev/video13` | 板级 RAW 输入节点，需确认 / Board-specific RAW input, verify on target |
| `OGSCOPE_CAMERA_V4L2_ISP_OUTPUT_DEVICE` | `/dev/video14` | 同一 ISP 实例的 RGB 输出 / RGB output of the same ISP instance |
| `OGSCOPE_CAMERA_V4L2_ISP_TIMEOUT_SEC` | `2` | 处理已采集帧的超时，不是曝光上限 / Processing timeout, not exposure limit |
| `OGSCOPE_PREVIEW_PIPELINE_ENABLED` | `false` | 吞吐受限时最多预读一帧 / Prefetch at most one frame when throughput-bound |
| `OGSCOPE_PREVIEW_ENCODER` | `auto` | 新增可选 `v4l2_mjpeg` / Optional new `v4l2_mjpeg` preference |
| `OGSCOPE_PREVIEW_HARDWARE_ENCODER_DEVICE` | 空 / Empty | 空值按驱动名发现，否则使用指定节点 / Discover by driver name or use explicit node |

不要只更新应用而遗漏系统默认配置。发布镜像应同步保留这些开关、有效的 RAW 节点、传感器子设备和 ISP 节点权限；不得盲目把某块板子的 `/dev/video*` 编号复制到所有板子。运行时覆盖可能优先于打包默认值，必须检查最终生效配置。

Ship the switches and verified RAW/sensor/ISP permissions with the application. Device numbers are board-specific, not universal. Check configuration precedence and effective values rather than assuming packaged defaults win.

### BSP 系统交付清单 / BSP delivery requirements

| 功能 / Feature | 系统必须提供 / Required system support | 本次板端状态 / Tested board status |
|---|---|---|
| V4L2 RAW | 可工作的 IMX327/Unicam 驱动、正确的 media graph、RG12 原始输出，以及曝光/增益/帧周期控件；交付 `v4l2-ctl` 和 `media-ctl` / Working IMX327/Unicam drivers, media graph, RG12 capture and exposure/gain/frame-period controls; ship `v4l2-ctl` and `media-ctl` | 已有并通过实测 / Available and tested |
| V4L2 ISP | 与内核匹配的 `CONFIG_VIDEO_ISP_BCM2835` 或该版本等效配置、VCHIQ/MMAL 和匹配的 VideoCore 固件；提供同一 ISP 实例的 RAW 输入和 RGB3 输出节点 / Kernel-matched BCM2835 ISP support, VCHIQ/MMAL and compatible VideoCore firmware; paired RAW-input/RGB3-output nodes | 已有并通过严格 ISP 模式实测 / Available and tested in required ISP mode |
| 硬件旋转 / Hardware orientation | V4L2 传感器可回读的 H/V 翻转；Picamera2 路径需兼容的 libcamera `Transform` 与 Python 绑定 / Readable sensor H/V flips for V4L2; compatible libcamera `Transform` and Python bindings for Picamera2 | 两后端 180°通过；夜空中心偏移待验收 / 180° works on both; sky field-center acceptance pending |
| 硬件 JPEG / Hardware JPEG | `CONFIG_VIDEO_CODEC_BCM2835` 或该版本等效配置；如为模块须交付 `bcm2835-codec` 及依赖并保证加载；编码节点须实际支持 MJPG 输出、RGB3/BGR3 输入和输入时间标识回传 / BCM2835 codec support; package/load the module and dependencies when modular; verify MJPG output, RGB3/BGR3 input and echoed input timestamps | 编码节点和模块均缺失，尚未验收 / Encoder node and module absent; unverified |
| 运行库 / Runtime libraries | NumPy、OpenCV；Picamera2 后端另需 Picamera2/libcamera 及匹配服务 Python 的绑定；软件快速 JPEG 需 `libturbojpeg.so`，应用依赖包含 PyTurboJPEG 包装 / NumPy/OpenCV; Picamera2/libcamera and Python-compatible bindings for that backend; `libturbojpeg.so` plus the application's PyTurboJPEG wrapper for fast software JPEG | 当前可使用 TurboJPEG；缺库会回退 OpenCV / TurboJPEG works; OpenCV remains the fallback |
| 服务权限 / Service permissions | 服务用户可读写实际 RAW、sensor-subdev、media、ISP、编码和必要的 VCHIQ 节点；由系统设备权限/组规则交付，不要求应用自行改只读系统 / Service-user access to actual RAW, sensor-subdev, media, ISP, codec and required VCHIQ nodes through OS permissions/group rules | 已用目标板验证；镜像仍须按正式服务用户验收 / Tested on target; image acceptance must use the shipped service user |
| 配置和资源 / Config and assets | 同时交付应用模块、上述配置开关和产品 `imx327.json` tuning；核对服务实际环境、持久配置和覆盖优先级 / Ship application modules, switches and product `imx327.json` tuning; verify effective service environment and persistent overrides | 实验开关默认关闭；不能只更新 Python 源码就宣称启用 / Experiments default off; updating Python alone does not activate them |

参考内核配置：[BCM2835 ISP Kconfig](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/drivers/staging/vc04_services/bcm2835-isp/Kconfig)、[BCM2835 codec Kconfig](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/drivers/staging/vc04_services/bcm2835-codec/Kconfig)。BSP 应核对自己使用的内核源码和平台；内建驱动可以没有 `.ko` 文件，验收依据是节点、格式协商和实际帧处理，不是单独的 `modinfo` 结果。

Use the linked kernel configuration as a reference and verify the BSP's actual kernel/platform. Built-in drivers need no `.ko` file; acceptance depends on nodes, negotiated formats and real frame processing, not `modinfo` alone.

系统需保留足够的 CMA/DMA 连续内存，并验证两缓冲分配、长期预览和并发解算。仅本 ISP 的两张 RAW 输入加两张 RGB 输出，不计行对齐约占 720p 的 8.8 MiB、1080p 的 19.8 MiB；这不包含传感器、GPU、Python 和解算内存，不能直接作为镜像 CMA 配额。当前短测已有较低的 CMA 空闲量，不能仅凭进程 PSS 决定系统配额。

Preserve sufficient contiguous CMA/DMA memory and verify two-buffer allocation, sustained preview and concurrent solving. The ISP's two RAW-input plus two RGB-output buffers alone require about 8.8 MiB at 720p or 19.8 MiB at 1080p before stride alignment. Sensor/GPU/Python/solver memory is additional; these figures are not image-wide CMA recommendations. Low free CMA in short probes means process PSS alone is insufficient for sizing.

本板使用现有系统已能运行 ISP、硬件方向与软件编码重叠，不要求为这三项先更换系统镜像。硬件 JPEG 则需要 BSP 补齐编码能力并完成实际编码验收。内核对无效镜头阴影 DMA 描述符的异常处理也建议加固；本应用已禁止发送未经验证的镜头阴影控件。

The existing tested image already supports ISP, hardware orientation and software-encoding overlap without an OS replacement. Native hardware JPEG requires BSP codec support and real encoding acceptance. Harden invalid lens-shading DMA descriptor handling in the kernel as well; this application forbids unvalidated lens-shading controls.

## V4L2 ISP

`software` 完全沿用 CPU RAW 处理。`auto` 尝试 BCM2835 ISP，初始化或运行失败时释放资源，并对当前同一帧回退 CPU。`bcm2835_isp` 是严格模式：缺少 ISP 或 ISP 失败则停止交付帧，不静默伪装成硬件成功。

`software` retains CPU RAW processing. `auto` tries BCM2835 ISP and falls back on the same frame after releasing resources. Required `bcm2835_isp` stops delivering frames on failure instead of silently claiming hardware success.

RAW 采集、已验证的软件 AE/AWB 和 RAW 时域降噪保留。硬件执行黑电平、线性白平衡、去马赛克和 Gamma；额外图像增强、裁切/缩放及必要的残余几何变换仍使用 CPU。没有把 V4L2 改名为 Picamera2，也没有把软件统计宣称为 ISP 自动曝光。

RAW capture, existing software AE/AWB and RAW temporal filtering remain. Hardware performs black-level correction, linear WB, demosaic and gamma. Additional enhancement, crop/resize and residual geometry remain CPU work. This is direct ISP access, not a renamed Picamera2 backend or an ISP-managed AE claim.

每个节点最多分配两缓冲，每次只提交一张 RAW 并同步收回对应 RGB。输出在归还 DMA 缓冲前复制为独立 ndarray；不保留历史输出。黑电平从 RAW 位深转换到 ISP 的 16 位域；白电平归一化与 Gamma 有独立配置，不直接复制不相容单位。

Each node uses at most two buffers. Each submitted RAW frame is synchronously paired with its RGB output, copied before DMA buffer reuse. Black level is converted into the ISP's 16-bit units; white normalization and gamma are configured explicitly.

ISP 和硬件编码为每张输入附带单调递增的微秒标识，并核对输出的 `TIMESTAMP_COPY` 类型与回传值。标识不匹配时拒绝该输出，按对应策略回退或停止。此标识仅校验处理器输入输出，不替代采集 UTC、曝光中点或解算会话帧标识。

ISP and hardware encoding attach a monotonically increasing microsecond token to each input, requiring the output's `TIMESTAMP_COPY` type and echoed value to match. Mismatches are rejected and follow the configured failure policy. This internal token does not replace capture UTC, exposure midpoint or solve-session frame identifiers. See [Linux V4L2 buffer timestamps](https://docs.kernel.org/userspace-api/media/v4l/buffer.html).

本实验使用单位颜色矩阵并关闭 ISP 降噪、锐化和坏点修正，便于对照。尚不等价于经过完整色卡、镜头阴影和夜空验证的 libcamera 调参链路；硬件与软件去马赛克/Gamma 的像素结果也不承诺完全相同。

The experiment uses an identity color matrix and disables ISP denoise, sharpening and defective-pixel correction for comparison. It does not replace a fully validated libcamera tuning chain, and hardware/software demosaic and gamma are not guaranteed to be pixel-identical.

## 硬件画面方向 / Hardware orientation

0°和180°通过水平/垂直翻转组合实现；90°/270°使用软件。Picamera2 读取 libcamera 实际配置的 transform；V4L2 写入并回读传感器控件，同时核对 Bayer 格式。无法验证时不使用猜测值。软件只执行实际硬件变换之外的剩余操作，因此不会重复翻转；运行时改变方向也按剩余变换处理。

0°/180° use sensor flips; quarter turns use software. Picamera2 checks the configured libcamera transform. V4L2 verifies sensor-control readback and Bayer format. Software applies only the residual transformation, including runtime orientation changes.

实机 IMX327 的翻转会让传感器报告的裁切起点偏移一个像素。颜色相位虽保持不变，这仍需要通过相同星空/稳定图像对照判断视场中心和极轴误差影响。硬件方向开关保持默认关闭，不能把合成像素测试当作机械轴精度验收。

The tested IMX327 reports a one-pixel crop-origin change when flipped. Bayer order remains unchanged, but field-center and polar-error effects need paired image/sky validation. The switch stays off by default; synthetic geometry tests do not establish mechanical-axis accuracy.

## 编码与流水线 / Encoding and pipeline

软件路径继续使用已测速选择的 TurboJPEG/OpenCV。实验重叠模式最多持有当前编码帧与一张预读帧，采集仍由原有单工作线程执行；时间戳记录于读帧完成时刻，不能挪到编码完成时刻。停止时等待读帧和编码工作线程收尾，硬件编码缓冲在所属编码线程释放。

Software encoding retains measured TurboJPEG/OpenCV selection. Experimental overlap keeps the encoding frame and at most one prefetched frame. Capture remains on its single worker. Timestamps identify read completion, not delayed encode completion. Stop drains capture/encode work before releasing native encoder resources.

预览循环自身发生错误时，同样先收回预读工作再关闭相机；初始化失败和 ISP 关闭失败也会尝试恢复传感器方向。 / Errors inside the preview loop also drain prefetch before camera close; initialization or ISP-close failures still attempt sensor-transform restoration.

可选硬件 MJPEG 通过同一 V4L2 mem2mem 上下文管理输入输出，仍交付独立 JPEG，兼容网页 MJPEG。节点缺失、格式不支持或编码失败时，同一帧回退软件；该实例不再每帧重复尝试失败的硬件。硬件采用码率预算，不能把它与软件 JPEG 的质量值视为完全等价。

Optional hardware MJPEG uses one shared V4L2 mem2mem context and returns independent JPEGs compatible with browser MJPEG. Missing nodes, unsupported formats or encoding failure fall back on the same frame without repeatedly retrying failed hardware. Hardware bitrate mapping is not identical to software JPEG quality.

任一映射或队列关闭失败时，仍尝试释放其余映射、文件描述符及另一队列。编码线程停止失败会要求服务恢复，不报告安全关闭。客户端质量变体使用软件编码，不反复重建硬件编码上下文。

If one mapping or queue fails to close, remaining mappings, descriptors and the other queue are still released. Encoder-stop failures require service recovery rather than reporting a safe shutdown. Client quality variants use software encoding without rebuilding the hardware context.

## 板端证据与限制 / Board evidence and limits

2026-10-14 检查的 BCM2835 系统（Linux `7.1.13-v8`）提供 ISP 输入、RGB 输出和统计节点，接受 RG12；传感器提供可回读的水平/垂直翻转。当前没有 `bcm2835-codec-encode` 节点，硬件 MJPEG 适配器尚无法进行真实编码验收。BSP 需核对编码驱动构建、加载与节点权限，不能把存在 ISP 当作存在编码器。

The BCM2835 system inspected on 2026-10-14 (Linux `7.1.13-v8`) exposes ISP RAW/RGB/statistics nodes, supports RG12, and has readable sensor flips. It does not expose `bcm2835-codec-encode`, so native hardware MJPEG acceptance remains pending. BSP must verify codec build/loading and permissions independently of ISP availability.

首次独立合成 RAW 探针在发送空的“禁用镜头阴影”负载时，触发 `bcm2835_isp_s_ctrl → dma_buf_put` 内核异常。驱动对无效 DMA fd 的错误指针处理不安全。该调用已移除，并加入用户态拒绝保护；没有有效且单独验证的 DMA 表时，任何禁用/启用镜头阴影请求都禁止发送。内核异常后需要重启恢复驱动状态，后续板端结果不得沿用异常状态下的测试。

The first standalone synthetic RAW probe triggered a kernel fault in `bcm2835_isp_s_ctrl → dma_buf_put` when given an empty lens-shading-disable payload. The affected driver mishandles invalid DMA descriptors. That call was removed and guarded in userspace. No lens-shading control may be sent without a separately validated DMA table. Reboot is needed after the fault before further board validation.

硬件队列在内核已标记 Oops 时拒绝打开，避免用户在异常状态下重复试验。 / Hardware queues refuse to open when the kernel records an Oops, preventing repeated experiments in a faulted state.

设备重启后内核异常标记清零。修正后的合成 RAW 探针通过 6 帧颜色顺序、输入输出标识、输出缓冲所有权和关闭检查；真实 V4L2 相机在严格 ISP 模式下连续处理数百帧，没有触发软件回退或新的内核异常。两个后端的 180°硬件变换均通过配置/控件回读。

After reboot, the kernel fault marker cleared. The corrected synthetic RAW probe passed six-frame RGB order, echoed input tokens, output ownership and close checks. Real V4L2 capture processed hundreds of frames in required ISP mode without software fallback or a new kernel fault. Both backends confirmed 180° hardware transforms through configuration/control readback.

当前系统既没有编码节点，也找不到 `bcm2835-codec` 模块。BSP 应根据其内核版本核对 [`CONFIG_VIDEO_CODEC_BCM2835`](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/drivers/staging/vc04_services/bcm2835-codec/Kconfig)、模块交付与自动加载、VCHIQ/固件兼容性，以及节点实际支持的输入格式与 MJPEG。仅提供环境变量不能补上缺失的内核驱动。

The current system has neither an encoder node nor a discoverable `bcm2835-codec` module. BSP must check the kernel-version-appropriate `CONFIG_VIDEO_CODEC_BCM2835`, module packaging/loading, VCHIQ/firmware compatibility, and actual RGB/MJPEG format support. Environment switches cannot supply a missing kernel driver.

### 独立预览链路实测 / Isolated preview-pipeline measurements

同一块板，1280×720、180°输出、预览目标 30 fps、JPEG 质量 75、TurboJPEG；使用相同短手动曝光和固定白平衡，关闭降噪。每组独立进程预热 4 秒后采样 15 秒，运行本分支相机管理器的采集与 JPEG 链路；正式 OGScope/external client 服务保持运行但产品相机已停止。此处统计 JPEG 发布吞吐，不含浏览器网络传输或并发星空解算。

Same board, 1280×720, 180° output, target 30 fps, JPEG quality 75 and TurboJPEG; identical short manual exposure/fixed WB, denoise off. Separate processes warm for four seconds and sample for fifteen, running this branch's camera-manager capture/JPEG path while product services remain running with their camera stopped. These are JPEG-publish rates, excluding browser transport and concurrent solving.

| 路径 / Path | fps | CPU % | 读帧 / Read ms | JPEG ms |
|---|---:|---:|---:|---:|
| V4L2 软件处理、软件旋转 / Software processing and rotation | 7.84 | 162 | 93.34 | 33.13 |
| V4L2 软件处理、硬件旋转 / Software processing, hardware rotation | 8.60 | 167 | 82.50 | 32.82 |
| V4L2 ISP、硬件旋转 / ISP and hardware rotation | 12.26 | 95 | 48.58 | 31.55 |
| V4L2 ISP、硬件旋转、重叠 / ISP, hardware rotation and overlap | 19.93 | 156 | 49.19 | 32.07 |
| Picamera2 软件旋转 / Software rotation | 18.45 | 115 | 22.04 | 30.67 |
| Picamera2 硬件旋转 / Hardware rotation | 23.07 | 114 | 10.50 | 31.16 |
| Picamera2 硬件旋转、重叠 / Hardware rotation and overlap | 29.10 | 145 | 19.62 | 31.93 |

CPU 100% 表示占满一个核心。软件旋转已使用 OpenCV；本表不是旧版 NumPy 旋转链路的复测。硬件 JPEG 尚未验收，表中 JPEG 都仍由 CPU 编码。重叠模式增加单位时间处理量，因此总 CPU 可能上升，不能把帧率提升误读成总 CPU 必然下降。

100% CPU means one fully occupied core. Software rotation already uses OpenCV, so this table is not a rerun of the former NumPy rotation path. JPEG remains CPU-encoded; native hardware JPEG has not been accepted. Overlap processes more frames per second, so higher throughput does not guarantee lower total CPU.

硬件加速不能缩短当前曝光本身。另一次正式服务读数为约 184ms 曝光、185ms 帧周期和 5.3–5.5 fps，已接近曝光允许的约 5.4 fps；8 fps 需要曝光不超过约 125ms，30 fps 需要不超过约 33ms，并额外留出采集/处理余量。本 PR 不改变曝光与增益的优先策略，也不承诺长曝光下达到上述短曝光帧率。

Acceleration cannot shorten the exposure itself. A separate product-service reading showed approximately 184ms exposure, 185ms frame period and 5.3–5.5 fps, close to the approximately 5.4 fps exposure limit. Eight fps needs exposure at or below about 125ms; thirty fps needs about 33ms or less, with capture/processing margin. This PR does not change exposure/gain priorities or promise short-exposure throughput during long exposures.

这些短测没有 OOM。独立相机进程 PSS 约 88–97 MiB，首个软件组另有约 12 MiB SwapPss；PSS 不包含全部 DMA/GPU 内存，不能据此认定 ISP 总内存更低。部分组 CMA 空闲量很低，发布前仍需验证长期预览、并发解算、1080p，以及可见场景和夜空下的图像/几何结果。

No OOM occurred in these short probes. Camera-process PSS was about 88–97 MiB, with roughly 12 MiB SwapPss in the first software case. PSS excludes some DMA/GPU memory and does not establish lower total ISP memory use. Low free CMA in several cases still warrants sustained preview/concurrent-solving/1080p validation, plus visible-scene and sky image/geometry acceptance.

另以 50ms 手动曝光对照室内窗帘图像，两个后端的软硬件旋转方向一致；这只能排除明显重复翻转，不能验证一像素级中心偏移。V4L2 ISP 的 AE 从 10ms 起点到首次采样时（预热四秒后约一秒）已收敛到约 183ms，并在这轮 15 秒采样期间保持稳定；RAW AWB 回报收敛。选择硬件 MJPEG 时因节点缺失成功回退 TurboJPEG，ISP 仍保持实际启用。

Paired indoor curtain images at 50ms manual exposure confirmed matching software/hardware orientation on both backends. This excludes gross double flips, not one-pixel field-center shifts. Starting from 10ms, V4L2 ISP AE had converged to about 183ms at the first sample, roughly one second after the four-second warm-up, and remained stable during the fifteen-second sample window; RAW AWB also reported convergence. Requested hardware MJPEG correctly fell back to TurboJPEG because the node was missing, while ISP processing remained active.

相关公开接口：[BCM2835 ISP UAPI](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/include/uapi/linux/bcm2835-isp.h)、[驱动镜头阴影处理](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/drivers/staging/vc04_services/bcm2835-isp/bcm2835-v4l2-isp.c)、[Picamera2 编码与 transform](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)。

## 验收与回退 / Acceptance and rollback

开发板试用配置可选择 `OGSCOPE_CAMERA_V4L2_PROCESSING=auto`、`OGSCOPE_CAMERA_HARDWARE_TRANSFORM=true`、`OGSCOPE_PREVIEW_PIPELINE_ENABLED=true`、`OGSCOPE_PREVIEW_ENCODER=turbojpeg`，同时明确经过验证的 ISP 节点。保留原帧率、曝光上限、图像尺寸及持久配置，将新应用放入独立的数据分区版本目录，仅重启 OGScope。切换前备份原配置、源文件校验值、相机状态和 H/V 控件；回退时先停止相机进程，再恢复 H/V 控件和配置。

A developer-board trial can select ISP `auto`, hardware transforms and preview overlap, keeping `turbojpeg` encoding and explicitly verified ISP nodes. Preserve existing FPS/exposure limits/geometry and persistent settings, place the application in a separate data-partition release directory, and restart only OGScope. Back up config, source hashes, camera state and H/V controls before switching. Rollback stops the camera process before restoring H/V controls and config.

2026-10-14 的开发板试用已启用以上配置，运行代码为 `2819404`，保留 1280×720、180°、8 fps 目标与 3s 曝光上限。30 秒真实 MJPEG 检查处理了 160 多帧 ISP 图像，AE/AWB 收敛，没有软件回退、JPEG 错误、OOM 或内核异常。暗室内约 183ms 曝光时，实际约 5.4–5.5 fps，受快门时长限制。部署验收过程中也实际恢复过旧配置和 H/V 控件，再启用试用版本。

The 2026-10-14 developer-board trial runs code `2819404` with this profile, retaining 1280×720, 180°, target 8 fps and the 3s exposure ceiling. Thirty seconds of real MJPEG monitoring processed over 160 ISP frames with converged AE/AWB and no software fallback, JPEG errors, OOM or kernel fault. At approximately 183ms indoor exposure, actual throughput was about 5.4–5.5 fps due to shutter duration. Acceptance also restored the previous config/H/V controls before final trial activation.

正式打包或 OTA 验收前必须处理开发板的 `PYTHONPATH` 覆盖：先回退试用覆盖，或将其迁移到受版本管理的发布路径，再核对服务实际导入代码和配置。只更新只读根分区的应用包、仍保留数据分区旧源码覆盖，不能视为完成升级。

Before image packaging or OTA acceptance, remove/rollback the developer `PYTHONPATH` overlay or migrate it to a versioned release mechanism, then verify actual module origins and effective config. Updating the read-only-root application package while a stale data-partition source overlay still wins does not establish a completed upgrade.

部署验收必须通过 HTTP 实际检查 `info.image_processing.effective` 与有效帧计数、回读确认的硬件方向，以及流状态中的 `preview_pipeline_enabled`、`hardware_encoder_error` 和实际编码器；不能只检查环境变量。流响应模型显式保留这两个加速诊断字段，兼容旧指标时分别默认为 `false` 和 `null`。同时核对有效 JPEG、两服务健康、轴位置、内核异常标记与根分区只读状态。

Acceptance checks actual HTTP processing mode/frame count, verified transforms, stream `preview_pipeline_enabled`/`hardware_encoder_error` and the effective encoder, not merely environment variables. The stream response model explicitly preserves both diagnostics and defaults legacy metrics to `false`/`null`. Verify complete JPEGs, both services, unchanged axes, kernel fault state and read-only root as well.

- 本地：四个旋转角与全部硬件/软件镜像组合、RGB 顺序、帧所有权、DMA 控件保护、超时/初始化失败、严格 ISP 策略、编码失败回退、重叠模式停止收尾。 / Local: geometry combinations, RGB order, frame ownership, DMA control guard, initialization/timeout policy, encoder fallback and overlap cancellation/drain.
- 板端：重启清除异常后，先合成 RAW 验证 ISP 的尺寸、颜色顺序、连续多帧和关闭；再验证实际相机、手动曝光、双向 AE/AWB、帧率、峰值内存及并发解算。 / Board: after recovery, synthetic RAW dimensions/color/multiple-frame/close checks, followed by real capture, manual controls, bidirectional AE/AWB, throughput, peak memory and concurrent solving.
- 夜间：硬件翻转后的视场中心、极轴目标、解算精度与主相机跟踪效果。 / Night: field center, polar target, solve precision and main-camera tracking with hardware flips.
- 应用回退：`OGSCOPE_CAMERA_V4L2_PROCESSING=software`、`OGSCOPE_CAMERA_HARDWARE_TRANSFORM=false`、`OGSCOPE_PREVIEW_PIPELINE_ENABLED=false`、`OGSCOPE_PREVIEW_ENCODER=auto`，重新启动相机服务后核对实际状态。 / Application fallback: restore the four software defaults, restart camera service and verify effective state.
- 回退到不重置传感器翻转的旧版本时，必须先停止相机，再恢复实验前的 H/V 控件并回读，之后启动旧服务。Picamera2 关闭不会自动恢复此前的传感器翻转；不能只撤销应用配置就声称方向已回退。 / Before reverting to an older revision that does not reset sensor flips, stop the camera, restore/read back the pre-experiment H/V controls, then start the old service. Picamera2 close does not automatically restore the preceding sensor flips; removing application settings alone does not prove orientation rollback.

本实验没有修改只读系统目录、内核、系统镜像或电机逻辑。临时硬件探针与正式服务部署分别管理；发布前应以板端和夜空验收为准。

The experiment does not modify read-only OS directories, kernel, system image or motor logic. Standalone probes and service deployment are managed separately; board and sky acceptance remain the release criteria.
