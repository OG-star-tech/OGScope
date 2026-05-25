# Subordinate Runtime Mode

English | [中文](subordinate-mode.md)

## Overview

OGScope supports two hardware-plane roles:

- `standalone` (default): full local capabilities (sensors, HMI, UI, network).
- `subordinate`: runs as a **subordinate capability service** orchestrated by an upper integrator; OGScope provides camera and core REST contract, with sensors delegated via an external UDS service.

This mode applies to any upper integrator, not a single product.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OGSCOPE_HARDWARE_PLANE_ROLE` | `standalone` | `standalone` or `subordinate` |
| `OGSCOPE_ENABLE_LOCAL_SENSORS` | `true` | auto-disabled in subordinate |
| `OGSCOPE_ENABLE_HMI` | `true` | auto-disabled in subordinate |
| `OGSCOPE_ENABLE_UI` | `true` | Web UI routes (debug console may stay enabled in subordinate) |
| `OGSCOPE_SUBORDINATE_LOCAL_DEV_ONLY` | `false` | restrict `/api/dev/*` to localhost in subordinate |
| `OGSCOPE_HARDWARE_PLANE_REMOTE_UDS_SOCKET` | `/tmp/external-sensor-plane.sock` | external sensor UDS path (see [hardware-plane-uds-v1](hardware-plane-uds-v1_EN.md)) |
| `OGSCOPE_HARDWARE_PLANE_RPC_TIMEOUT_MS` | `800` | hardware-plane RPC timeout (ms) |

## Subordinate surface limits

| Capability | standalone | subordinate |
|------------|------------|-------------|
| `/api/core/v1/*` | available | available (primary integrator entry) |
| `/api/dev/*` | available | available; localhost-only if `OGSCOPE_SUBORDINATE_LOCAL_DEV_ONLY=true` |
| `/api/network/*` | available | **disabled** (network owned by integrator) |
| local sensors / HMI | available | **disabled** (delegated UDS) |
| camera | local OGScope | local OGScope |

## Integration paths

- **Business**: integrator → OGScope `REST /api/core/v1/*` ([core-rest-v1](core-rest-v1_EN.md)).
- **Sensor delegation**: OGScope → external sensor service over `UDS JSON-RPC` ([hardware-plane-uds-v1](hardware-plane-uds-v1_EN.md)).

## Versioning

Additive-first; breaking changes require updating this document and [core-compatibility-matrix](core-compatibility-matrix.md).
