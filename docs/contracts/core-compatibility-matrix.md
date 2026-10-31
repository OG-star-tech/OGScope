# OGScope 核心契约兼容矩阵 / Core Contract Compatibility Matrix

## 移除未实现的机械对准占位接口 / Remove unimplemented mount-alignment placeholders

`/api/alignment/start`、`stop`、`status`此前只返回固定成功或进度，并未实现机械控制，现已移除。调用方应使用自己的运动编排；OGScope只通过Core提供真实图像、解算和视觉目标。Core v1端点不受影响。

The legacy `/api/alignment/start`, `stop` and `status` routes returned constant success/progress without implementing mount control and have been removed. Consumers own motion orchestration; OGScope supplies real capture, solves and visual targets through Core. Core v1 endpoints are unchanged.

## 矩阵 / Matrix

| OGScope | 契约路径 / Contract Path | 说明 |
|---|---|---|
| 0.1.x | `/api/core/v1/*` | 上层集成方 REST 入口 |
| 0.1.x | [subordinate-mode](subordinate-mode.md) | `standalone` / `subordinate` 运行模式 |
| 0.1.x | [hardware-plane-uds-v1](hardware-plane-uds-v1.md) | subordinate 下委托传感器 UDS JSON-RPC |

## 向后兼容规则

- 保持已有响应键稳定。
- 新增键须为可选或增量添加。
- 破坏性变更须发布新路径版本（例如 `/v2/`）。

## Backward compatibility

- Keep existing response keys stable.
- New keys must be optional/additive.
- Breaking changes must publish a new path version (for example `/v2/`).

## Exposure preparation / 曝光准备

Pair the new preparation capability and camera lease endpoint with consumers that wait before starting pose budgets. Old clients remain valid; new clients may fall back only on a missing endpoint and must report the reduced guarantee.

配套更新等待曝光准备、持有任务租约的调用方。旧客户端仍可运行；新客户端仅在接口缺失时回退，并明确不能保证新能力生效。无 BSP 或控制器固件依赖。

## Current pole / 当前极轴

New product clients require `current_pole_target` and explicitly request `current_pole_v1`. Upgrade OGScope first; an old server is blocked before motion. Legacy Core v1 calls without the new policy retain their historical J2000 semantics. The current policy never falls back to a catalogue pole. 先升级 OGScope；新 ZenitAPA 在旧服务上停止运动。旧 v1 未声明策略请求保持原义，新产品必须显式请求当前极轴。 See [model and contract](current-pole-v1.md).
