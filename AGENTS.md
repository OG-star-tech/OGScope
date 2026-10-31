# OGScope 项目边界 / OGScope project boundary

OGScope is an independent, generic camera, solver and Core API provider. Keep all consumers anonymous in this repository and its commit messages, branch/tag names, PR titles/bodies, documentation, fixtures and distribution artifacts.
OGScope 是独立通用的相机、解算器和 Core API 服务方。本仓及提交信息、分支/标签、PR 标题正文、文档、样例与发布包中的消费方必须匿名。

Consumer product names, repository links, internal modules, application workflows, paired revisions, deployment receipts and cross-repository integration suites belong in the consumer's repository. Do not copy or disguise them here. Generic API examples and provider-only tests remain here; runtime contracts and compatibility must be preserved.
消费方产品名、仓库链接、内部模块、业务流程、配套版本、部署记录和跨仓集成测试由消费方仓库持有，禁止复制或变形放入本仓。仅保留通用 API 示例与服务方测试，保持运行契约和兼容性。

Before committing, run `python3 scripts/check_project_independence.py --staged --message-file <message-file>`. Before pushing or opening/editing/merging a PR, also check the new commit range and the exact PR title/body with `--commit-range` and `--event-file`. Never disable a failing boundary check; remove the cause. Install both hooks with `pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`.
提交前必须检查完整暂存索引和最终提交信息；推送、创建/编辑/合并 PR 前还须检查新增提交及最终 PR 元数据。失败必须清理原因，禁止跳过；安装 pre-commit、commit-msg 与 pre-push 三种钩子。

The scanner detects reserved fingerprints without storing the original product names. It supplements a semantic review of ownership; a keyword-free consumer workflow still belongs outside this project. The `project-independence` CI job should be a required status check on protected integration branches.
扫描器仅保存受限词指纹，不保存原名；仍须人工审阅职责边界，不能以没有关键词为由混入消费方业务。受保护集成分支应将 `project-independence` 设为必需检查。
