# Core REST Contract v1

本文档定义上层调用 OGScope 的最小稳定接口（上层调用方）。

## 设计原则

- OGScope 仅提供稳定 REST 契约，不承诺 外部集成方 私有实现细节。
- 新增字段保持向后兼容，不删除既有稳定字段。
- 错误语义以 HTTP 状态码 + `detail` 文本表达。

## Endpoints

### 1) Start Analysis

- `POST /api/core/v1/analysis/start`
- 请求体（可选）：
  - `hint_ra_deg`
  - `hint_dec_deg`
  - `fov_estimate`
  - `fov_max_error`
  - `solve_timeout_ms`
- 响应：
  - `success: bool`
  - `session_id: str`
  - `state: "running" | "stopped"`
  - `message: str`

### 2) Get Analysis Result

- `GET /api/core/v1/analysis/result`
- 响应：
  - `success: bool`
  - `session_id: str`
  - `state: "running" | "completed" | "stopped"`
  - `result: object | null`
  - `last_error: str`
  - `frame_count: int`
  - `fullsolve_count: int`

### 3) Stop Analysis

- `POST /api/core/v1/analysis/stop`
- 响应：
  - `success: bool`
  - `session_id: str`
  - `state: "running" | "stopped"`
  - `message: str`

### 4) Get System Status

- `GET /api/core/v1/system/status`
- 响应：
  - `success: bool`
  - `health: str`
  - `version: str`
  - `capabilities: object`
  - `system: object`

## 错误码与版本策略

- `4xx`：请求参数非法、契约字段校验失败。
- `5xx`：内部运行异常或底层能力不可用。
- 契约版本路径固定为 `/v1/`。新增字段以可选形式扩展，不破坏既有消费者。
