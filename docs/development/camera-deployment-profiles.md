# 相机部署与验收 / Camera Deployment and Acceptance

最新记录 / Latest record: [2026-10-15 部署与回退实测 / Deployment and fallback validation](camera-profiles-validation-20261015.md)。

新安装默认 `v4l2` + `software`。保留两个采集后端：V4L2 下选择 CPU 或已适配的 ISP，Picamera2/libcamera 自行管理 ISP。不创建第三套相机接口；上层集成应用继续只消费 Core v1。

New installations default to `v4l2` + `software`. Keep two capture backends: V4L2 selects CPU or an adapted ISP, while Picamera2/libcamera manages its own ISP. External consumers continue to consume Core v1 without backend-specific product behavior.

| 模板 / Template | 采集 / Capture | 色彩 / Color | 用途 / Use |
|---|---|---|---|
| [`compatibility.env`](../../deploy/camera/compatibility.env) | V4L2 | CPU | 默认、无可用 ISP 适配 / Default, no usable ISP adapter |
| [`isp.env`](../../deploy/camera/isp.env) | V4L2 | BCM2835 ISP，失败后安全回退 CPU / BCM2835 ISP with safe CPU fallback | 已验证的内核、固件和节点 / Validated kernel, firmware and nodes |
| [`picamera2.env`](../../deploy/camera/picamera2.env) | Picamera2/libcamera | libcamera ISP | 树莓派系统或完整相机栈 / Raspberry Pi OS or a complete camera stack |

CPU 模式仍要求可工作的 RAW 驱动、格式及曝光/增益控件；不是任意 USB 相机适配器。直接 ISP 当前仅支持 BCM2835，不能凭其它平台存在 ISP 就启用。依赖和内核要求见[硬件加速说明](camera-hardware-acceleration.md)。

CPU mode still requires working RAW capture, formats and exposure/gain controls; it is not a universal USB-camera adapter. Direct ISP currently supports BCM2835 only. See [hardware acceleration requirements](camera-hardware-acceleration.md).

## 交付清单 / Distribution contents

三份 `deploy/camera/*.env` 模板同时进入 wheel 和源码包。BSP 从源码构建时也必须保留它们，放在可查阅的配置示例目录；不要自动把模板整份覆盖设备持久配置。`imx327.json` 随 Python 包交付；V4L2 不读取 Picamera2 的 tuning。静态相机控制台需要与后端一起构建／交付。

The wheel and source distribution include all three camera templates. BSP builds must install accessible examples too, without overwriting device configuration. The Python package retains imx327.json; V4L2 does not use Picamera2 tuning. Build and ship the matching camera console with the backend.

本次为室内验收的临时测试版：硬件 JPEG 不作为依赖，使用 TurboJPEG/OpenCV。保留既有开发板已验证的明确配置，新安装默认兼容模式。真实星空精度与主相机长曝光验收单列，不把历史测速当成新组合版本的验收结果。

This temporary preview uses software JPEG and preserves explicit verified board choices; only new installations default to compatibility mode. Real-sky geometry and main-camera tracking remain separate acceptance gates. Historical performance numbers are not acceptance of a newly integrated build.

## 配置与升级 / Configuration and upgrades

1. 选择一份模板，将相机相关键合并到现有持久配置，保留路径、网络、星库、硬件平面与服务配置。模板中的尺寸/帧率是新安装参考值；升级时保留现有值，除非明确要修改。
2. V4L2 另外需要板级 RAW、media 和 sensor 配置。用 `media-ctl -p` 和 `v4l2-ctl --list-devices` 核对目标板，不复制其它板子的节点编号。ISP 模板中的 `/dev/video13`、`/dev/video14` 只是参考，必须属于同一可用 ISP 实例。
3. 已有 Picamera2 部署在升级前保留或补齐 `OGSCOPE_CAMERA_TYPE=imx327_mipi`。未写明后端的旧部署也应先固定实际后端，避免默认值变化带来意外切换。支持 `picamera2`、`libcamera` 别名；规范值仍是 `imx327_mipi`。
4. 修改部署后端或处理方式后停止相机、重启 OGScope。运行中不自动从 Picamera2 切到 V4L2，也不反复探测故障 ISP。

1. Merge one template's camera keys into persistent configuration, preserving paths, network, star database, hardware-plane and service settings. Sizes/FPS are new-install examples; retain deployed values during upgrades unless intentionally changed.
2. V4L2 also needs verified board RAW/media/sensor settings. Discover nodes on the target. ISP node numbers are examples and must identify the same usable ISP instance.
3. Preserve or pin `OGSCOPE_CAMERA_TYPE=imx327_mipi` for existing Picamera2 deployments. Pin the effective backend before upgrading legacy installations without an explicit selection. `picamera2` and `libcamera` normalize to `imx327_mipi`.
4. Stop the camera and restart OGScope after changing deployment selection. Do not switch capture backends automatically or repeatedly retry a failed ISP.

