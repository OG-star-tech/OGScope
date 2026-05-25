# Subordinate 运行模式

中文 | [English](subordinate-mode_EN.md)

## 概述

OGScope 支持两种硬件平面角色：

- `standalone`（默认）：完整本地能力（传感器、HMI、UI、网络）。
- `subordinate`：作为**从属能力服务**运行，由上层集成方编排；OGScope 提供相机与核心 REST 契约，传感器等能力可通过外部 UDS 服务委托。

本模式适用于任意上层集成方，不限于单一产品。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OGSCOPE_HARDWARE_PLANE_ROLE` | `standalone` | `standalone` 或 `subordinate` |
| `OGSCOPE_ENABLE_LOCAL_SENSORS` | `true` | subordinate 下自动禁用本地传感器 |
| `OGSCOPE_ENABLE_HMI` | `true` | subordinate 下自动禁用 HMI |
| `OGSCOPE_ENABLE_UI` | `true` | 是否启用 Web UI 路由（subordinate 下仍可按需开启调试台） |
| `OGSCOPE_SUBORDINATE_LOCAL_DEV_ONLY` | `false` | subordinate 下是否仅允许本机访问 `/api/dev/*` |
| `OGSCOPE_HARDWARE_PLANE_REMOTE_UDS_SOCKET` | `/tmp/external-sensor-plane.sock` | 外部传感器 UDS 路径（见 [hardware-plane-uds-v1](hardware-plane-uds-v1.md)） |
| `OGSCOPE_HARDWARE_PLANE_RPC_TIMEOUT_MS` | `800` | 硬件平面 RPC 超时（毫秒） |

## subordinate 表面限制

| 能力 | standalone | subordinate |
|------|------------|-------------|
| `/api/core/v1/*` | 可用 | 可用（上层集成方主入口） |
| `/api/dev/*` | 可用 | 可用；若 `OGSCOPE_SUBORDINATE_LOCAL_DEV_ONLY=true` 则仅 localhost |
| `/api/network/*` | 可用 | **禁用**（网络由上层集成方管理） |
| 本地传感器 / HMI | 可用 | **禁用**（委托外部 UDS） |
| 相机 | OGScope 本地 | OGScope 本地 |

## 集成路径

- **业务调用**：上层集成方 → OGScope `REST /api/core/v1/*`（详见 [core-rest-v1](core-rest-v1.md)）。
- **传感器委托**：OGScope → 外部传感器服务 `UDS JSON-RPC`（详见 [hardware-plane-uds-v1](hardware-plane-uds-v1.md)）。

## 版本与兼容

- 契约以增量扩展为主；破坏性变更须更新本文档与 [core-compatibility-matrix](core-compatibility-matrix.md)。
