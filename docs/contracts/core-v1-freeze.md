# Core v1 重构冻结基线 / Core v1 Refactoring Freeze

相机运行接口迁移期间，现有调用方应观察到相同的 HTTP 契约与占用行为。基线在运行接口改造前从 PR #22 的 `af9b77a` 状态采集，覆盖全部 14 条 Core v1 路径与 18 个可达 schema；不依赖板上设备。

Camera runtime migration must preserve the HTTP contract and ownership behavior observed by existing callers. The baseline was captured before the interface refactor from PR #22 at `af9b77a`, covering all 14 Core v1 paths and 18 reachable schemas without a board.

## 自动保护 / Automated Protection

- `tests/fixtures/core-v1-contract.json` 固定方法、路径、参数位置、请求体必需性、字段类型/默认值/枚举/边界、必需响应键和公开响应媒体类型；忽略标题、文案和自动 operationId。/ The fixture freezes HTTP shape and schema constraints while ignoring prose and generated operation IDs.
- `test_core_v1_schema.py` 对比实际公开 schema，并分别检查包含或裁剪 Network/Dev 路由时的 Core 一致性。测试不会自动刷新基线。/ Compare the published schema and both role-specific route sets; tests never rewrite the baseline.
- `test_core_contract_api.py`、`test_analysis_session_ownership.py`、`test_capture_readiness.py` 保护启动就绪、忙碌拒绝、会话所有权、准备预算及精确帧身份。/ Behavioral regressions cover confirmed readiness, busy refusal, ownership, preparation budgets and exact frame identity.
- `test_camera_runtime_binding.py` 保护 Core/Dev 共享状态、跨入口租约、独立注入实例、并发首次绑定及中性接口的独立导入；默认中性控制仍绑定原采集管理器。/ Binding tests exercise the actual neutral controls with shared ownership, isolated injection and the original capture manager.
- `test_camera_control_service.py` 保护无 Web Debug/HTTP 依赖的组合与启停、调焦恢复与实例隔离、占用拒绝、重配失败不写覆盖参数、旧驱动 FPS 回读重试及预览 HTTP 兼容。/ Control tests cover independent composition, focus restoration/isolation, busy refusal, failed overrides, legacy FPS retry and preview HTTP compatibility.

## 必须保留的行为 / Required Behavior

| 边界 / Boundary | 保持的行为 / Preserved behavior |
|---|---|
| 分析启动 / Analysis start | 请求体必需，`{}` 有效；owner 可选，缺失时保留旧语义 / Body required, `{}` valid, owner optional with legacy semantics |
| 无效请求 / Invalid input | 请求体/Query 校验失败为 422；旋转仅 0/90/180/270 / Validation returns 422; rotation accepts right angles only |
| 相机启动 / Camera start | `success` 必须同时满足命令成功及 connected/streaming 就绪；保留 `applied` 结构 / Success requires confirmed readiness and preserves applied fields |
| 相机停止 / Camera stop | 占用拒绝为 HTTP 200、`success=false`、`applied.busy=true`；拒绝后不得下发硬件平面停止 / Busy refusal preserves its envelope and prevents a plane-stop bypass |
| 租约 / Lease | TTL 10–120 秒；空 ID 获取、已知 ID 续期、重复释放幂等；不自动启动相机 / Preserve bounded lease semantics without auto-start |
| 状态 / Status | 保留 lifecycle 的阶段、四类消费者计数、空闲时限与独立 analysis_readiness；读取不唤醒硬件 / Preserve lifecycle telemetry without waking capture |
| 结果与图像 / Results and frames | session/frame 必须匹配；缺失/冲突分别为 404/409，JPEG 身份头和禁止缓存策略不变 / Preserve identity, 404/409 errors and uncached JPEG headers |
| 停止成功的边界 / Stop-success limit | 命令回执不证明原生句柄已释放；仍须回读 sleeping 与占用，超时隔离不能包装成释放成功 / A command receipt alone does not establish native release |

这里固定当前行为，不重新定义状态机，也不把自由字典字段视为完整 JSON Schema。其语义由行为测试及文档共同保护，真实线程阻塞与恢复仍待板上验证。

This freezes current behavior without redesigning state machines or treating free-form dictionaries as fully specified schemas. Behavioral tests and documentation protect those semantics; native blocking and recovery still require board acceptance.

## 后续变更规则 / Change Rules

内部重构应原样通过基线。确需增量字段/接口时，同一 PR 解释调用方兼容性、更新文档及行为测试，并审阅最小 JSON 差异；不得为了消除测试失败直接重录整份基线。删除字段、收紧输入或改变既有错误语义须采用新版本路径。库升级造成 schema 表示变化时，先证明语义等价。

Refactors must pass the baseline unchanged. Additions require compatibility rationale, docs, behavioral tests and review of the minimal JSON diff in the same PR. Never regenerate blindly to hide failures. Removed fields, narrower inputs or changed failure semantics require a new versioned path. Prove semantic equivalence before accepting schema differences caused by dependency upgrades.