### systemd 配置优先级 / systemd configuration precedence

**构建默认值先加载，设备持久配置后加载。** BSP 镜像的参考顺序：

**Load build defaults before persistent device settings.** Reference BSP unit order:

```ini
[Service]
EnvironmentFile=-/usr/share/ogscope/build.env
EnvironmentFile=-/data/ogscope/ogscope.env
EnvironmentFile=-/data/ogscope/network.env
```

后加载的环境文件会覆盖前面的同名键。`build.env` 放在最后会把设备选择覆盖；已实测出现“持久文件为 Picamera2、进程实际为 V4L2”。BSP 必须修正正式 unit 的顺序，`network.env` 应只写网络配置。普通树莓派安装使用 `/etc/ogscope/ogscope.env`；路径由安装环境确定。

Later files override earlier duplicate keys. A trailing `build.env` can override the user's backend selection; this was observed with Picamera2 in the persistent file but V4L2 in the process. BSP must fix the shipped unit order. Keep network files network-only. Standard Raspberry Pi installations use `/etc/ogscope/ogscope.env`; paths are deployment-specific.

应用内参数优先级仍为：相机运行时覆盖 > 实际进程环境 > dotenv 文件 > 代码默认值。不得为了绕过 BSP 的错误顺序而颠倒应用配置规则。重启后检查最终状态和实际进程环境，不能仅检查文件内容。

Application precedence remains camera runtime overrides > effective process environment > dotenv files > code defaults. Do not invert this rule to conceal an incorrectly ordered BSP unit. Check effective status and the process environment after restart, not just file contents.

只读系统由 BSP 交付 unit、依赖和设备权限；运行时配置、版本目录与回退记录写入数据分区。旧 `PYTHONPATH`/静态目录热修复覆盖必须在 OTA 时明确迁移，否则新版系统应用可能不会生效。

On read-only systems, BSP ships units, dependencies and device permissions. Runtime settings, application versions and rollback records belong on the data partition. OTA must explicitly migrate old `PYTHONPATH`/static hotfix overrides or the new image's application may remain shadowed.

## 回退与状态 / Fallback and status

- `software`：只用 CPU，不打开 ISP 节点。/ CPU only; never open ISP nodes.
- `auto`：初始化或处理失败后释放 ISP，并用当前帧回退 CPU；状态保留错误，当前实例不反复重试。/ Release a failed ISP and process the same frame on CPU; retain the failure reason and do not retry within that instance.
- `bcm2835_isp`：验收用严格模式。失败不交付 CPU 帧，`effective=unavailable`；不能把缺少硬件误判为验收成功。/ Required mode for acceptance: failure never delivers CPU frames and reports `effective=unavailable`.
- 内核异常或资源无法安全关闭不能承诺自动恢复；停止测试并恢复服务或重启设备。/ Kernel faults or unsafe resource cleanup require service/device recovery, not an automatic-recovery claim.

开发者相机页显示配置后端、请求/实际色彩处理、请求/实际编码器和回退原因。`info.image_processing` 对 Picamera2 报告 `libcamera_isp`，对 V4L2 报告 `software`、`bcm2835_isp` 或 `unavailable`。这是诊断信息，不用于上层分叉对准算法。

The camera console displays configured backend, requested/effective processing and encoder, plus fallback reasons. Picamera2 reports `libcamera_isp`; V4L2 reports `software`, `bcm2835_isp` or `unavailable`. This is diagnostic telemetry, not an upper-layer alignment selector.

旋转与编码独立选择。三份模板在星空几何验收前保留软件方向；部署中已验证的硬件方向设置可显式保留。默认软件 JPEG 自动选择 TurboJPEG/OpenCV，不依赖尚未验证的硬件 JPEG。

Orientation and encoding are independent. Templates retain software orientation until sky geometry passes; explicitly preserve already-validated hardware orientation settings when applicable. JPEG automatically selects TurboJPEG/OpenCV without requiring unverified hardware JPEG.

## 最小验收 / Minimum acceptance

