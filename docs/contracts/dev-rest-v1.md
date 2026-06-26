# Dev REST Domain v1

中文 | [English](dev-rest-v1_EN.md)

本文档定义 OGScope 开发者域接口（内部使用），不属于对客户承诺的稳定契约。

## 域划分

- 标准契约（客户可见）：`/api/core/v1/*`
- 开发者域（内部调试与实验）：`/api/dev/*`

## 主要路径组

- 调试工具：`/api/dev/debug/*`
  - 相机调试、预设、录制文件、systemd 日志
- 分析实验：`/api/dev/analysis/*`
  - 素材池、实验记录、离线/在线解算与参数试验

## 调试相机状态

- `GET /api/dev/debug/camera/status`
  - 用途：开发者调试页与板端性能排查。
  - 典型字段：
    - `sensor_target_fps` / `preview_target_fps`：传感器与预览目标帧率
    - `actual_capture_fps` / `actual_preview_fps`：运行时采集与预览实际帧率
    - `actual_exposure_us` / `frame_duration_us`：曝光与帧时长遥测
    - `preview_consumers` / `analysis_consumers` / `recording_consumers`：消费者数量
    - `jpeg_average_encode_ms` / `jpeg_cached_bytes` / `jpeg_encode_failures`：JPEG 编码健康度
    - `throttle_reason`：运行时降速原因，空值表示未主动降速
    - `process_rss_kb` / `process_swap_kb` / `cma_free_kb`：低内存板排查指标
    - `preview_encoder` / `jpeg_source_format`：当前预览编码器与源格式
    - `camera_driver` / `camera_backend`：相机驱动与后端
    - `lores_enabled` / `lores_available` / `lores_width` / `lores_height` / `lores_format`：低分辨率支路状态

### 相机调试设置

- `POST /api/dev/debug/camera/settings`
  - 用途：开发调试 UI 的增量设置入口，不属于稳定对外契约。
  - 近期字段包括：
    - `whiteBalanceMode`、`whiteBalanceGainR`、`whiteBalanceGainB`
    - `autoExposureMaxUs`
    - `aeFlickerMode`
    - `noiseReductionMode`
    - `previewEncoder`

## 分析实验扩展

- `POST /api/dev/analysis/solve/frame`
- `POST /api/dev/analysis/solve/frame_upload`
  - 请求可选 `enable_polar_guide`。
  - 响应中的 `overlay_ext.polar_guide` 是实验性极轴引导叠加数据，用于开发 UI 验证，不属于 `core/v1` 稳定字段。
  - `overlay_ext.labels_topn` 与 `overlay_ext.polar_guide` 可独立存在；调用方应按可选字段处理。

## 文档入口

- 标准接口文档：`/docs`（默认）
- 开发者接口文档：`/docs/dev`
- 全量接口文档：`/docs/all`

## 兼容策略

- 开发者域允许迭代与重构，不保证跨大版本完全稳定。
- 对客户集成请仅依赖 `core/v1` 契约与其版本策略。
