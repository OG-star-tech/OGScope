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