1. 三份模板能选择预期后端；旧显式选择升级后不变；非法配置拒绝启动。/ Each template selects the intended backend; explicit legacy selection survives; invalid selection is rejected.
2. ISP 严格模式持续输出有效帧；缺失节点与模拟运行失败符合回退策略，状态不伪报硬件成功。/ Required ISP delivers real frames; missing nodes and simulated runtime failures follow policy without false hardware success.
3. 同场景检查 RGB 色序、180°方向、实际尺寸/FOV、3 秒曝光上限、明暗切换，以及共享解算帧身份。/ Compare RGB order, orientation, size/FOV, the 3-second ceiling, light/dark transitions and shared solve-frame identity.
4. 长预览加并发解算，检查 CPU、PSS、swap、CMA、OOM、过期帧、停止/重启和配置持久化；不能只看进程 PSS。/ Sustain preview with concurrent solving; inspect CPU, PSS, swap, CMA, OOM, stale frames, stop/restart and persistence, not process PSS alone.
5. 保存原配置、源码版本、静态资源和传感器翻转；回退后独立检查服务健康、画面和最终配置。夜空精度验收单独记录。/ Save config, application/static versions and sensor flips; independently verify health, frames and effective config after rollback. Record sky-accuracy acceptance separately.
## V4L2 warm-idle freshness / V4L2 保温空闲后的帧新鲜度

An open V4L2 stream can retain queued images while analysis and preview stop reading. These images must not be accepted as current observations when reading resumes. After a read gap exceeding two frame periods (with a 0.5-second minimum), the RAW driver reuses its existing exposure-freshness gate and resets temporal history before returning a frame. Continuous capture and short retries do not rearm that gate. The stream and image-processing profile stay unchanged.

分析及预览停止读取时，仍打开的V4L2流可能积压旧图像，恢复读取后不能将其当成当前观测。读取中断超过两个帧周期（最短0.5秒）时，RAW驱动复用已有的曝光新鲜度门槛，并清除跨帧历史，再交付图像；连续抓帧和短暂重试不重新等待，流及图像处理配置保持不变。

Ship `ogscope/platform/hardware/v4l2_camera.py`, `ogscope/web/camera_shared.py` and `ogscope/domain/camera/services.py` together and restart OGScope while camera jobs are idle. No new environment key, BSP dependency or controller firmware is required. Preserve the previous application source for rollback. UTC remains estimated from read completion and exposure duration; this change does not introduce hardware exposure timestamps. Acceptance compares stationary star motion across capture, warm idle and resume, as well as stop/restart and short retry behavior.

部署须同时包含本次修改的`ogscope/platform/hardware/v4l2_camera.py`、`ogscope/web/camera_shared.py`和`ogscope/domain/camera/services.py`，在相机任务空闲时重启OGScope，并保留旧程序以便回退；无需新增环境配置、BSP依赖或控制器固件。UTC仍由读取完成时刻和曝光时间估算，本修改没有引入硬件曝光时间戳。验收应比较静止底座上连续采集、保温空闲及恢复时的星点运动，同时检查停止重启和短暂重试。


The shared RAW cache now keeps the sequence and read-completion timestamp of its own pixels, rather than the current global capture counter. A later preview prefetch cannot relabel an older image. Cache reuse expires after two observed frame periods / target preview periods, with a 0.5 s floor; an expired cache causes a real read. Explicit history reset invalidates cached and in-flight reads and serializes the driver hook with the same capture worker. Late JPEG completion cannot reintroduce a pre-reset RAW frame. No extra retained image is added when `OGSCOPE_KEEP_RAW_CACHE=0`.

共享 RAW 缓存保存图像自身的序号和读完时间，后续预读不能用全局新序号给旧图像重新贴标签。缓存复用最多两个实测帧周期/目标预览周期，最短 0.5 秒；超时后实际读帧。显式历史重置同时使缓存与在途读帧失效，并在同一采集线程执行驱动钩子；晚到的 JPEG 编码不能把旧 RAW 塞回分析缓存。关闭 RAW 缓存时不新增常驻图像。

Repeated start calls preserve warm-idle tracking. The V4L2 freshness window stays active until a fresh image has actually been dequeued, not merely until wall time passes. Verify both RAW-cache settings, preview prefetch during reset, long exposures, warm idle/resume and quick stationary retries on the board. Cache identity and timing are locally tested; the expanded cache/reset path still requires board acceptance. Read completion remains an estimate, not a sensor exposure-start timestamp.

重复启动保留温空闲追踪；V4L2 必须真正取到新图像才结束新鲜度等待，不能只靠时间经过。实机需覆盖 RAW 缓存开/关、预读期间重置、长曝光、保温恢复和原地快速重试。缓存身份与时序已有本地测试，扩展的缓存/重置路径仍需实机验收；读取完成时间仍不等于传感器曝光起始时间。
