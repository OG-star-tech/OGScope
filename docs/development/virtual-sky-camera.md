# 虚拟天空相机 / Virtual sky camera

`virtual_sky` replaces capture with generated star images while keeping the actual extraction, solver, Core sessions, previews and exact-frame endpoint. It does not open a physical camera or fabricate solve results.

`virtual_sky` 用生成星图替换采集输入，保留真实提星、解算、Core 会话、预览和精确帧接口。它不访问物理相机，也不注入伪造板解。

## Select the development source / 选择开发图像源

Run a compatible `sky_simulator.virtual_eye` service on a reachable lab computer, then explicitly configure OGScope and restart its development instance:

先在局域网主机运行兼容的 `sky_simulator.virtual_eye`，再为 OGScope 开发实例显式配置并重启：

```sh
OGSCOPE_CAMERA_TYPE=virtual_sky
OGSCOPE_CAMERA_VIRTUAL_SKY_URL=http://LAB_HOST:8091
OGSCOPE_CAMERA_VIRTUAL_SKY_TIMEOUT_SEC=5
OGSCOPE_CAMERA_WIDTH=1280
OGSCOPE_CAMERA_HEIGHT=720
OGSCOPE_CAMERA_ROTATION=0
OGSCOPE_SHARED_PREVIEW_FPS=2
OGSCOPE_SOLVER_FULLSOLVE_INTERVAL_FRAMES=1
OGSCOPE_SIMULATION_MODE=false
```

The last two options keep every analyzed frame on the real full solver during experiments. Normal production defaults remain unchanged. Virtual images are already upright RGB888; sensor rotation and ISP tuning do not apply. Exposure and gain are not claimed as hardware controls.

最后两项用于实验时每帧真实完整解算；产品默认配置不变。虚拟图像已经是正向 RGB888，不应用传感器旋转或 ISP 参数，也不将曝光增益伪装为硬件控制。

Start/stop analysis and obtain results through the existing `/api/core/v1/*` contract. A developer image upload returns a separate result and does not populate a Core session.

通过既有 `/api/core/v1/*` 启停分析并获取结果。开发者单帧上传接口有独立结果，不会填充 Core 会话。

## Provenance and freshness / 来源与新鲜度

Each request supplies a random request ID, dimensions and the device's UTC observation time. The source must echo that identity and time, with a monotonically increasing frame ID inside a stream. A source restart uses a new stream ID. Missing, corrupt, repeated, oversized or mismatched frames raise a source error; no old image or physical fallback is returned.

每次请求携带随机请求 ID、尺寸及设备 UTC 观测时刻。服务必须回传一致的 ID/时刻，并在同一流内递增帧号；服务重启使用新流 ID。缺失、损坏、重复、过大或不匹配的图像均报告来源错误，不回传旧图，也不自动回退到物理相机。

Core results add `capture_source="virtual_sky"` and `virtual_frame`. Their `observation_time_utc` belongs to the actual pixels, independent of network completion and preview scheduling. A host clock may differ from the device clock; render for the requested observation time and keep host generation time separate. Consumers must check session/frame identity, new solve counts and `last_error`, because a source failure can retain the previous result for diagnosis.

Core 结果增加 `capture_source="virtual_sky"` 和 `virtual_frame`。`observation_time_utc` 与实际像素绑定，不受网络完成时间或预览抢帧影响。主机与设备时间可以不同；按请求时刻生成天空，并单独记录主机生成时间。来源失败时可能保留上次结果供诊断，消费方必须同时检查会话/帧身份、新解算计数及 `last_error`。

## Calibration boundary / 校准边界

Replacing the camera does not disable mount motion. Automatic alignment and mechanical calibration still send real controller commands unless a separate motion simulator is selected. Static camera/Core tests and virtual-pose math experiments need no motor movement. Keep synthetic calibration profiles in a separate lab location; never use synthetic tilt to overwrite the real accelerometer or compass calibration.

替换相机不会禁用底座运动。若未另行选择运动仿真器，自动对准和机械标定仍会发送真实控制器命令。静态相机/Core 测试、虚拟姿态数学实验无需电机运动。模拟校准档案应保存于独立实验目录，不能用虚拟倾斜覆盖真实加速度计或磁力计校准。

The source must declare its astrometric model. A fixed J2000 star image alone cannot validate local level. Local scenes require date conversion and a consistent site/time; refraction, aberration and nutation settings must be explicit. Matching a catalogue used by the renderer proves interface consistency, not real-sky or mechanical accuracy.

图像源必须声明天文模型。固定 J2000 星图本身不能验收当地水平；地平场景需要历元转换及一致的地点/时刻，折射、光行差和章动设置应明确。生成器与解算器共用星表时，匹配证明接口一致性，不证明真实夜空或机械精度。

## Restore physical capture / 恢复物理采集

Stop analysis before changing the source. Restore the previous camera environment/profile, remove the virtual development overlay and restart OGScope. Inspect `configured_backend` to confirm it is the intended physical driver. A failed virtual source must remain a visible failure until explicitly restored or reconfigured.

先停止分析，再恢复原相机环境/配置、移除虚拟开发覆盖并重启 OGScope。核对 `configured_backend` 已回到预期物理驱动。虚拟源失败应持续明确显示，直到显式恢复或重新配置。
