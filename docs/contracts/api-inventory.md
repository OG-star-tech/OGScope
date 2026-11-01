# API 调用方与兼容边界 / API Consumers and Compatibility

本清单区分稳定产品契约、现行界面接口和开发工具，作为后续相机迁移的兼容基线。接口继续保留；清单本身不改变鉴权、CORS 或角色默认配置。

This inventory distinguishes the stable product contract, current UI APIs and developer tools before camera migration. It does not change routes, authentication, CORS or role defaults.

## Core v1

稳定规则见 [兼容矩阵](core-compatibility-matrix.md)。当前所有 Core 路由在 standalone/subordinate 下均注册；新增字段应可选，破坏性变化使用新路径版本。上层集成方的业务仅依赖 Core，不依赖 Dev。

All Core routes are registered in both roles. Fields are extended additively; breaking changes require a new path version. Integrators consume Core for product behavior. See the [compatibility matrix](core-compatibility-matrix.md).

| 路径（前缀 `/api/core/v1`）/ Path | 方法 / Method | 当前用途、调用方 / Purpose and consumers | 状态影响 / Effects | 弃用条件 / Retirement |
|---|---|---|---|---|
| `/system/status` | GET | 集成方健康与版本 / Integrator health and version | 状态读取 / Status | v1 内保留 / Retain in v1 |
| `/camera/status` | GET | 集成方相机、光学及占用遥测 / Camera, optics and ownership | 读取遥测 / Read telemetry | v1 内保留 / Retain in v1 |
| `/camera/start`, `/camera/stop` | POST | 产品相机生命周期 / Product camera lifetime | 启停设备；忙碌保护 / Device control with busy guards | v1 内保留 / Retain in v1 |
| `/camera/lease` | POST | 跨任务步骤保留相机 / Keep camera across task steps | 获取、续期、释放占用 / Acquire, renew, release lease | 增量能力，保留 / Additive capability, retain |
| `/camera/preview/stream` | GET | 产品 MJPEG / Product MJPEG | 连接期间持有预览消费者 / Holds a preview consumer | v1 内保留 / Retain in v1 |
| `/camera/tune` | POST | 产品相机参数 / Product camera settings | 修改运行参数 / Runtime changes | v1 内保留 / Retain in v1 |
| `/camera/reset-temporal-history` | POST | 移动稳定后的历史重置 / Reset after settled motion | 清除后端时域历史 / Clears temporal history | 增量能力，保留 / Additive capability, retain |
| `/camera/videos`, `/camera/videos/{filename}` | GET | 视频元信息 / Video metadata | 读取 / Read | v1 内保留 / Retain in v1 |
| `/analysis/start`, `/analysis/stop` | POST | 产品实时分析 / Product realtime analysis | 有界会话与所有权 / Session ownership | v1 内保留 / Retain in v1 |
| `/analysis/result` | GET | 当前会话及结果 / Current session and result | 匹配 owner 的查询会续期 / Matching-owner polling renews ownership | v1 内保留 / Retain in v1 |
| `/analysis/frame` | GET | 精确会话/帧 JPEG / Exact session/frame JPEG | 无缓存读取 / Uncached read | v1 内保留 / Retain in v1 |

## 其他现行接口 / Other Current Surfaces

以下调用方来自仓库内使用点；外部调用方未完成普查，不能据“仓库内无调用”删除接口。GET 也可能占用硬件或触发扫描，不能仅按 HTTP 方法推断无副作用。

Consumers below are identified from this repository. External consumers have not been fully surveyed. An absent in-repo call is not evidence that a route can be removed. GET requests may hold hardware or trigger scans.

