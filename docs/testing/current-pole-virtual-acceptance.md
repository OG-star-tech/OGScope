# 当前极轴图像闭环验收 / Current-pole image-loop acceptance

The optional integration suite exercises rendered catalogue pixels through real Tetra matching, OGScope astronomy and Core REST routes, the actual ZenitAPA adapter, alignment state machine and simulated mount dynamics. Every new pose is rendered again; expected pointing errors are never injected as solver results.
可选集成测试从星库像素进入真实 Tetra 板解、OGScope 天文转换与 Core API、ZenitAPA 适配层、生产对准状态机和底座运动模型；每次新姿态重新渲染，不向解算器注入预制误差。

## Reproduce / 复现

Use the paired ZenitAPA current-pole checkout and the existing sky-simulator checkout. Install Astropy in the test environment only (validated with 8.0.2); it is not a product dependency. Supply a compatible Tetra J2000 database explicitly. No board, camera service or motor is contacted.
使用配套 ZenitAPA 当前极轴检出和现有 sky-simulator 检出，仅在测试环境安装 Astropy（本轮使用 8.0.2），并显式指定兼容的 Tetra J2000 星库；不连接开发板、相机服务或电机。

From the OGScope checkout / 在 OGScope 检出运行：

```sh
export PYTHONPATH="$PWD:$ZENITAPA_CHECKOUT:$SKY_SIMULATOR_CHECKOUT"
export OGSCOPE_TEST_STAR_DATABASE="$TETRA_DATABASE"
python -m pytest tests/integration/test_current_pole_closed_loop.py --no-cov -s
```

Without the optional checkouts, dependency or database, these tests skip explicitly. The ordinary unit suite remains self-contained.
缺少可选检出、依赖或星库时明确跳过；普通单元测试保持独立。

## Coverage and results / 范围与结果

- Three successful alignments: rolls 0°, 180° and 37°, refraction off/standard, and a board clock one hour ahead. Starting near ALT 43° / AZ 3° at latitude 40°, each uses newly rendered verification frames and finishes within 0.01 arcmin of the simulated physical pole.
  三组成功对准覆盖旋转角、折射开关和板端快一小时；初始 ALT 43° / AZ 3°、纬度 40°，复核重新生成图像，理想模型最终误差小于 0.01 角分。
- Cancellation during motion, blank images, no-frame timeout, system-clock steps and expired trusted UTC terminate with analysis stopped and neither motor moving. Clock/UTC failures issue no motor command. No-match and timeout retain the existing bounded search behavior.
  运动中取消、空图、无帧超时、系统校时跳变及可信 UTC 过期均退出并清理分析与运动；时间失效不发运动指令，无匹配和超时保留有界搜索。
- PoleGuard starts from the real successful session snapshot, detects Polaris in rendered images and measures the aligned state. A simulated six-arcminute disturbance is confirmed by two separately solved frames before exactly one realignment request. Expired UTC disables the guard before acquiring another frame.
  守护读取真实成功状态快照并确认图像中的北极星；施加 6 角分扰动后，两帧独立板解确认才请求一次重对准，UTC 过期则在再次采图前关闭。

The test exposed a consumer snapshot omission: target policy, pole and astronomy provenance were set internally but lost by the public snapshot copy, preventing PoleGuard from enabling after success. The paired ZenitAPA fix retains a deep copy of those fields, with a standalone regression.
测试发现消费端公开快照漏传内部天文策略、半球和来源，导致成功后无法开启守护；配套修复深复制这些字段，并补独立回归。

## Limits / 限制

Astropy ICRS→AltAz provides the forward projection while OGScope fits transformed matched stars; both share ERFA standards. Ideal synthetic sub-arcsecond residuals do not establish physical accuracy. Camera acquisition/preparation, leases, real scheduling, network latency, lens distortion and mechanical error are outside this test. The guard's final realignment callback is recorded, not a second alignment run.
正向投影和产品姿态拟合采用不同路径，但共享 ERFA 底层；理想残差不代表实机精度。真实采集、曝光准备、租约、调度、网络、镜头畸变及机械误差不在此测试内；守护最终重对准回调仅记录请求，未再次运行对准。

Real-sky acceptance is deferred because of weather. Board runtime/health acceptance remains separate; keep the paired PRs in Draft until their required acceptance is complete. Full southern search/preposition acceptance remains with the southern-workflow PR.
天气原因暂缓真实星空验收；板端运行与健康检查独立进行，配套 PR 保持草稿。完整南半球搜索和预定位仍由南半球流程 PR 验收。
