# 相机运行层与验收边界 / Camera Runtime and Acceptance Boundaries

Core、Dev、分析与预览共用同一个相机运行实例。设备生命周期、占用规则、帧与编码、任务与执行器已有明确所有者；相机 Domain 不再导入 HTTP 或绕经 Web Debug 读取产品数据。Core v1 冻结基线保持不变，相关 PR 继续 Draft，合并由维护者另行决定。

Core, Dev, analysis and preview share one camera runtime. Device lifetime, ownership, frames/encoding and task/executor resources have explicit owners. Camera Domain no longer imports HTTP or delegates product reads through Web Debug. Core v1 remains frozen; the PR stays draft pending a maintainer's decision.

## 职责与依赖 / Responsibilities and Dependencies

| 所有者 / Owner | 职责 / Responsibility | 约束 / Constraint |
|---|---|---|
| `application/camera.py` | 绑定一个 runtime，协调分析、录像和采集终止 / Bind one runtime and coordinate terminal consumer/capture shutdown | 未使用的 runtime 不在退出时初始化硬件 / No hardware initialization for an unused runtime at exit |
| `application/camera_manager.py` | 唯一设备句柄、生命周期锁、启停/重配/故障隔离、空闲关闭 / Sole device handle, lifetime lock, start/stop/reconfiguration/quarantine and idle close | 只有它能决定释放设备，流水线异常经回调取得生命周期锁 / Only the coordinator releases hardware; pipeline faults acquire its lifetime lock |
| `domain/camera/ownership.py` | 预览/分析/录像计数、限额租约、续期/到期/释放 / Consumer counts and bounded lease acquire/renew/expire/release | 占用不等于设备或曝光状态；普通 stop 尊重分析、录像和操作占用 / Ownership is separate from device/readiness state and protects ordinary stop |
| `application/camera_frames.py` | 唯一共享帧身份、缓存、时域屏障、抓帧流水线、JPEG 质量变体及编码指标 / Shared identity/cache, epoch barrier, capture pipeline, JPEG variants and metrics | 编码结果与原采集身份绑定，不因质量变体额外抓 RAW；保留有界缓存 / Bind encodes to capture identity, never capture extra RAW for variants, bound caches |
| `application/camera_resources.py` | 后台任务、原生工作完成回执、抓帧及编码线程池 / Background tasks, native completion receipts and both worker pools | 请求取消不取消原生完成证据，已运行线程不能靠 cancel 强制结束 / Request cancellation preserves receipts; running native threads cannot be forcibly cancelled |
| `platform/adapters/camera_config.py` | 配置到后端参数的映射 / Settings-to-backend mapping | 保留默认值、运行覆盖顺序和驱动配置 / Preserve defaults, override precedence and driver configuration |
| `domain/camera/media.py` | Core/Dev 共用的只读目录和侧车元数据 / Shared read-only media catalog and sidecar metadata | 目录可注入；文件创建、删除和预设持久化继续由 Dev 负责 / Injectable directory; Dev retains file mutations and preset persistence |
| `web/camera_http.py`, `web/camera_streaming.py` | HTTP 状态/头、预览节流、MJPEG 响应及连接收尾 / HTTP status/headers, throttling, MJPEG response and connection cleanup | HTTP 消费者释放运行层占用，不持有第二个相机 / HTTP consumers release runtime ownership; no second camera |

`CameraControlService` 继续持有共享参数事务、调焦快照和录像任务/锁。`CaptureReadiness` 独立回答曝光是否可供分析；不得用一个设备状态枚举掩盖占用、曝光和关闭隔离的差别。帧与编码保留为同一流水线组件，因为帧身份、质量变体与缓存淘汰必须一致。

Shared controls retain parameter transactions, focus state and the recording task/lock. CaptureReadiness independently governs analysis readiness. Device state must not collapse ownership, exposure and quarantine into one enum. Frames and encoding stay in one pipeline because identity, variants and cache eviction must agree.

```text
Core / Dev routes
  -> CameraDomainService / CameraControlService
     -> CameraRuntime(control, capture)
        -> CameraManager: device handle and lifetime lock
           -> CameraOwnership: consumers and operation leases
           -> CameraFramePipeline: frames, readiness evidence and encodes
           -> CameraResources: tracked tasks and native workers

HTTP preview / MJPEG -> Web adapters -> neutral runtime
Core / Dev media reads -> CameraMediaCatalog
```

旧 `web/camera_shared.py` 保留类、帧类型和单例的兼容转发。内部 `domain.camera.streaming` 与反向 Debug 适配器已移除，仓库内调用方统一使用 Web HTTP 实现；外部 REST 路径未删除。局部 runtime、媒体目录及底层设备回调均可注入，不引入第二套生产单例或 DI 框架。

The old Web camera module still forwards class/frame/singleton identity. Internal Domain streaming and the reverse Debug adapter are removed; in-repo callers use the Web HTTP implementation. No REST route is removed. Local runtimes, media directories and device callbacks support injection without a second production singleton or DI framework.

## 生命周期不变量 / Lifetime Invariants

