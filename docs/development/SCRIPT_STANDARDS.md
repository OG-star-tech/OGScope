# OGScope 脚本编写与调用规范

中文 | English (inline)

本规范用于统一 `scripts/` 与后续 `deploy/` 相关脚本的行为，降低双仓联动时的维护成本与误操作风险。

## 1. 作用域与边界

- OGScope 脚本只负责 OGScope 自身安装、升级、卸载、诊断与修复。
- 不在 OGScope 脚本中固化特定产品的联合部署逻辑。
- 联合部署编排由上层集成方实现，OGScope 只暴露稳定脚本入口和健康检查。

## 2. 统一命令模型

推荐统一入口（可逐步迁移）：

```bash
./scripts/stackctl.sh <command> [options]
```

标准子命令：

- `install`: 首次安装（支持最小安装与扩展安装）
- `update`: 增量升级
- `uninstall`: 卸载
- `doctor`: 只读诊断
- `repair`: 白名单修复
- `status`: 当前运行状态与版本摘要

## 3. 参数规范

所有脚本应优先支持以下通用参数：

- `--yes`: 非交互确认（CI/自动化）
- `--dry-run`: 仅检查，不落盘、不重启服务
- `--json`: 输出机器可读 JSON（便于在线管理调用）
- `--verbose`: 输出详细过程日志
- `--strict`: 将 warning 视为失败

兼容要求：

- 参数解析失败必须返回参数错误退出码（见第 4 节）。
- 未显式 `--yes` 时，危险操作必须二次确认。

## 4. 退出码规范

建议统一退出码语义：

- `0`: 成功
- `2`: 参数错误 / Invalid arguments
- `3`: 前置条件不满足（依赖/权限/环境）/ Preconditions not met
- `4`: 执行失败 / Execution failed
- `5`: 部分成功（存在未完成项）/ Partially successful

## 5. 幂等与安全要求

- 脚本必须可重复执行（idempotent）；重复执行不应破坏已有可用环境。
- 任何修改 `systemd`、`/etc/*`、网络配置的动作必须：
  - 在日志中显式说明将修改的目标；
  - 支持 `--dry-run` 预览；
  - 在失败时给出可恢复路径。
- 默认禁止在日志打印敏感值（密码、令牌、私钥）。

## 6. 输出与日志规范

- 人类可读日志：保持中英双语关键提示。
- 机器可读输出（`--json`）：至少包含
  - `success` (bool)
  - `code` (int)
  - `summary` (string)
  - `checks`/`actions` (array)
- 关键步骤建议使用稳定前缀：`INFO/WARN/ERROR`.

## 7. 文件与命名规范

- 脚本文件名使用 `kebab-case`。
- 入口脚本放 `scripts/`，复用函数放 `scripts/lib/`（若尚无可逐步建立）。
- 避免在多个脚本中复制粘贴同一系统操作逻辑，优先复用函数。

## 8. 权限与提权规范

- 顶层脚本在启动时检测权限，不在中间步骤隐式提权。
- 需要 root 的动作应集中执行，并在开始前一次性说明。
- 对 `sudo -n` 失败场景必须给出清晰提示与手动补救命令。

## 9. 外部集成约束

- OGScope 保持“核心能力提供方”定位；联合部署与产品侧编排由上层集成方负责。
- OGScope 脚本侧只承诺：
  - 稳定安装/升级/卸载接口；
  - 可诊断的健康与配置状态；
  - 向上游暴露 `core/v1` 与 [subordinate 模式](../contracts/subordinate-mode.md) 契约。

## 10. 提交前最小检查（脚本改动）

- `bash -n` 通过（新增/修改脚本）。
- 至少执行一次目标脚本 `--help` 或等价参数检查。
- 涉及运行路径改动时，验证 `systemd` 与健康检查可用：
  - `systemctl status ogscope`
  - `curl -s http://127.0.0.1:8000/health`