| 接口 / Surface | 仓库内调用方 / In-repo consumers | 稳定等级 / Stability | 写入或占用 / Writes or ownership | standalone / subordinate | 弃用条件 / Retirement |
|---|---|---|---|---|---|
| `/health`, `/api` | 服务诊断、HUD 版本 / Service diagnostics, HUD version | 现行发现入口 / Current discovery | GET；`/health` 仅为进程健康 / GET; process health only | 均注册 / Both | 调用方迁移后再审阅 / Review after consumer migration |
| `/api/camera/status` | 基础 API 测试；外部用户未知 / Base API tests; external use unknown | 兼容状态接口 / Compatibility status | GET；有独立 simulation 分支 / GET; separate simulation branch | 均注册 / Both | 盘点外部调用后决定 / Survey external consumers first |
| `/api/network/wifi`, `/scan`, `/profiles`, `/sta/connect`, `/profile/activate`（后四项相对于 `/api/network/wifi` / last four relative to `/api/network/wifi`） | React `NetworkPage.tsx` 与旧 `debug-system.js` / React and legacy network UI | 现行系统界面 / Current system UI | GET 查询/扫描；POST 切换及连接 / GET status/scan; POST switches/connections | standalone 注册，subordinate 不注册 / Standalone only | UI 替代与迁移完成后决定 / Requires replacement and UI migration |
| `/api/dev/debug/*` | React 相机台、HUD 脚本 / Camera console and HUD | Dev | 预览、抓拍、录像、设置、预设、文件及传感器工具 / Preview, capture, recording, settings, presets, files, sensors | 当前应用均注册；构造函数可裁剪，但应用传入 `include_dev_debug=true`；本机限制由现有配置决定 / Registered in both by the app; router construction supports exclusion but app passes true; existing locality configuration applies | Dev 变更须同步界面；不能成为集成方产品依赖 / Update UI together; no integrator product dependency |
| `/api/dev/analysis/*` | React 分析台、HUD / Analysis lab and HUD | Dev | 素材写入、解算、设置 / Assets, solves, settings | 与 Dev debug 相同 / Same registration as Dev debug | 同步调用方后可演进 / Evolve with consumers |
| `/api/dev/system/*` | React 系统台 / System console | Dev | GET 状态/配置；POST 配置/硬件命令 / GET diagnostics/config; POST config/commands | 均注册；现有 subordinate 本机限制可选 / Both; optional existing locality guard | 同步调用方后可演进 / Evolve with consumers |
| `/docs`, `/docs/dev`, `/docs/all`, `/openapi*.json` | 开发者与契约检查 / Developers and contract checks | 文档视图 / Documentation views | GET | 均注册 / Both | 与接口分组同步 / Track API grouping |

React 的 `requestDevDebugJson` 会把旧 `/api/debug/*` 字符串规范化到 Dev 前缀；这不表示服务端保留了旧路由。首页 HUD 的直接请求和共享系统常量已统一到 Dev 路径，不能依赖 React 包装替它们转发。机械对准占位接口及 `/api/system/*` 不再注册，`/api` 不再宣传 `system_legacy`。

React's `requestDevDebugJson` normalizes old debug strings to Dev paths; the server does not expose legacy routes. Direct HUD requests and the shared system constant now use Dev paths explicitly, since they do not traverse that React helper. Mount-alignment placeholders and `/api/system/*` are absent, and discovery no longer advertises `system_legacy`.

## 维护依据 / Maintenance Sources

- 路由注册 / Registration: `ogscope/web/api/main.py`, `ogscope/web/app.py`.
- HTTP 与模型 / HTTP and models: `ogscope/web/api/{core,camera,network,debug,analysis,system}/routes.py`, `ogscope/web/api/models/schemas.py`.
- 界面调用方 / UI consumers: `web/spa/src/apps/`, `web/static/js/`, `web/spa/src/shared/transport/http.ts`.
- 回归 / Regressions: `tests/unit/test_core_contract_api.py`, `test_dev_contract_api.py`, `test_api_boundary.py`.

每次迁移均需核对注册路由、OpenAPI、界面调用方和两种运行角色；不得把目标架构误写为已实现能力。

For each migration, recheck registered routes, OpenAPI, UI consumers and both runtime roles. Proposed architecture must remain distinguished from implemented behavior.
