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

Real-sky acceptance is deferred because of weather. The bounded board checks below do not replace physical-axis or endurance acceptance; keep the paired PRs in Draft. Full southern search/preposition acceptance remains with the southern-workflow PR.
天气原因暂缓真实星空验收；下述板端检查不能替代实机极轴与耐久验收，配套 PR 保持草稿。完整南半球搜索和预定位仍由南半球流程 PR 验收。

## Native board acceptance / 原生板端验收

Validated the application code at OGScope `17d79f4` and ZenitAPA `a2ea91d` on a Raspberry Pi Compute Module 0, aarch64 Python 3.12.12. Both complete packages were selected with boot-scoped service overrides on writable data; the read-only system image was preserved.
在 CM0、aarch64 Python 3.12.12 上验证上述配套代码；完整包通过数据分区与本次启动有效的服务覆盖运行，保留只读系统镜像。

- Both services became healthy; the delegated sensor socket responded; the new current-pole capability and consumer default were active. Four live Core contract tests passed. Wrong-owner stop was rejected, changing pole within a session returned HTTP 409, and physical daylight capture returned `TOO_FEW` with exposure UTC corrected using the trusted session reference.
  双服务健康、传感器 UDS 正常，新能力与默认目标生效；4 项真实 Core 契约通过。错误调用者不能停止会话，运行中换极返回 409，日间物理采集如实返回星点不足并正确换算 UTC。
- Twenty complete-model rendered fields passed native Tetra matching, Core result construction, current-pole fitting and the native ZenitAPA consumer/planner. Maximum pose/ALT/AZ errors were 1.483/1.264/1.860 arcsec. Five legacy mean-date controls retained the expected model mismatch. This image replay used isolated processes, not the physical camera or a running motor loop.
  20 组完整模型星图通过原生板解、Core 结果构造、目标拟合及消费规划，最大姿态/ALT/AZ 误差分别为 1.483/1.264/1.860 角秒；5 组旧平历元对照保留模型差异。图像回放使用隔离进程，不是物理相机或真实电机闭环。
- Pure current-pole calculation, excluding plate solving and transport: 50 timed samples per mode, median 22.0 ms with refraction off and 25.5 ms with standard refraction; p95 25.8/35.0 ms. These measurements are not a long-duration throughput guarantee.
  单独天文计算每模式 50 次，关闭/标准折射中位耗时 22.0/25.5 毫秒，p95 为 25.8/35.0 毫秒；不包含板解和传输，不代表长时间吞吐保证。

The image lacked `pyerfa`; acceptance used the lockfile-verified aarch64 2.0.1.5 wheel in an isolated dependency directory. Formal BSP/OTA packaging must include it. Existing BSP NumPy 1.26.4 is below the project's declared `>=2,<3` range; SciPy 1.14.1 and Pydantic 2.7.4 satisfy their declared ranges. Native compatibility here does not certify a lockfile-equivalent release. The image also lacked `curl`, making `doctor.sh` report HTTP failures; independent HTTP and UDS checks passed. These are packaging follow-ups, not reasons to disable target validity checks.
镜像缺少 `pyerfa`，本次在隔离依赖目录使用与锁文件散列一致的 ARM 2.0.1.5 wheel，正式 BSP/OTA 必须纳入。原镜像 NumPy 1.26.4 低于项目声明的 `>=2,<3`；SciPy 1.14.1 和 Pydantic 2.7.4 符合各自声明范围。本次原生兼容结果不能替代锁定依赖发布验收。镜像还缺少 `curl`，导致 doctor 脚本误报 HTTP 失败；独立 HTTP/UDS 验证通过。这些打包问题不能通过关闭目标有效性检查绕过。

After acceptance, both services were restored to their original source/static selectors and became healthy. Temporary service overrides were removed; persistent environment and calibration/settings hashes were unchanged. ALT/AZ positions were unchanged and no motor command, controller firmware update or system-clock adjustment was performed.
验收后双服务已恢复原代码及静态资源选择并通过健康检查，临时服务覆盖已移除，持久环境与校准/设置文件散列未变。ALT/AZ 位置未变，未执行电机命令、控制器固件升级或系统时钟调整。
