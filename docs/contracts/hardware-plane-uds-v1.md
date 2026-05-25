# Hardware Plane UDS JSON-RPC v1（委托传感器）

中文 | [English](hardware-plane-uds-v1_EN.md)

## 范围

当 OGScope 以 `subordinate` 角色运行时，本地传感器服务禁用，传感器读请求通过 **Unix Domain Socket JSON-RPC** 委托给外部传感器提供方（delegated sensor provider）。

传输实现见 `ogscope/platform/hardware_plane/transport/jsonrpc_uds.py`。

## 套接字

- 配置项：`OGSCOPE_HARDWARE_PLANE_REMOTE_UDS_SOCKET`
- 默认：`/tmp/external-sensor-plane.sock`
- 部署方须保证 OGScope 与传感器提供方使用同一路径

## 必需方法（v1）

| 方法 | 说明 |
|------|------|
| `status.get` | 服务健康与就绪状态 |
| `capability.list` | 可用传感器能力列表 |
| `sensor.read` | 读取指定传感器 |

## 请求示例

```json
{"jsonrpc":"2.0","id":1,"method":"sensor.read","params":{"name":"sensor.gps"}}
```

## 成功响应

响应体须符合 OGScope hardware-plane 统一形状：

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

## 错误响应

```json
{
  "success": false,
  "error": {"code": "unavailable", "message": "reason"},
  "data": {}
}
```

常见 `error.code`：`unavailable`、`timeout`、`invalid_params`。

## 能力元数据

OGScope 在 subordinate 模式下将传感器 capability 的 `metadata.source` 标记为 `remote_delegated`。

## 版本与兼容

- v1 以增量扩展为主；新增方法或字段须更新本文档与 [core-compatibility-matrix](core-compatibility-matrix.md)。
- 破坏性变更须发布新版本文档（例如 `hardware-plane-uds-v2`）。
