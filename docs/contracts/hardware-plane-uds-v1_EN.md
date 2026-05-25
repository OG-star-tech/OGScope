# Hardware Plane UDS JSON-RPC v1 (Delegated Sensors)

English | [中文](hardware-plane-uds-v1.md)

## Scope

When OGScope runs in `subordinate` role, local sensor services are disabled and sensor reads are delegated to an external **delegated sensor provider** over **Unix Domain Socket JSON-RPC**.

Transport implementation: `ogscope/platform/hardware_plane/transport/jsonrpc_uds.py`.

## Socket

- Config: `OGSCOPE_HARDWARE_PLANE_REMOTE_UDS_SOCKET`
- Default: `/tmp/external-sensor-plane.sock`
- Deployments must align the path between OGScope and the sensor provider

## Required methods (v1)

| Method | Description |
|--------|-------------|
| `status.get` | service health and readiness |
| `capability.list` | available sensor capabilities |
| `sensor.read` | read a named sensor |

## Request example

```json
{"jsonrpc":"2.0","id":1,"method":"sensor.read","params":{"name":"sensor.gps"}}
```

## Success response

Payload must follow the OGScope hardware-plane shape:

```json
{
  "success": true,
  "error": null,
  "data": {
    "sensor": {
      "name": "sensor.gps",
      "state": "available",
      "value": {"lat": 0.0, "lon": 0.0},
      "unit": "deg"
    }
  }
}
```

## Error response

```json
{
  "success": false,
  "error": {"code": "unavailable", "message": "reason"},
  "data": {}
}
```

Common `error.code`: `unavailable`, `timeout`, `invalid_params`.

## Capability metadata

In subordinate mode, OGScope marks sensor capabilities with `metadata.source` = `remote_delegated`.

## Versioning

Additive-first; new methods/fields require updating this document and [core-compatibility-matrix](core-compatibility-matrix.md).
Breaking changes require a new doc version (for example `hardware-plane-uds-v2`).
