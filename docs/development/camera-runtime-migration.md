# 相机运行边界迁移准备 / Camera Runtime Migration Preparation

Core 与 Dev 通过中性运行端口共用一个默认实例，Core v1 保持重构冻结基线。共享启停、状态、参数重配和调焦恢复现已由 `application/camera_control.py` 持有；Web Debug 的旧入口只转发这些操作。采集管理器现位于 `application/camera_manager.py`，旧 Web 导入仅转发同一个实例；普通停机仍可重启，新增终止关闭统一收回后台任务和执行器。相关 PR 保持 Draft，分提交记录验证结果。

Core and Dev share neutral runtime ports under the frozen Core v1 contract. `application/camera_control.py` now owns shared start/stop, status, reconfiguration and focus restoration; legacy Web Debug entries forward these operations. The capture manager now lives in `application/camera_manager.py`; the old Web import forwards the same instance. Ordinary stop remains reusable, while terminal shutdown drains owned tasks and executors. The PR stays draft, with validation recorded per commit.

回归复现表明：原快速路径只检查帧新鲜度，关闭持有控制锁期间仍可能提前放行分析。现在快速路径要求控制锁空闲；预览必须取得控制锁后重新检查句柄，覆盖锁刚释放但关闭请求仍排队的窗口。关闭等待被取消时，原生线程可能仍在工作，因此保留并隔离原句柄，拒绝新的相机获取。自动空闲关闭、显式关闭、排队预览和原生 stop/close 等待取消均有确定性交错测试，驱动配置与超时预算保持不变。

Regressions reproduce the former freshness-only fast path accepting analysis while closure owns the control lock. The fast path requires an unlocked controller, and preview rechecks the handle after acquiring control, including when a closer is already queued on an unlocked lock. Cancelling a close waiter does not stop native workers, so the original handle is retained and quarantined against new acquisition. Deterministic interleaving tests cover idle/explicit closure, queued preview and cancellation during native stop/close without changing driver configuration or timeout budgets.

## 现有行为基线 / Existing Behavior Baseline

| 不变量 / Invariant | 当前证据 / Existing regression evidence |
|---|---|
| 同一进程只保留一个活动硬件所有者；启动须确认有效帧 / One hardware owner; startup confirms a frame | `test_camera_manager_health.py` |
| 启动失败安全释放后可再次创建；停止失败、超时或等待取消时保留原句柄并禁止重新获取 / Retry only after safe failed-start release; quarantine failed, timed-out or cancelled stops | `test_camera_manager_health.py` |
| 空闲关闭一旦开始释放硬件，新消费者等待完成；不能取消到一半 / New consumers wait for an idle close already releasing hardware | `test_camera_manager_health.py` |
| 生命周期、曝光准备、资源占用分开；重启不沿用旧就绪证据 / Separate lifetime, readiness and ownership; reset readiness after sleep | `test_capture_readiness.py` |
| 曝光准备有预算，准备期间不消耗解算次数 / Bounded readiness without spending solve attempts | `test_capture_readiness.py` |
| 分析、录像、任务占用阻止普通停止；硬件平面不能绕过 / Analysis, recording and task leases guard ordinary stop, including hardware-plane calls | `test_capture_readiness.py` |
| 不同 owner 不得更改或停止他人会话；旧清理不能写入新会话 / Ownership checks and stale-cleanup isolation | `test_analysis_session_ownership.py` |
| JPEG 与结果按 session/frame 配对；共享预览限制缓存与连接 / Exact frame identity with bounded shared previews | `test_core_contract_api.py`, `test_shared_preview_stream_encoding.py`, `test_domain_camera_streaming.py` |

这些自动回归保护每次迁移。接口阶段 `e3616e7` 已完成 V4L2 三轮板上基线（含临时进程重启、跨入口占用和原服务恢复），不代表后续提交或完整发布验收；当前提交证据见 PR。原生驱动阻塞、长曝光与持续 CMA 等仍须经[发布冒烟与人工验收](core-api-smoke.md)验证。

Automated regressions protect each migration. Interface-stage commit `e3616e7` passed three V4L2 baseline cycles including a temporary-process restart, cross-entry ownership and restoration. That evidence does not validate later commits or full release acceptance; see the PR for current evidence. Native stalls, long exposures and sustained CMA use remain manual acceptance items.

## 已完成的接口与组合点 / Implemented Ports and Composition

