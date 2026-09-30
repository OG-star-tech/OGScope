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
  - `solve_context` (optional sensor context)
    - `quality.time_fresh`: optional; when explicitly `false`, time is not used for sensor prediction
    - `quality.camera_pose_calibrated`: optional; when explicitly `false`, mount angles are not used as camera-pose prediction
    - Omitting both fields preserves legacy-client behavior
    - When either field is `false`, OGScope returns `sensor_status=unavailable` for diagnostics without changing the plate solver's `MATCH_FOUND` result
- Response:
  - `success: bool`
  - `session_id: str`
  - `state: "running" | "stopped"`
  - `message: str`

A new `session_id` is generated whenever analysis starts from the stopped state;
upstream consumers should ignore results from an older session.

### 2) Get Analysis Result

- `GET /api/core/v1/analysis/result`
- Response:
  - `success: bool`
  - `session_id: str`
  - `state: "running" | "completed" | "stopped"`
  - `result: object | null`
    - `observation_time_utc`: optional exposure-midpoint UTC for the current frame; astronomical coordinate conversion should prefer it
    - `capture_completed_at_utc`, `capture_exposure_us`: optional capture diagnostics
    - `centroid_quality`: optional extraction and obstruction-fallback diagnostics; `strategy`, `normal_status`, `fallback_attempted`, and `fallback_status` describe the path actually used
      - `scene` is analyzed only after a normal solve failure; `has_structural_evidence` requires a large bright region or long structural edges, and star density alone is never obstruction evidence
      - `metrics.filter_limited=true` means filtering reached its conservative cap and retained the remaining candidates; callers must not turn this developer diagnostic into a user error
  - `last_error: str`
  - `frame_count: int`
  - `fullsolve_count: int`

While Core realtime analysis is active, developer single-frame camera solves return `SKIPPED_BUSY` so debug polling cannot contend with product alignment for camera and CPU resources. File solving is unaffected.

A normal `MATCH_FOUND` result is authoritative and is never overturned by scene classification. Only after a normal failure with independent structural evidence does OGScope remove dense or collinear candidates that overlap that evidence and retry once. At most 35% of the reserve candidate pool is removed.

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
  - `health: str` (`healthy` | `degraded`)
  - `health_reasons: string[]` — stable degradation codes when not healthy (e.g. `camera_not_connected`, `network_wifi_not_configured`); empty when `healthy`
  - `version: str`
  - `capabilities: object`
  - `system: object`
  - `camera: object` — camera online and runtime summary
  - `network: object` — WiFi mode / signal / connection; includes `managed_by`, `in_health_scope`; when subordinate or minimal deploy without OGScope WiFi config, status is `delegated` and **does not** affect `health`
  - `sensors: object` — temperature / CPU / memory, etc.

### 5) Camera Runtime & Preview (MJPEG / single-frame)

- `GET /api/core/v1/camera/status` — connection, stream state, runtime overrides, and optional `ambient_hint`
  - `ambient_hint` is advisory ambient-light telemetry for upstream display/interaction policy. Typical fields: `available`, `dark_score` (0.0 bright to 1.0 dark), `lux`, `exposure_us`, `digital_gain`
  - Optional `info.optics` describes product optics. `lens` carries nominal 16mm F1.4, 5MP optical rating, M12, and IR-cut properties; `full_sensor_fov_deg` describes the 1920×1080 optical field, while `effective_fov_deg` is the product-calibrated field for the active capture mode. Upstream solving and sky search should prefer `effective_fov_deg`, with a local fallback for older servers.
  - Optional `info.driver` / `info.backend` and `info.capabilities` describe backend capabilities. V4L2 RAW uses OGScope software AE while preserving the same RGB888, frame-identity, and solve contracts. Failed hardware-control readback may leave `info.actual_exposure_us` / `info.actual_analogue_gain` as `null`.
  - Upstream business logic must not branch on driver names; it consumes Core v1 readiness, `info.optics.effective_fov_deg`, optional capability/ambient telemetry, and existing analysis results.
  - `info.ae_scene_mode` and `info.ae_requested_exposure_mode` diagnose autonomous AE. `starfield` means OGScope independently selected the shutter-first long-exposure curve and does not depend on an upstream work mode.
- `POST /api/core/v1/camera/start`
  - Returns `success=true` only when the start command succeeds and status confirms both `connected=true` and `streaming=true`
  - `applied` includes `action`, `hardware_plane_ok`, `ready`, `connected`, and `streaming`; callers should use `ready` before requesting frames
- `POST /api/core/v1/camera/stop`
- `GET /api/core/v1/camera/preview/stream?quality=75`
  - Product MJPEG preview using the shared preview consumer and concurrency limiter
  - `quality` ranges from `10` to `100`; omission uses the server preview-quality setting
  - Responses are non-cacheable; at the client limit, the stream with the oldest send progress is evicted to make room for the new connection
- `POST /api/core/v1/camera/reset-temporal-history`
  - No request body. The upstream caller explicitly invokes this after a mount move has settled to discard cross-frame denoising history; OGScope does not infer mount motion
  - Uses the camera-control response shape. `applied.temporal_history_reset` reports whether the driver implements the reset hook; drivers without cross-frame history, such as Picamera2, return `false`
  - This is an integration hook for avoiding pre-move history on V4L2. Until the upstream caller invokes it, end-to-end reset after movement is not in effect

Stream diagnostics and single-frame JPEG preview (polling, `since_frame_id`, debug rate limits) remain developer-only:

- `GET /api/dev/debug/camera/stream?quality=75` — developer entry backed by the shared Core preview implementation
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
