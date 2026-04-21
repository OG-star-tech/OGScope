# Architecture Quick Checklist

中文 | [English](ARCHITECTURE_QUICK_CHECKLIST_EN.md)

提交 API 或架构相关改动前，请快速自检以下项目（建议 2 分钟内完成）。

## 1) 路由与分域

- [ ] 标准契约仅使用 `"/api/core/v1/*"`。
- [ ] 开发接口仅使用 `"/api/dev/*"`。
- [ ] 未重新引入旧前缀：`"/api/debug/*"`、`"/api/analysis/*"`、`"/api/system/*"`。
- [ ] `/docs`、`/docs/dev`、`/docs/all` 展示范围与本次改动一致。

## 2) 分层边界

- [ ] `routes.py` 只保留 HTTP 适配（参数解析、异常映射、响应序列化）。
- [ ] 业务逻辑放在 `domain/*` 或 `core/application/*`，而不是路由层。
- [ ] 跨域复用优先走 `domain/shared/*`，没有复制粘贴同类逻辑。
- [ ] 没有新增 `domain -> web.api` 反向依赖。

## 3) 文档同步

- [ ] 已同步更新契约文档：
  - `docs/contracts/core-rest-v1.md`、`docs/contracts/core-rest-v1_EN.md`
  - `docs/contracts/dev-rest-v1.md`、`docs/contracts/dev-rest-v1_EN.md`
  - `docs/contracts/core-compatibility-matrix.md`（段内中英）
- [ ] 若接口分组或标签变更，已同步检查：
  - `ogscope/web/api/main.py`
  - `ogscope/web/app.py`
- [ ] 若目录结构或开发约定变更，已同步更新：
  - `docs/API_ARCHITECTURE.md`、`docs/API_ARCHITECTURE_EN.md`
  - `docs/development/README.md`
  - `docs/development/README_EN.md`
  - `CONTRIBUTING.md`、`CONTRIBUTING_EN.md`

## 4) 基础验证

- [ ] 后端单测通过：`poetry run pytest tests/unit -q`
- [ ] 前端构建通过（如涉及前端）：`cd web/spa && npm run build`
- [ ] API 基本可达：
  - `curl http://127.0.0.1:8000/api`
  - `curl http://127.0.0.1:8000/api/core/v1/system/status`
  - `curl http://127.0.0.1:8000/api/dev/debug/camera/status`

## 5) 提交规范

- [ ] 提交信息使用中英文双语（中文标题 / English title）。
- [ ] 提交内容与标题一致，避免把无关变更打包进同一个提交。
- [ ] 若是破坏性改动，明确写明影响范围与迁移方式。
