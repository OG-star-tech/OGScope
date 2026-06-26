# Dev REST Domain v1

English | [中文](dev-rest-v1.md)

This document describes OGScope **developer-domain** APIs (internal). They are **not** part of the customer-facing stable contract.

## Surface split

- Stable contract (customer-visible): `/api/core/v1/*`
- Developer domain (internal debug and experiments): `/api/dev/*`

## Main path groups

- Debug tools: `/api/dev/debug/*`
  - Camera debug, presets, recordings, systemd logs
- Analysis lab: `/api/dev/analysis/*`
  - Asset pool, experiment records, offline/online solving and parameter trials

## Debug camera status

- `GET /api/dev/debug/camera/status`
  - Purpose: developer console diagnostics and board-side performance triage.
  - Typical fields:
    - `sensor_target_fps` / `preview_target_fps`: sensor and preview target FPS
    - `actual_capture_fps` / `actual_preview_fps`: runtime capture and preview FPS
    - `actual_exposure_us` / `frame_duration_us`: exposure and frame-duration telemetry
    - `preview_consumers` / `analysis_consumers` / `recording_consumers`: active consumers
    - `jpeg_average_encode_ms` / `jpeg_cached_bytes` / `jpeg_encode_failures`: JPEG encoder health
    - `throttle_reason`: runtime throttling reason; empty means no active throttling
    - `process_rss_kb` / `process_swap_kb` / `cma_free_kb`: low-memory-board diagnostics
    - `preview_encoder` / `jpeg_source_format`: active preview encoder and source format
    - `camera_driver` / `camera_backend`: camera driver and backend
    - `lores_enabled` / `lores_available` / `lores_width` / `lores_height` / `lores_format`: low-resolution stream status

### Debug camera settings

- `POST /api/dev/debug/camera/settings`
  - Purpose: incremental settings endpoint for the developer UI; not part of the stable external contract.
  - Recent fields include:
    - `whiteBalanceMode`, `whiteBalanceGainR`, `whiteBalanceGainB`
    - `autoExposureMaxUs`
    - `aeFlickerMode`
    - `noiseReductionMode`
    - `previewEncoder`

## Analysis lab extensions

- `POST /api/dev/analysis/solve/frame`
- `POST /api/dev/analysis/solve/frame_upload`
  - Request may include optional `enable_polar_guide`.
  - `overlay_ext.polar_guide` in the response is experimental polar-guide overlay data for developer UI validation; it is not a stable `core/v1` field.
  - `overlay_ext.labels_topn` and `overlay_ext.polar_guide` are independent optional fields; callers must handle either one being absent.

## Documentation entrypoints

- Standard OpenAPI: `/docs` (default)
- Developer OpenAPI: `/docs/dev`
- Full OpenAPI: `/docs/all`

## Compatibility policy

- The developer domain may iterate and refactor; stability across major revisions is not guaranteed.
- Customer integrations must rely only on `core/v1` and its versioning policy.
