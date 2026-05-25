# 贡献指南

中文 | [English](CONTRIBUTING_EN.md)

感谢你对 OGScope 项目的关注！我们欢迎任何形式的贡献。

## 如何贡献

### 报告 Bug

如果你发现了 bug，请：

1. 在 [Issues](https://github.com/OG-star-tech/OGScope/issues) 页面搜索是否已有相关问题
2. 如果没有，创建新 Issue，包含：
   - 详细的问题描述
   - 复现步骤
   - 预期行为和实际行为
   - 运行环境信息（OS、Python 版本等）
   - 相关日志或截图

### 提出新功能

1. 在 Issues 中创建功能请求
2. 说明功能的用途和场景
3. 等待维护者反馈

### 提交代码

1. **Fork 项目**
   ```bash
   # 在 GitHub 上点击 Fork 按钮
   git clone https://github.com/OG-star-tech/OGScope.git
   cd OGScope
   ```

2. **基于 develop 创建功能分支 / Branch from develop**
   ```bash
   git fetch origin
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

3. **安装开发依赖**
   ```bash
   poetry install
   poetry run pre-commit install  # 安装 Git hooks
   ```

4. **编写代码**
   - 遵循项目代码规范
   - 添加必要的测试
   - 更新相关文档

5. **运行测试和检查**
   ```bash
   poetry run pytest
   poetry run black ogscope tests
   poetry run ruff check ogscope tests
   poetry run mypy ogscope
   ```
   同时建议按 [Architecture Quick Checklist](docs/development/ARCHITECTURE_QUICK_CHECKLIST.md)（[English](docs/development/ARCHITECTURE_QUICK_CHECKLIST_EN.md)）做一次提交前自检，尤其是 API/架构改动。

6. **提交更改**
   ```bash
   git add .
   git commit
   ```
   
   提交信息格式（建议中英文双语）：
   - 标题：`中文一句话 / English one-liner`
   - 正文：按要点写 1~3 条中文/英文对应说明

   提交类型前缀：
   - `feat:` 新功能
   - `fix:` Bug 修复
   - `docs:` 文档更新
   - `style:` 代码格式调整
   - `refactor:` 代码重构
   - `test:` 测试相关
   - `chore:` 构建/工具变更

7. **推送到 GitHub**
   ```bash
   git push origin feature/your-feature-name
   ```

8. **创建 Pull Request**
   - 在 GitHub 上创建 PR
   - 填写 PR 模板
   - 等待代码审查

## 代码规范

### Python 代码风格

- 使用 **Black** 格式化（行长度 88）
- 使用 **Ruff** 进行代码检查
- 添加类型注解（MyPy）
- 遵循 **PEP 8** 规范

### 文档规范

- 使用 Markdown 格式
- 中文文档使用全角标点（英文除外）
- 代码示例应可运行

### 测试规范

- 所有新功能必须有测试
- 测试覆盖率应保持在 80% 以上
- 使用合适的测试标记（unit/integration/hardware）

### API 改动防误提规范（重要）

- 标准契约固定在 `"/api/core/v1/*"`。
- 开发接口固定在 `"/api/dev/*"`，不要再引入 `"/api/debug/*"`、`"/api/analysis/*"`、`"/api/system/*"` 旧路径。
- `routes.py` 仅保留 HTTP 适配逻辑，业务逻辑下沉到 `domain/*` 与 `core/application/*`。
- API 相关改动需同步更新：
  - `docs/contracts/core-rest-v1.md`、`docs/contracts/core-rest-v1_EN.md`
  - `docs/contracts/dev-rest-v1.md`、`docs/contracts/dev-rest-v1_EN.md`
  - `docs/contracts/core-compatibility-matrix.md`（段内中英）

## Git 分支策略

| 分支 | 用途 |
|------|------|
| `main` | 稳定发布线；仅通过 PR 从 `develop` 合入 |
| `develop` | **唯一集成分支**；日常开发与板端联调基准 |
| `feature/*` | 功能/重构；从 `develop` 拉出，PR 合回后删除 |
| `fix/*` | 小修复；可合 `develop`，紧急时可 hotfix 合 `main` |

流程：`feature/*` → PR → `develop` → 定期 PR → `main`。

**已废弃**：不再使用 `dev`、`dev-latest` 双集成分支。

## 开发流程

1. **选择 Issue**: 从 Issues 列表中选择要解决的问题
2. **开发**: 在本地开发和测试
3. **提交 PR**: 创建 Pull Request
4. **代码审查**: 等待维护者审查
5. **合并**: 审查通过后合并到 `develop`（发版时再合 `main`）

## 代码审查标准

- 代码功能正确
- 代码风格符合规范
- 有足够的测试覆盖
- 文档完整清晰
- 没有破坏性变更（或已充分说明）

## 社区准则

- 尊重他人
- 积极反馈
- 建设性讨论
- 欢迎新手

## 获取帮助

如果你在贡献过程中遇到问题：

- 查看 [文档索引](docs/README.md)（[English](docs/README_EN.md)）与 [开发文档](docs/development/README.md)
- 在 [Discussions](https://github.com/OG-star-tech/OGScope/discussions) 提问
- 联系维护者

感谢你的贡献！🎉

