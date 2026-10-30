# 相机运行边界迁移准备 / Camera Runtime Migration Preparation

当前产品相机能力仍经过 Domain → Debug adapter → Web Debug service，共享管理器也位于 Web。目标是在保留既有硬件保护的前提下，让 Core 与 Dev 共用中性运行服务。本阶段建立验证基线，并修复新消费者误用正在关闭的相机句柄的竞态，尚未迁移实现；相关 PR 暂不合并。

Product camera behavior currently traverses Domain, a debug adapter and Web Debug services, while the shared manager lives under Web. The target is a neutral runtime shared by Core and Dev with existing hardware protections preserved. This phase establishes a validation baseline and fixes a new consumer reusing a camera handle during closure. Runtime relocation is not implemented; the PR is held as draft.

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

## 分阶段迁移方案（待实施）/ Proposed Stages (Not Implemented)

1. **抽取注入点。** 定义启动、停止、状态、消费者、租约、恢复诊断的窄接口；应用组合层提供默认实例，测试传入替身。保留单设备唯一所有者，避免引入通用 DI 框架。/ Define a narrow runtime interface and composition-level default; allow test substitutes while retaining one device owner.
2. **中性服务取得行为所有权。** 逐项迁出 Debug 服务中产品所需的生命周期和控制逻辑；Core/Domain 直接依赖中性接口，Dev 成为适配调用方。迁移中不修改线程、锁、超时、硬件参数与恢复策略；兼容转发复用同一实例。/ Move shared product behavior out of Debug incrementally, preserving threading, locks, budgets, hardware settings and recovery. Forwarders share one instance.
3. **迁移管理器并明确关闭。** 根据已有依赖将运行管理器移到中性位置，集中管理启动任务、租约、抓帧和编码执行器的关闭；原导入保留临时转发。原生 I/O 超时后不能凭逻辑状态宣称已释放硬件。/ Relocate the manager and centralize task/executor shutdown. Keep temporary import forwarding; timed-out native I/O does not establish hardware release.
4. **按修改原因拆分。** 再分别拆共享帧/编码、设备生命周期、占用规则；逐项证明行为等价后移除兼容导入。曝光准备继续独立，禁止用单个枚举掩盖多个状态维度。/ Split frame/encoding, lifecycle and ownership responsibilities after behavior is protected; retain separate readiness and remove forwarding only after equivalence checks.

目标生命周期转换可以显式记录为 closed → opening → running → closing → closed，以及故障隔离分支；这是待设计模型，不是当前已实现的状态机。`sleeping/active/warm_idle` 继续表达占用与热驻留；`CaptureReadiness` 继续回答是否可开始分析。

An explicit closed/opening/running/closing lifecycle with quarantined failure is a proposed model, not current implementation. Existing sleeping/active/warm_idle describe ownership and warm retention; CaptureReadiness independently governs analysis readiness.

## 每一步的验收条件 / Acceptance at Each Stage

- Core v1 路径、字段、忙碌/停止语义、精确帧身份与两种运行角色保持兼容；同步核对 [API 清单](../contracts/api-inventory.md)。/ Preserve Core paths, fields, busy/stop behavior, frame identity and both roles; recheck the inventory.
- 定向生命周期/所有权测试通过，再运行完整单元测试、Black、Ruff、wheel/sdist 授权检查；涉及界面时再构建前端。/ Pass targeted tests, then unit suite, formatting, lint and distribution-license checks; build UI if touched.
- 代码层能证明 Core/Domain 不再导入 Web 实现；Core 与 Dev 必须连接同一运行实例。/ Verify dependency direction and that Core/Dev share one runtime instance.
- 板上重复启停、长曝光、竞争、服务重启和持续运行验收通过后，维护者才能决定合并。不同后端的结果单独记录。/ Board acceptance precedes a merge decision; record each backend independently.

本阶段不调整鉴权、CORS、Dev 默认访问策略、现有网络接口或前端框架，也不部署到设备。许可证已确定统一为 CC BY-NC-SA 4.0；第三方许可证保留原条款。

This phase leaves authentication, CORS, Dev locality defaults, network routes and frontend frameworks unchanged and does not deploy. Project licensing is CC BY-NC-SA 4.0; third-party terms remain intact.
