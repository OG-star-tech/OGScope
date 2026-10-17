# 相机部署收敛验收 / Camera Profile Validation — 2026-10-15

本次验证三种显式部署选择和安全回退，不将目标 8 fps 的结果视为性能上限。板端为 IMX327、BCM2835 ISP、1280×720、180°输出；JPEG 使用软件自动选择，硬件方向关闭。

This validates explicit selection and fallback, not maximum throughput: all profiles target 8 fps. The board uses IMX327/BCM2835 ISP, 1280×720 and 180° output, software-selected JPEG and software orientation.

| 场景 / Case | 持续时间 / Duration | 收到 JPEG / JPEGs received | 结果 / Result |
|---|---:|---:|---|
| V4L2 CPU | 35 s | 205 | `software`，无 ISP 尝试 / No ISP attempt |
| V4L2 严格 ISP / Required ISP | 150 s | 1,138 | `bcm2835_isp`，硬件处理 1,209 帧，无回退 / 1,209 hardware frames; no fallback |
| Picamera2/libcamera | 35 s | 267 | `libcamera_isp`，显式后端生效 / Explicit backend honored |
| ISP 节点缺失 / Missing ISP node | 20 s | 150 | 同帧 CPU 回退，状态保留错误，`fallback_active=true` / Same-frame fallback with visible error |

ISP 严格场景同时调用实时分析；室内得到 `TOO_FEW`/`NO_MATCH`，不据此宣称星空解算成功。系统星库已预热。四个场景无新增 OOM 或内核异常；ISP 场景系统可用内存最低约 70.7 MiB。部分场景空闲 CMA 仍较低，不能用这几分钟替代长时间及 1080p 压力验收。

Required ISP ran with concurrent real-time analysis; indoor `TOO_FEW`/`NO_MATCH` does not establish a successful sky solve. The star database was warmed. No new OOM/kernel fault occurred; minimum available system memory in the ISP case was approximately 70.7 MiB. Low free CMA in some cases still requires longer and 1080p stress acceptance.

临时 systemd 配置使设备持久选择在构建默认值之后加载，实测 Picamera2 与 V4L2 均可正确选择。测试结束删除临时覆盖，恢复原部署；持久相机配置哈希保持一致，ZenitAPA 进程未重启，ALT/AZ 位置未变化，根目录保持只读。

A temporary systemd override loaded profile selection after build defaults and demonstrated both backends. It was removed after testing. Original deployment and persistent camera configuration were restored; ZenitAPA's process and ALT/AZ positions stayed unchanged, and the root remained read-only.

板端原 unit 最后加载 `build.env`，会覆盖持久文件的驱动选择。这是仍需 BSP 按[部署说明](camera-deployment-profiles.md)修正的交付项，应用没有倒置环境变量优先级来隐藏它。镜头当前画面接近灰色且纹理较少，不能据此确认色卡、白平衡准确度或星空几何精度；色序由非对称 RGB 单元测试覆盖。

The original BSP unit loads `build.env` last, overriding persistent backend selection. BSP must ship the corrected order in the [deployment guide](camera-deployment-profiles.md); application precedence was not inverted to conceal it. The current nearly gray, low-texture scene does not establish color-chart, AWB or sky-geometry accuracy; asymmetric RGB tests cover channel ordering.

本地验证：Python 全量单元测试、Black/Ruff、前端构建和两项前端测试。独立 `tsc --noEmit` 仍有既有类型/路径别名错误；与修改前同基线比对，本次无新增错误。已有问题未混入本次相机修复。

Local validation: full Python unit tests, Black/Ruff, frontend build and two frontend tests. Standalone `tsc --noEmit` retains existing type/path-alias errors; comparison with the unchanged baseline found no new errors. Those pre-existing issues were kept outside this camera change.

当前代码在独立短期分支提交；此次实机运行是临时验证，不代表已合并或长期部署。真实暗夜、硬件方向的一像素中心影响、长时间并发解算和主相机长曝光仍需专项验收。

Code is committed on a dedicated short-lived branch. Temporary board validation is not a merge or permanent deployment. Dark-sky behavior, hardware-orientation center shifts, sustained concurrent solving and main-camera long exposures still require field acceptance.
