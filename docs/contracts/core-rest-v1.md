# Core REST Contract v1

中文 | [English](core-rest-v1_EN.md)

本文档定义上层调用 OGScope 的最小稳定接口。

> 开发者调试/实验接口已隔离到 `/api/dev/*`，默认文档不展示，详见 `docs/contracts/dev-rest-v1.md`。

## 设计原则

- OGScope 仅提供稳定 REST 契约，不承诺调用方私有实现细节。
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
  - `solve_context`（可选传感器上下文）
    - `quality.time_fresh`：可选；显式为 `false` 时不使用该时间做传感器预测
    - `quality.camera_pose_calibrated`：可选；显式为 `false` 时不使用机械轴角做光轴预测
    - 两个字段缺失时保持旧客户端行为
    - 字段为 `false` 时仅返回 `sensor_status=unavailable` 诊断，不影响星图本身的 `MATCH_FOUND` 结果
- 响应：
  - `success: bool`
  - `session_id: str`
  - `state: "running" | "stopped"`
  - `message: str`

每次从停止状态启动分析时都会生成新的 `session_id`；上层应忽略旧会话结果。

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
  - `health: str`（`healthy` | `degraded`）
  - `health_reasons: string[]`（降级时的稳定原因码，如 `camera_not_connected`、`network_wifi_not_configured`；`healthy` 时为空数组）
  - `version: str`
  - `capabilities: object`
  - `system: object`
  - `camera: object`（相机在线与运行态摘要）
  - `network: object`（WiFi 模式/信号/连接态；含 `managed_by`、`in_health_scope`；subordinate 或最小部署未配 WiFi 时为 `delegated`，**不参与** `health`）
  - `sensors: object`（温度/CPU/内存等核心传感状态）

### 5) Camera Runtime & Preview (MJPEG / single-frame)

- `GET /api/core/v1/camera/status`
  - 返回相机连接状态、流状态、runtime overrides 与可选 `ambient_hint`
  - `ambient_hint` 是环境亮度建议遥测，供上层设备做显示/交互策略参考；典型字段包括 `available`、`dark_score`（0.0 明亮到 1.0 昏暗）、`lux`、`exposure_us`、`digital_gain`
  - `info.optics` 是可选的产品光学描述；`lens` 保存 16mm F1.4、标称 500 万像素、M12 与红外截止滤镜等名义参数，`full_sensor_fov_deg` 保存 1920×1080 全幅光学视场，`effective_fov_deg` 保存当前采集模式经过产品标定后的有效视场。上层解算与寻星应优先使用 `effective_fov_deg`，字段缺失时再回退本地默认值
  - `info.ae_scene_mode` 与 `info.ae_requested_exposure_mode` 是自主 AE 诊断；`starfield` 表示 OGScope 已独立识别暗天空并选择快门优先的长曝光曲线，不依赖上位机工作模式
- `POST /api/core/v1/camera/start`
  - 仅当相机启动命令成功且状态确认 `connected=true`、`streaming=true` 时返回 `success=true`
  - `applied` 包含 `action`、`hardware_plane_ok`、`ready`、`connected`、`streaming`；调用方应以 `ready` 判断是否可立即取帧
- `POST /api/core/v1/camera/stop`
- `GET /api/core/v1/camera/preview/stream?quality=75`
  - 产品级 MJPEG 连续预览；使用与相机分析共享的预览消费者和并发限制
  - `quality` 范围为 `10`–`100`；省略时使用服务端预览质量配置
  - 响应禁止缓存；达到并发上限时返回 `503`

流控诊断状态和单帧 JPEG 预览（轮询、`since_frame_id`、调试限频）仍仅暴露于开发路径：

- `GET /api/dev/debug/camera/stream?quality=75` — 与 Core 预览共享实现的开发入口
- `GET /api/dev/debug/camera/stream/status` — `max_clients`、`active_clients`、取帧超时、目标预览帧率
- `GET /api/dev/debug/camera/preview` — 单帧预览

### 6) Camera Tuning

- `POST /api/core/v1/camera/tune`
  - 请求体采用可选字段增量更新，支持：
    - 曝光/增益：`exposure_us`、`analogue_gain`、`digital_gain`、`auto_exposure`
    - 采集参数：`fps`、`width`、`height`、`sampling_mode`
    - 成像方向：`rotation`、`flip_horizontal`、`flip_vertical`
    - 颜色相关：`color_mode`、`white_balance_mode`、`white_balance_gain_r`、`white_balance_gain_b`

### 7) Video Metadata

- `GET /api/core/v1/camera/videos`
  - 返回录制视频列表（仅 video 类型）
- `GET /api/core/v1/camera/videos/{filename}`
  - 返回单个视频的侧车元信息（曝光/增益/分辨率/时长等）

## 错误码与版本策略

- `4xx`：请求参数非法、契约字段校验失败。
- `5xx`：内部运行异常或底层能力不可用。
- 契约版本路径固定为 `/v1/`。新增字段以可选形式扩展，不破坏既有消费者。
