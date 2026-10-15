# 相机部署与验收 / Camera Deployment and Acceptance

最新记录 / Latest record: [2026-10-15 部署与回退实测 / Deployment and fallback validation](camera-profiles-validation-20261015.md)。

新安装默认 `v4l2` + `software`。保留两个采集后端：V4L2 下选择 CPU 或已适配的 ISP，Picamera2/libcamera 自行管理 ISP。不创建第三套相机接口；external client 继续只消费 Core v1。

New installations default to `v4l2` + `software`. Keep two capture backends: V4L2 selects CPU or an adapted ISP, while Picamera2/libcamera manages its own ISP. external client continues to consume Core v1 without backend-specific product behavior.

| 模板 / Template | 采集 / Capture | 色彩 / Color | 用途 / Use |
|---|---|---|---|
| [`compatibility.env`](../../deploy/camera/compatibility.env) | V4L2 | CPU | 默认、无可用 ISP 适配 / Default, no usable ISP adapter |
| [`isp.env`](../../deploy/camera/isp.env) | V4L2 | BCM2835 ISP，失败后安全回退 CPU / BCM2835 ISP with safe CPU fallback | 已验证的内核、固件和节点 / Validated kernel, firmware and nodes |
| [`picamera2.env`](../../deploy/camera/picamera2.env) | Picamera2/libcamera | libcamera ISP | 树莓派系统或完整相机栈 / Raspberry Pi OS or a complete camera stack |

CPU 模式仍要求可工作的 RAW 驱动、格式及曝光/增益控件；不是任意 USB 相机适配器。直接 ISP 当前仅支持 BCM2835，不能凭其它平台存在 ISP 就启用。依赖和内核要求见[硬件加速说明](camera-hardware-acceleration.md)。

CPU mode still requires working RAW capture, formats and exposure/gain controls; it is not a universal USB-camera adapter. Direct ISP currently supports BCM2835 only. See [hardware acceleration requirements](camera-hardware-acceleration.md).

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
