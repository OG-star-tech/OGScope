# OGScope 核心契约兼容矩阵 / Core Contract Compatibility Matrix

## 矩阵 / Matrix

| OGScope | 契约路径 / Contract Path |
|---|---|
| 0.1.x | `/api/core/v1/*` |

## 向后兼容规则

- 保持已有响应键稳定。
- 新增键须为可选或增量添加。
- 破坏性变更须发布新路径版本（例如 `/v2/`）。

## Backward compatibility

- Keep existing response keys stable.
- New keys must be optional/additive.
- Breaking changes must publish a new path version (for example `/v2/`).
