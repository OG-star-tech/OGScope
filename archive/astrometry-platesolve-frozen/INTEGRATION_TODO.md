# 未来若重新引入 astrometry 板解 — 检查清单 / Integration checklist (if revived)

以下条目在快照合入 `feature/legacy protocol-client` 时**未与当前主线对齐**，复活开发时需逐项处理。

- [ ] 在 [`ogscope/web/api/models/schemas.py`](../../ogscope/web/api/models/schemas.py) 中补充或核对 `PlateSolveRequest` / `PlateSolveResponse`（快照中的 `routes.py` 曾依赖这些类型；分支上可能未完整提交）。
- [ ] 在 [`ogscope/web/api/main.py`](../../ogscope/web/api/main.py) 注册 `platesolve` 路由，并确认前缀与 OpenAPI 标签。
- [ ] 在 [`ogscope/config.py`](../../ogscope/config.py) 中增加 `platesolve_*` 配置项（routes 中 `getattr(settings, "platesolve_...", None)`）。
- [ ] 依赖：`astrometry` 与系统/镜像约束；与现有 `plate_solve` 包职责划分文档化。
- [ ] 修复/补充单元测试路径，并决定是否移回 `tests/unit/`。
- [ ] 与 CI、Docker、部署脚本统一（`deploy_platesolve.sh` 内主机与路径为示例）。

**在此之前请勿将本目录代码当作可运行主线的一部分。**
