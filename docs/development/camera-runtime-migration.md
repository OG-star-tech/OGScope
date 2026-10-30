# 相机运行边界迁移准备 / Camera Runtime Migration Preparation

Core 与 Dev 现在通过中性运行端口共用一个默认实例，Core v1 已建立重构冻结基线。现有控制实现和管理器仍在 Web，由临时适配器绑定；本阶段完成接口与组合点，没有迁移硬件运行实现。关闭竞态保护继续保留，相关 PR 暂不合并，板上验收后续进行。

Core and Dev now share one default instance through neutral runtime ports, with a refactoring freeze baseline for Core v1. A temporary adapter still binds the existing Web control implementation and manager. This stage provides ports and composition, preserving close-race protections without relocating hardware runtime behavior. The PR remains draft; board acceptance is deferred.

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

这些是本地回归证据；真实设备上的驱动阻塞、CMA 与服务重启须经[发布冒烟与人工验收](core-api-smoke.md)验证。

These are local regressions. Driver stalls, CMA and service restart require board smoke plus manual acceptance.

## 已完成的接口与组合点 / Implemented Ports and Composition

- `domain/camera/runtime.py` 定义 `CameraControl`、`CameraCapture` 和不可变的 `CameraRuntime` 绑定；共享帧值对象 `SharedFrame` 也位于这里，旧 Web 导入继续可用。端口声明不导入 Web 或具体驱动。/ Neutral ports and the shared frame value live in Domain; the old frame import remains compatible.
- `application/camera.py` 线程安全地延迟绑定一次默认 runtime；获取接口不打开相机。Core/Dev、实时分析、预览、硬件平面和应用启停均从该组合入口取得同一采集对象。/ Composition binds one default runtime without starting hardware and shares capture across every consumer.
- `platform/adapters/camera_runtime.py` 是默认实现的过渡绑定点，复用已有 `CameraManager` 与 Web `DebugCameraService`，不创建第二个管理器。Debug 专用拍摄、录像、配置持久化与预览 HTTP 表示仍是迁移遗留，不声称 Web 已退出实现链。/ The bridge reuses the existing manager and control implementation; debug-only behavior and legacy preview responses remain for later migration.
- `CameraDomainService(runtime=...)`、`CoreContractService(camera=..., hardware_client=...)` 和 `RealtimeSolveService(capture=...)` 支持局部测试替身。注入控制端口与采集端口必须代表同一设备；测试可并存两组独立状态，不需要替换生产单例或引入 DI 框架。/ Constructors support isolated test collaborators; injected control and capture must represent the same device.
- [Core v1 冻结基线](../contracts/core-v1-freeze.md)覆盖公开 schema、两种角色、关键失败语义及跨入口占用。新端口的类型检查在 CI 中阻断失败，项目其余 MyPy 门禁保持原状。/ Schema and behavioral baselines protect compatibility; new ports have a blocking type check while the existing project-wide MyPy policy is unchanged.

```text
Core / Dev / camera domain
  -> application.camera.get_camera_runtime()
     -> CameraRuntime(control, capture)
        -> temporary adapter: existing Web control + existing CameraManager
```

## 分阶段迁移方案 / Migration Stages

1. **接口与注入点已完成。** 公开契约基线、控制/采集端口、默认组合和局部注入均已接入；仍需板上等价性验收。/ Contract baselines, ports, default composition and local injection are implemented; board equivalence remains unverified.
2. **中性服务取得行为所有权。** 逐项迁出 Debug 服务中产品所需的生命周期和控制逻辑；Core/Domain 直接依赖中性接口，Dev 成为适配调用方。迁移中不修改线程、锁、超时、硬件参数与恢复策略；兼容转发复用同一实例。/ Move shared product behavior out of Debug incrementally, preserving threading, locks, budgets, hardware settings and recovery. Forwarders share one instance.
3. **迁移管理器并明确关闭。** 根据已有依赖将运行管理器移到中性位置，集中管理启动任务、租约、抓帧和编码执行器的关闭；原导入保留临时转发。原生 I/O 超时后不能凭逻辑状态宣称已释放硬件。/ Relocate the manager and centralize task/executor shutdown. Keep temporary import forwarding; timed-out native I/O does not establish hardware release.
4. **按修改原因拆分。** 再分别拆共享帧/编码、设备生命周期、占用规则；逐项证明行为等价后移除兼容导入。曝光准备继续独立，禁止用单个枚举掩盖多个状态维度。/ Split frame/encoding, lifecycle and ownership responsibilities after behavior is protected; retain separate readiness and remove forwarding only after equivalence checks.

目标生命周期转换可以显式记录为 closed → opening → running → closing → closed，以及故障隔离分支；这是待设计模型，不是当前已实现的状态机。`sleeping/active/warm_idle` 继续表达占用与热驻留；`CaptureReadiness` 继续回答是否可开始分析。

An explicit closed/opening/running/closing lifecycle with quarantined failure is a proposed model, not current implementation. Existing sleeping/active/warm_idle describe ownership and warm retention; CaptureReadiness independently governs analysis readiness.

## 每一步的验收条件 / Acceptance at Each Stage

- Core v1 路径、字段、忙碌/停止语义、精确帧身份与两种运行角色保持兼容；同步核对 [API 清单](../contracts/api-inventory.md)。/ Preserve Core paths, fields, busy/stop behavior, frame identity and both roles; recheck the inventory.
- 定向生命周期/所有权测试通过，再运行完整单元测试、Black、Ruff、wheel/sdist 授权检查；涉及界面时再构建前端。/ Pass targeted tests, then unit suite, formatting, lint and distribution-license checks; build UI if touched.
- 当前阶段禁止 Core/相机 Domain 直接导入 Web 相机管理器或 Debug 控制实现，并验证共用实例；后续实现迁移须进一步移除临时适配器对 Web 的依赖。/ This stage guards direct imports and shared identity; later migration must remove the bridge's Web dependency as well.
- 板上重复启停、长曝光、竞争、服务重启和持续运行验收通过后，维护者才能决定合并。不同后端的结果单独记录。/ Board acceptance precedes a merge decision; record each backend independently.

本阶段不调整鉴权、CORS、Dev 默认访问策略、现有网络接口或前端框架，也不部署到设备。许可证已确定统一为 CC BY-NC-SA 4.0；第三方许可证保留原条款。

This phase leaves authentication, CORS, Dev locality defaults, network routes and frontend frameworks unchanged and does not deploy. Project licensing is CC BY-NC-SA 4.0; third-party terms remain intact.