- 同一进程只有一个活动设备所有者。启动在生命周期锁内确认有效帧；新消费者不能穿过已经开始的空闲关闭。/ One active device owner; startup verifies frames under the lifetime lock and new consumers wait for an active idle close.
- 普通 `stop()` 保留占用检查、驱动顺序和既有预算，完成后可以重新启动；不销毁线程池。/ Ordinary stop preserves ownership checks, driver ordering and budgets, permits restart and keeps worker pools reusable.
- `begin_shutdown()` 拒绝新工作、撤销操作租约并取消计时器。已经开始原生释放的空闲任务须先完成。/ Terminal fencing rejects acquisition, revokes leases and cancels timers; an idle task already releasing native resources must finish.
- 进程退出顺序为分析、录像、采集。前一阶段失败仍继续后续清理；`CameraManager.shutdown()` 默认预算 8 秒。调用方取消不打断共享终止任务，重复关闭等待同一结果。/ Exit stops analysis, recording and capture with independent bounds; manager shutdown defaults to eight seconds. Caller cancellation does not interrupt shared terminal cleanup, and repeated callers observe one result.
- 先排空抓帧、RAW 直读、时域重置、预览/变体/非 JPEG 编码，再关闭编码器和设备，最后封闭线程池。/ Drain capture, direct RAW reads, temporal reset and all encodes before closing encoder/device resources and sealing pools.
- 原生停止/关闭失败、超时或取消等待后保留并隔离原句柄，不以逻辑状态宣称硬件已经释放。`shutdown(wait=False)` 不会终止已运行原生线程。/ Failed, timed-out or cancelled native closure retains and quarantines the handle; logical state and nonblocking executor shutdown do not establish release.
- 正式日志 `camera_runtime_shutdown released=... pending_workers=... pending_tasks=...` 是关闭回执。`released=False` 要求人工检查或重启服务；不能发布为正常释放。/ Product logs report release and outstanding work; an incomplete receipt requires manual recovery, not a successful-release claim.
- 启动中途失败也走清理路径；录像 writer 最终释放。普通 Dev 停录继续写侧车，进程终止不新增侧车持久化行为。/ Startup failures clean up and recording writers finalize. Normal Dev stop writes sidecars; terminal shutdown adds no persistence behavior.

## 回归与板上验收 / Regression and Board Acceptance

公开契约保留 14 条 Core v1 路径与 18 个 schema；冻结 fixture 不随内部拆分重录。状态码、owner/session、忙碌拒绝、精确帧 404/409、standalone/subordinate 注册规则保持一致。

The reviewed fixture keeps 14 Core v1 paths and 18 schemas. Internal refactoring does not regenerate it or change status codes, ownership, busy refusal, exact-frame errors or role-specific registration.

| 保护内容 / Protection | 测试 / Tests |
|---|---|
| 控制锁交错、关闭取消、失败隔离 / Lock interleaving, cancellation, quarantine | `test_camera_manager_health.py`, `test_camera_runtime_shutdown.py` |
| 抓帧身份、时域屏障、预取与编码缓存 / Capture identity, epochs, prefetch and encoding caches | `test_raw_frame_freshness.py`, `test_shared_preview_stream_encoding.py` |
| 租约限额、过期不释放其他消费者、媒体读一致 / Lease bounds, independent consumers and shared media reads | `test_camera_runtime_components.py`, `test_capture_readiness.py` |
| 禁止 Web/HTTP 导入后的默认组合与领域服务 / Neutral composition and Domain without Web/HTTP imports | `test_camera_runtime_binding.py`, `test_camera_control_service.py` |
| MJPEG 断连、淘汰、清理与共享实例 / MJPEG disconnect, eviction, cleanup and shared runtime | `test_domain_camera_streaming.py`, `test_mjpeg_stream_limiter.py` |
| Core 契约与分析归属 / Core contract and analysis ownership | `test_core_v1_schema.py`, `test_core_contract_api.py`, `test_analysis_session_ownership.py` |

本地先做定向回归，再运行完整单元/集成测试、Black、Ruff、相机运行模块的阻断式 MyPy 和 wheel/sdist 检查。内部组件可以分提交审阅；集中板上验收必须对应最终提交、归档哈希及实际导入路径，结果记录在 PR。

Run targeted regressions, then full unit/integration suites, formatting, lint, focused blocking typing and distribution checks. Reviewable commits may separate internals, but board acceptance must identify the final commit, archive hash and actual import path; record results in the PR.

现有设备的集中验收包括反复启停、长曝光下停止/恢复、多客户端预览/分析/录像竞争、断连、租约到期、带占用退出和有界持续负载。临时配置与媒体目录必须与常驻服务隔离，监督进程最终恢复原服务，独立复核健康、配置哈希、消费者归零和相机休眠。

On the available device, exercise repeated restart, long-exposure stop/recovery, preview/analysis/recording contention, disconnect, lease expiry, active-consumer exit and a bounded load run. Isolate temporary configuration/media and independently verify restoration, settings, health, zero consumers and idle release.

有限时长的 V4L2 验收不证明通宵稳定性、Picamera2 或真实星空精度；受控单元测试也不等于真实原生驱动故障恢复。硬件或场景不足的项目单列，参见[发布冒烟与人工验收](core-api-smoke.md)。安全、前端和驱动算法不属于本阶段修改范围，项目授权保持 CC BY-NC-SA 4.0，第三方条款保留。

Bounded V4L2 acceptance does not establish overnight stability, Picamera2 behavior or real-sky accuracy; controlled unit stalls are not hardware fault recovery. List unavailable hardware/scene checks separately in the release checklist. Security, frontend and driver algorithms are outside this milestone; licensing remains CC BY-NC-SA 4.0 with third-party terms intact.
