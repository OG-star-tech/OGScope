# OGScope 测试指南（小团队版）

中文 | [English](testing-guide_EN.md)

本文档用于 1-2 人开发团队的测试落地，目标不是追求高覆盖率，而是用最小成本防止高频改动造成回归。

## 1. 测试目标

- 保护关键链路：服务可启动、核心 API 可用、调试控制台关键功能可用
- 减少回归排查时间：出现问题能快速定位是“代码逻辑”还是“硬件环境”
- 让测试可维护：每次改动只补充最相关的 1-2 个测试

## 2. 测试分层（推荐）

### 2.1 Unit（默认）

- 运行环境：本地或开发板均可
- 特点：不依赖真实硬件，执行快
- 方法：使用 `FakeCamera`、`monkeypatch`、临时目录 fixture

### 2.2 Integration（可选）

- 运行环境：本地优先，必要时开发板
- 特点：覆盖模块协作（路由 + 服务 + 文件）

### 2.3 Hardware（开发板专用）

- 运行环境：开发板
- 特点：只验证真实相机与系统依赖，不做大量业务分支覆盖

## 3. 当前最小测试网

已纳入的最小网包括：

- `tests/unit/test_api.py`
  - 根路径、健康检查、API 根接口、相机状态基础结构
- `tests/unit/test_debug_presets_api.py`
  - 预设空列表、保存、覆盖更新、删除
- `tests/unit/test_debug_files_api.py`
  - 文件列表、文件信息、删除联动删除 `.txt` 信息
- `tests/unit/test_debug_camera_api.py`
  - 调试相机状态、启动/停止、旋转、FPS、采样模式、图像质量、设置更新
- `tests/conftest.py`
  - `temp_debug_dir` fixture，确保测试不污染用户目录

## 4. 日常开发执行策略

### 4.1 本地改动后（每次）

```bash
poetry run pytest -q
```

### 4.2 提交前（推荐）

```bash
poetry run pytest -q
poetry run ruff check tests ogscope
```

### 4.3 开发板验证（涉及硬件改动时）

```bash
sudo systemctl restart ogscope
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

## 5. 编写新测试的规则（低压力）

- 每次功能改动，至少补 1 个“成功路径”测试
- 每次修 bug，必须补 1 个“回归测试”
- 优先测“最容易坏、影响最大”的接口
- 不追求一次写全，按迭代慢慢扩

## 6. 推荐优先级（后续增量）

下一批建议优先补：

1. `/api/camera/*` 的 simulation 分支冒烟
2. `DebugPresetService.apply_preset` 的异常路径
3. `DebugCameraService.set_size/set_fps` 的失败分支
4. 开发板上 3-5 个硬件 smoke 测试（启动、抓帧、重启后健康检查）

## 7. 常见问题

### 7.1 为什么不直接写大量硬件测试？

因为硬件测试慢、环境依赖重，不适合小团队高频提交。应把硬件测试集中在关键 smoke，业务分支放到 unit 层完成。

### 7.2 覆盖率只有 30% 左右是否可接受？

在当前阶段可以接受。比“覆盖率数字”更重要的是：关键接口有稳定回归保护，且每次改动都能快速验证。
