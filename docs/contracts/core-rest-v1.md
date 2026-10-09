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
    - `observation_time_utc`：可选，当前图像曝光中点 UTC；天文坐标换算应优先使用该时刻
    - `capture_completed_at_utc`、`capture_exposure_us`：可选抓帧诊断字段
    - `centroid_quality`：可选提星与遮挡回退诊断；`strategy`、`normal_status`、`fallback_attempted`、`fallback_status` 描述实际采用的路径
      - `scene` 仅在常规解算失败后分析；`has_structural_evidence` 只表示发现大亮区或长结构边缘，星点密度本身不构成遮挡证据
      - `metrics.filter_limited=true` 表示过滤达到保守上限，剩余候选已放行；调用方不得把该开发诊断转换为用户错误
    - `solve_overlay.scene_evidence_regions`：可选、有界的干扰证据几何；黄色区域/线段只解释过滤依据，不能单独否定解算结果
    - `solve_frame`：可选精确解算帧元数据；`available=true` 时包含 `session_id`、`frame_id`、尺寸、JPEG 字节数、编码器与耗时
  - `last_error: str`
  - `frame_count: int`
  - `fullsolve_count: int`

Core 实时分析运行时，开发者相机单帧解算返回 `SKIPPED_BUSY`，避免调试轮询与产品对准争抢相机和 CPU；文件解算仍可提交，并与实时解算串行排队。

实时分析、快照编码和开发者图像分析共用一个工作线程，以限制低内存设备的原生图像缓存和并发内存峰值。停止会话取消等待并丢弃该会话后续结果；已经执行中的原生解算会自行结束，下一项解算等它完成后才执行。

常规 `MATCH_FOUND` 是权威结果，不会被后续画面分类推翻。只有常规解算失败且存在独立结构证据时，OGScope 才会过滤与证据重合的过密/共线候选并重试一次；过滤最多移除本次候选池的 35%。

### 2.1) Get Exact Solve Frame

- `GET /api/core/v1/analysis/frame?session_id=...&frame_id=...`
- 仅保留最新一张压缩 JPEG，不保留 raw 帧或历史队列；新结果会覆盖或清除旧图
- 成功解算以及带结构证据的失败会尝试编码；编码失败不改变星图解算状态
- `session_id` 或 `frame_id` 与当前结果不匹配时返回 `409`，当前没有快照时返回 `404`
- 响应使用 `private, no-store`；调用方应使用当前 `result.solve_frame` 中的双键读取，避免错配

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
  - `info.driver` / `info.backend` 与 `info.capabilities` 是可选的后端能力遥测。V4L2 RAW 使用 OGScope 软件 AE，仍保持相同的 RGB888、帧身份和解算契约；硬件控件回读失败时 `info.actual_exposure_us` / `info.actual_analogue_gain` 可为 `null`
  - 上层不得依据驱动名称分叉业务逻辑；只消费 Core v1 的 `connected`、`streaming`、`info.optics.effective_fov_deg`、可选 capability/ambient 字段以及既有分析结果
  - `info.ae_scene_mode` 与 `info.ae_requested_exposure_mode` 是自主 AE 诊断；`starfield` 表示 OGScope 已独立识别暗天空并请求快门优先的长曝光曲线，不依赖上位机工作模式。请求值不代表驱动已生效
  - Picamera2 可选诊断：`info.ae_actual_exposure_mode` 来自完成帧的模式回报；`info.ae_exposure_mode_status` 为 `unknown`、`awaiting_metadata`、`verified`、`unverified` 或 `unsupported`。`verified` 只证明模式已回报；实际曝光/增益仍以帧元数据为准。`info.actual_auto_exposure` / `info.actual_auto_gain` 缺少模式元数据时为 `null`。libcamera 0.5.2 的 Long 切换先暂停 AE，收到帧确认后再开启；8 秒内未确认会恢复 AE 并报告 `exposure_mode_not_confirmed`，避免假报成功
  - `info.auto_exposure_max_us` 是可调的曝光帧周期上限，Picamera2 与 V4L2 均限制为最多 3 秒；Long 曲线先延长快门再增加增益。长曝光会降低实际帧率，上限不表示每帧都会使用最长曝光
- `POST /api/core/v1/camera/start`
  - 仅当相机启动命令成功且状态确认 `connected=true`、`streaming=true` 时返回 `success=true`
  - `applied` 包含 `action`、`hardware_plane_ok`、`ready`、`connected`、`streaming`；调用方应以 `ready` 判断是否可立即取帧
- `POST /api/core/v1/camera/stop`
- `GET /api/core/v1/camera/preview/stream?quality=75`
  - 产品级 MJPEG 连续预览；使用与相机分析共享的预览消费者和并发限制
  - `quality` 范围为 `10`–`100`；省略时使用服务端预览质量配置
  - JPEG 预览始终消费共享帧，不因客户端质量不同而再次抓帧；同帧同质量共用有界变体缓存。未保留 RAW 时从共享 JPEG 转码，提高输出质量不能恢复源 JPEG 已丢失的细节
  - 响应禁止缓存；达到并发上限时淘汰最久未完成发送进展的旧连接，并为新连接腾出名额
- `POST /api/core/v1/camera/reset-temporal-history`
  - 无请求体；底座移动并确认稳定后由上层显式调用，清空驱动跨帧降噪历史。OGScope 不自行判断底座是否移动
  - 响应沿用相机控制结构；`applied.temporal_history_reset` 表示驱动是否实现重置钩子。Picamera2 等无跨帧历史的驱动返回 `false`
  - 该接口是 V4L2 移动后避免旧画面混入的集成钩子；上层未调用时，不能认为端到端重置已生效

流控诊断状态和单帧 JPEG 预览（轮询、`since_frame_id`、调试限频）仍仅暴露于开发路径：

- `GET /api/dev/debug/camera/stream?quality=75` — 与 Core 预览共享实现的开发入口
- `GET /api/dev/debug/camera/stream/status` — `max_clients`、`active_clients`、取帧超时、目标预览帧率
  - `camera_read_average_ms` 包含驱动取帧与处理；`jpeg_average_encode_ms` 是共享预览编码；`jpeg_variant_average_encode_ms` 与 `jpeg_variant_cached_bytes` 是客户端质量变体的耗时与缓存字节数
  - 吞吐目标取传感器与预览目标的较小值；`throttle_reason=preview_rate_limit` 表示主动预览限帧。`auto_exposure_long` 需要实际曝光或帧周期超出有效目标周期的证据；其余产帧吞吐不足报告 `processing_limit`
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
