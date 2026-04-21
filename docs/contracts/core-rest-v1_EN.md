# Core REST Contract v1

English | [中文](core-rest-v1.md)

This document defines the **minimal stable REST surface** for callers integrating with OGScope.

> Developer/debug/experimental APIs are isolated under `/api/dev/*` and are hidden from the default docs. See `docs/contracts/dev-rest-v1.md`.

## Design principles

- OGScope exposes a stable REST contract only; implementation details for a specific integrator are not guaranteed.
- New fields must remain backward compatible; do not remove stable fields.
- Errors use HTTP status codes plus `detail` text.

## Endpoints

### 1) Start Analysis

- `POST /api/core/v1/analysis/start`
- Request body (optional):
  - `hint_ra_deg`
  - `hint_dec_deg`
  - `fov_estimate`
  - `fov_max_error`
  - `solve_timeout_ms`
- Response:
  - `success: bool`
  - `session_id: str`
  - `state: "running" | "stopped"`
  - `message: str`

### 2) Get Analysis Result

- `GET /api/core/v1/analysis/result`
- Response:
  - `success: bool`
  - `session_id: str`
  - `state: "running" | "completed" | "stopped"`
  - `result: object | null`
  - `last_error: str`
  - `frame_count: int`
  - `fullsolve_count: int`

### 3) Stop Analysis

- `POST /api/core/v1/analysis/stop`
- Response:
  - `success: bool`
  - `session_id: str`
  - `state: "running" | "stopped"`
  - `message: str`

### 4) Get System Status

- `GET /api/core/v1/system/status`
- Response:
  - `success: bool`
  - `health: str`
  - `version: str`
  - `capabilities: object`
  - `system: object`
  - `camera: object` — camera online and runtime summary
  - `network: object` — WiFi mode / signal / connection state
  - `sensors: object` — temperature / CPU / memory, etc.

### 5) Camera Runtime & Preview (MJPEG / single-frame)

- `GET /api/core/v1/camera/status` — connection, stream state, runtime overrides
- `POST /api/core/v1/camera/start`
- `POST /api/core/v1/camera/stop`

MJPEG stream, stream control status, and single-frame JPEG preview (polling, `since_frame_id`, debug rate limits) are **only** on developer paths (not duplicated under `/api/core/v1/`):

- `GET /api/dev/debug/camera/stream?quality=75` — MJPEG (JPEG)
- `GET /api/dev/debug/camera/stream/status` — `max_clients`, `active_clients`, grab timeout, target preview FPS
- `GET /api/dev/debug/camera/preview` — single-frame preview

### 6) Camera Tuning

- `POST /api/core/v1/camera/tune`
  - Optional incremental fields:
    - Exposure/gain: `exposure_us`, `analogue_gain`, `digital_gain`, `auto_exposure`
    - Capture: `fps`, `width`, `height`, `sampling_mode`
    - Orientation: `rotation`, `flip_horizontal`, `flip_vertical`
    - Color: `color_mode`, `white_balance_mode`, `white_balance_gain_r`, `white_balance_gain_b`

### 7) Video Metadata

- `GET /api/core/v1/camera/videos` — list recorded videos (video entries only)
- `GET /api/core/v1/camera/videos/{filename}` — sidecar metadata (exposure, gain, resolution, duration, etc.)

## Errors and versioning

- `4xx`: invalid parameters or contract validation failure.
- `5xx`: internal failure or underlying capability unavailable.
- Contract version is fixed at `/v1/`. Add fields as optional extensions without breaking existing consumers.
