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
  - 开发 UI 的曝光输入与普通摘要统一显示为秒；提交到现有 API、预设和侧车时仍换算并保留 `exposure_us` / `autoExposureMaxUs` 微秒字段，避免破坏兼容性。

### 星点焦点校准

- `GET /api/dev/debug/camera/focus/metrics`
  - 用途：基于当前原始相机帧计算实时星点锐度，引导用户手动调整镜头焦距。
  - 可选查询参数：`target_x` 与 `target_y`，均为 `0..1` 归一化坐标；必须成对提供，用于锁定预览画面中点击的星点。
  - 响应包含：
    - `aggregate.median_hfd_px` / `aggregate.hfd_mad_px`：可用星点的 HFD 中位数与离散度
    - `aggregate.median_fwhm_px`：可用星点的 FWHM 中位数
    - `aggregate.median_concentration`：星点核心能量集中度
    - `stars` / `selected_star`：候选星点及当前选择
    - `stars_detected` / `stars_measured` / `stars_used`：检测、测量与质量筛选计数
  - HFD 与 FWHM 越低通常表示越锐利；这些数值只适合在同一镜头、曝光、增益与目标区域下做相对比较，不是跨设备绝对标定值。

## 分析实验扩展

### 解算管线边界

- `/api/core/v1/analysis/*` 与 `/api/dev/analysis/*` 保留不同的产品/实验接口职责，但两者的当前帧星图解算统一使用 `PlateSolver.solve_from_bgr_frame()` 的 Tetra 提星与匹配管线。
- 开发接口可覆盖提星参数和实验分档；Core 使用服务端生产默认值，不向上层暴露实验分档。
- `StarExtractor` 仍用于焦点校准、轻量星点计数和性能基线，不作为产品级 plate solve 的权威提星结果。
- 历史的 Core `StarExtractor -> PlateSolver.solve()` 组合已停止使用；这是内部实现迁移，不弃用任何 `/api/core/v1/*` 或 `/api/dev/*` HTTP 路径。

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