- `domain/camera/runtime.py` 定义 `CameraControl`、`CameraCapture` 和不可变的 `CameraRuntime` 绑定；共享帧值对象 `SharedFrame` 也位于这里，旧 Web 导入继续可用。端口声明不导入 Web 或具体驱动。/ Neutral ports and the shared frame value live in Domain; the old frame import remains compatible.
- `application/camera.py` 线程安全地延迟绑定一次默认 runtime；获取接口不打开相机。Core/Dev、实时分析、预览、硬件平面和应用启停均从该组合入口取得同一采集对象。/ Composition binds one default runtime without starting hardware and shares capture across every consumer.
- `application/camera_control.py` 实现 `CameraControl`，仅依赖注入的采集端口和分析占用查询；不导入 Web、FastAPI 或具体驱动。状态读取、启停、帧读取、参数事务和调焦恢复均可独立运行。/ Neutral controls depend only on capture and an injected analysis-busy query, without Web, FastAPI or driver imports.
- `platform/adapters/camera_runtime.py` 只将既有 `CameraManager` 与中性控制绑定。控制端持有调焦快照/锁和录像状态，录像任务和锁也由控制端持有，Dev 仍管理文件及侧车元数据；没有创建第二套相机所有者。/ Composition binds the existing manager to neutral controls. Focus state/locks and recording status belong to that instance; controls also own the recording task and lock, while Dev manages files and sidecar metadata.
- 预览端口返回帧值及状态码，既有 Domain 门面负责 HTTP 状态、缓存策略和身份头；Web 旧方法保持转发。Dev 专用拍摄、录像文件、预设及配置持久化仍未迁移，Domain 的这些开发能力仍经适配器加载旧服务。/ Preview ports return frame values and status codes; the existing facade preserves HTTP headers and status. Dev capture files, recording metadata, presets and persistence still use the legacy adapter.
- `CameraDomainService(runtime=...)`、`CoreContractService(camera=..., hardware_client=...)` 和 `RealtimeSolveService(capture=...)` 支持局部测试替身。注入控制端口与采集端口必须代表同一设备；测试可并存两组独立状态，不需要替换生产单例或引入 DI 框架。/ Constructors support isolated test collaborators; injected control and capture must represent the same device.
- `reset_temporal_history` 经注入的采集端口执行，保留 develop 的帧身份屏障；即使驱动没有降噪钩子，也会失效缓存及在途旧帧。/ Temporal reset uses the injected capture barrier and preserves upstream invalidation even for drivers without a temporal-NR hook.
- [Core v1 冻结基线](../contracts/core-v1-freeze.md)覆盖公开 schema、两种角色、关键失败语义及跨入口占用。新端口的类型检查在 CI 中阻断失败，项目其余 MyPy 门禁保持原状。/ Schema and behavioral baselines protect compatibility; new ports have a blocking type check while the existing project-wide MyPy policy is unchanged.

```text
Core / Dev / camera domain
  -> application.camera.get_camera_runtime()
     -> CameraRuntime(control, capture)
        -> CameraControlService(capture, analysis_running)
        -> CameraManager (application.camera_manager)
```

## 分阶段迁移方案 / Migration Stages

1. **接口与注入点已完成。** 公开契约基线、控制/采集端口、默认组合和局部注入已接入；接口阶段的 V4L2 基线已记录。/ Contract baselines, ports, composition and injection are implemented, with the interface-stage V4L2 baseline recorded.
2. **共享控制实现已迁出。** Core/Domain 与 Dev 调用同一中性实现，旧 Web 方法兼容转发。保留原参数事务、10 秒重配预算、帧率回读重试和调焦恢复顺序；共享预览仍复用同一帧身份。录制文件任务、预设及持久化继续留在 Dev。/ Shared controls now have a neutral owner. Legacy forwarders preserve transactions, 10-second reconfiguration budgets, FPS readback retry, focus restoration and shared frame identity. Recording files/tasks, presets and persistence remain in Dev.
3. **管理器迁移与终止关闭已实现。** Application 持有管理器及共享生命周期入口，集中管理预热、空闲/租约计时器、抓帧、录像和编码关闭；原导入保留转发。原生 I/O 超时后保留句柄并隔离，不能宣称已释放硬件。/ Application now owns the manager and shared lifecycle entry, draining warm-up, idle/lease timers, capture, recording and encoding. Legacy imports forward; native timeouts retain and quarantine the handle without claiming release.
4. **按修改原因拆分。** 再分别拆共享帧/编码、设备生命周期、占用规则；逐项证明行为等价后移除兼容导入。曝光准备继续独立，禁止用单个枚举掩盖多个状态维度。/ Split frame/encoding, lifecycle and ownership responsibilities after behavior is protected; retain separate readiness and remove forwarding only after equivalence checks.

目标生命周期转换可以显式记录为 closed → opening → running → closing → closed，以及故障隔离分支；这是待设计模型，不是当前已实现的状态机。`sleeping/active/warm_idle` 继续表达占用与热驻留；`CaptureReadiness` 继续回答是否可开始分析。

