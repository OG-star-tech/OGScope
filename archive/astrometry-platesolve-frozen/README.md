# Astrometry 板解与 UI 构建工具 — 封存快照 / Frozen snapshot (astrometry plate solve + UI tools)

## 状态 / Status

**封存（FROZEN）— 非主线代码 / Not part of the active codebase**

本目录为从 Git 分支 `feature/legacy protocol-client` 截取的**只读参考快照**（见 [`SOURCE_COMMIT.txt`](SOURCE_COMMIT.txt)），用于保留一度误与 legacy hardware protocol 工作混在同一分支上的 **第二套板解方案**（基于 Python `astrometry` 封装）及 Docker UI 构建脚本。

**当前产品解算路径以 [`ogscope/algorithms/plate_solve/`](../../ogscope/algorithms/plate_solve/)（如 Tetra3）与既有 Analysis API 为准；不要在本仓库中并行维护两套运行时解算实现。**

This tree is a **read-only reference**. Production solving uses [`ogscope/algorithms/plate_solve/`](../../ogscope/algorithms/plate_solve/) and the existing analysis APIs. **Do not wire this snapshot into `ogscope` imports or FastAPI routes without an explicit product decision and refactor.**

## 为何封存 / Why archived

- 与主线 **重复**：同一仓库内不应长期存在两套板解栈。
- 历史提交属 **失误合并范围**：保留代码供将来需要时参考，而非当前迭代目标。

## 目录内容 / Contents

| 路径 | 说明 |
|------|------|
| `ogscope/algorithms/plate_solver.py` | 单文件 astrometry 封装（与 `plate_solve/` 包无关） |
| `ogscope/web/api/platesolve/` | 曾计划的 `/api/platesolve/*` 路由（未并入当前 `main.py`） |
| `deploy_platesolve.sh` | 向远端部署并 `poetry add astrometry` 的示例脚本 |
| `docker/` | UI builder 容器与 compose |
| `scripts/build_ui_container.sh`, `ui_builder_shell.sh` | 容器内构建前端 |
| `tests/unit/test_platesolve.py` | 针对上述 API 的测试（**不在**默认 `pytest tests/` 路径下） |
| `tests/images/*.png` | 测试图像 |

## 给开发者与 AI 的约束 / Rules

1. **默认不要修改**本目录下文件；Issue/任务中明确写「恢复 astrometry 板解」或「整理 archive」时再动。
2. **不要**将 `archive/.../ogscope/` 加入 `PYTHONPATH` 或复制进 `ogscope/` 包内除非走完整集成评审。
3. 恢复开发时请先读 [`INTEGRATION_TODO.md`](INTEGRATION_TODO.md)。

## 与 Cursor 规则的关系

仓库内 [`.cursor/rules/archive-astrometry-platesolve-frozen.mdc`](../../.cursor/rules/archive-astrometry-platesolve-frozen.mdc) 提示：除非用户明确要求，否则勿编辑本快照。