An explicit closed/opening/running/closing lifecycle with quarantined failure is a proposed model, not current implementation. Existing sleeping/active/warm_idle describe ownership and warm retention; CaptureReadiness independently governs analysis readiness.

## 普通停机与进程退出 / Reusable Stop and Process Exit

- `stop()` 保留原普通停机/占用检查、驱动顺序和预算，后续仍可重新启动；它不会销毁线程池。`begin_shutdown()` 先关闭获取入口，撤销操作租约并取消计时器；已经开始原生释放的空闲任务等待完成。/ Ordinary stop preserves ownership checks, driver ordering and budgets and allows reuse. Terminal fencing rejects new acquisition, clears leases and cancels timers while joining an idle closure already releasing native resources.
- `shutdown_camera_runtime()` 顺序终止实时分析、录像及采集端。每阶段都有预算，前一阶段失败仍继续清理。调用方取消不会中断共享关闭任务；重复关闭等待同一结果。未创建 runtime 的退出不会初始化硬件。/ The shared exit coordinator stops analysis, recording and capture with independent bounds, continues after errors, survives caller cancellation and reuses one shutdown result. Exiting an unused runtime does not construct hardware.
- `CameraManager.shutdown()` 默认总预算 8 秒，跟踪预热、后台抓帧、JPEG 变体、RAW 直读、时间域重置和非 JPEG 编码；原生工作的完成回执不随请求取消。先排空工作，再关闭编码器和相机，最后封闭两个专用线程池。/ The manager has an eight-second terminal budget. It tracks warm-up, preview, JPEG variants, direct RAW reads, temporal reset and non-JPEG encodes independently of request cancellation, drains work before native closure, then seals both pools.
- 超时或失败保留原句柄、重启要求及未完成工作；拒绝再次获取，也不在事件循环中等待卡住的原生线程。`shutdown(wait=False)` 只禁止新提交，不能终止已运行的原生线程；`camera_runtime_shutdown released=False` 明确表示未确认释放。/ Failures quarantine the original handle and reject reacquisition. Nonblocking executor shutdown cannot terminate running native work; `released=False` explicitly reports unconfirmed release.
- 应用启动中途失败也进入同一清理路径；录像任务最终释放 writer。Dev 的正常停止仍负责录像侧车，进程终止不会新增侧车持久化行为。Core v1 的路径、字段和帧身份不变。/ Startup failures use the same cleanup path and recording finalizers release the writer. Dev's ordinary stop still writes sidecars; process exit adds no sidecar persistence behavior. Core v1 paths, fields and frame identity stay unchanged.

确定性测试见 `test_camera_runtime_shutdown.py`，覆盖取消等待、原生读/编码仍在执行、迟到预热句柄、空闲关闭交错、重复关闭、失败隔离及应用启动异常。/ Deterministic regressions cover cancelled waiters, active native reads/encodes, late warm-up handles, idle-close interleaving, repeated closure, quarantine and startup failure.

## 每一步的验收条件 / Acceptance at Each Stage

- Core v1 路径、字段、忙碌/停止语义、精确帧身份与两种运行角色保持兼容；同步核对 [API 清单](../contracts/api-inventory.md)。/ Preserve Core paths, fields, busy/stop behavior, frame identity and both roles; recheck the inventory.
- 定向生命周期/所有权测试通过，再运行完整单元测试、Black、Ruff、wheel/sdist 授权检查；涉及界面时再构建前端。/ Pass targeted tests, then unit suite, formatting, lint and distribution-license checks; build UI if touched.
- Core、相机 Domain 和 Application 不得直接导入 Web 管理器或 Debug 控制实现。测试禁止加载 Web API/FastAPI 后仍能组合控制实例并执行状态/启停，同时保护实际控制实现的 Core/Dev 占用、失败参数写入和调焦隔离。默认组合在禁止所有 Web/FastAPI 导入时仍可运行。/ Import and behavioral checks protect the neutral owner, real Core/Dev control sharing, failed overrides and isolated focus state. Default composition also runs with all Web/FastAPI imports forbidden.
- 板上重复启停、长曝光、竞争、服务重启和持续运行验收通过后，维护者才能决定合并。不同后端的结果单独记录。/ Board acceptance precedes a merge decision; record each backend independently.

本阶段不调整鉴权、CORS、Dev 默认访问策略、现有网络接口或前端框架，不替换设备常驻版本，临时板上验收须记录对应提交并恢复原服务。许可证已确定统一为 CC BY-NC-SA 4.0；第三方许可证保留原条款。

This phase leaves authentication, CORS, Dev locality defaults, network routes and frontend frameworks unchanged and does not replace the installed version. Authorized temporary board checks must record the tested commit and restore the installed service. Project licensing is CC BY-NC-SA 4.0; third-party terms remain intact.
