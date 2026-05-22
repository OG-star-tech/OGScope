# OGScope 开发指南（开发板部署与调试）

中文 | [English](README_EN.md)

完整 `docs/` 中英索引（A–E 分组）见：[文档索引](../README.md) | [English](../README_EN.md)。

本文档面向项目成员与协作者，说明 OGScope 在 **Raspberry Pi Zero 2W** 等开发板环境中的实际运行方式、依赖要求与标准调试流程。

### 文档地图（与索引分组一致）

- **A 入门与总览**：本页为主指南；[快速开始](../QUICK_START.md) | [English](../QUICK_START_EN.md)
- **B 板上运维**：[WiFi](wifi-nm.md) | [English](wifi-nm_EN.md)；[星库](plate-solve-data.md)；[稳定性](ogscope-service-hardening.md)；[BOM](../hardware/bom.md) | [English](../hardware/bom_EN.md)
- **C API/契约/测试**：[API 架构（含 FastAPI 入口）](../API_ARCHITECTURE.md) | [English](../API_ARCHITECTURE_EN.md)；[系统架构](../architecture/OGSCOPE_SYSTEM_ARCHITECTURE_BILINGUAL.md)；[Core 契约](../contracts/core-rest-v1.md) | [English](../contracts/core-rest-v1_EN.md)；[Dev 契约](../contracts/dev-rest-v1.md) | [English](../contracts/dev-rest-v1_EN.md)；[兼容矩阵](../contracts/core-compatibility-matrix.md)；[自检](ARCHITECTURE_QUICK_CHECKLIST.md) | [English](ARCHITECTURE_QUICK_CHECKLIST_EN.md)；[测试](testing-guide.md) | [English](testing-guide_EN.md)
- **D 跨仓**：[CROSS_PROJECT_COLLAB.md](CROSS_PROJECT_COLLAB.md) | [English](CROSS_PROJECT_COLLAB_EN.md)；[外部集成契约](OG_ZENIT_COLLAB_MINIMAL_CONTRACT_ZH.md) | [English](OG_ZENIT_COLLAB_MINIMAL_CONTRACT.md)
- **E 工具与贡献**：[脚本规范](SCRIPT_STANDARDS.md)；[调试控制台](../DEBUG_CONSOLE.md) | [English](../DEBUG_CONSOLE_EN.md)；[贡献指南](../../CONTRIBUTING.md) | [English](../../CONTRIBUTING_EN.md)

当前推荐流程为：**本地编辑代码 -> 上传到开发板 -> 使用 `systemd` 重启服务验证**。  
该流程与实际硬件运行环境一致，适合涉及相机与系统库依赖的场景。

## 0. 部署速查（爱好者复刻）

本节与 **§1–§11** 的关系：**只列最常用命令与检查项**；Poetry/PEP 668、镜像选项、卸载与排错原理见后文对应章节。

### 0.1 系统要求

- 单板：**ARM**（`aarch64` 或 `armhf`），推荐 **Raspberry Pi Zero 2W**  
- 系统：**Debian/apt** 系镜像（与 `picamera2`/`libcamera` 文档一致；脚本会读 `/etc/os-release`，见 **§1.4**）  
- Python：**3.10+**（以 `pyproject.toml` 为准）  
- 网络：首次安装需拉取依赖；浏览器访问 Web 需可达设备 **TCP 8000**（按需防火墙放行）

### 0.2 首次安装

```bash
cd /path/to/OGScope
chmod +x scripts/install.sh
./scripts/install.sh
```

最小化安装（仅主服务与运行时依赖）可使用：

```bash
cd /path/to/OGScope
chmod +x scripts/install-min.sh
./scripts/install-min.sh
```

说明摘要：默认 `poetry install --only main`；国内网络可 `**export OGSCOPE_MIRROR=cn**`；低配板可 `**OGSCOPE_APT_SLOW=1**`。完整选项见 **§1.4**。安装后：`sudo systemctl start ogscope`。
部署态主配置文件为 `/etc/ogscope/ogscope.env`，网络专用配置为 `/etc/ogscope/network.env`。

### 0.3 网络与 WiFi（AP/STA）

- `**install.sh`** 会安装 `network-manager`、`avahi-daemon`，并执行 `**ogscope-network-init.sh init**`（NM 连接、`/etc/ogscope/network.env`、sudoers、主机名与 `hosts` 等），除非 `**OGSCOPE_SKIP_NETWORK_INIT=1**`。
- 同次安装会写入 `**ogscope-network-boot.service**`（开机无线网络引导：无可用 STA 则回 AP），除非 `**OGSCOPE_SKIP_NETWORK_BOOT=1**`。
- **日常仅同步代码与依赖**优先 `**./scripts/board-update.sh`**；全量重装或改系统级依赖时再跑 `**install.sh**`（见 **§0.5**）。
- 热点 SSID/密码、调试页 `**/debug/system`**、API、**开机引导与运行时 STA 回滚** 的分工：**唯一详解**见 **[wifi-nm.md](wifi-nm.md)**。

### 0.4 星图解算数据

将 `**default_database.npz`** 放到 `**data/plate_solve/**`（不随仓库分发）。放置与配置见 [plate-solve-data.md](plate-solve-data.md)。

### 0.5 日常更新

```bash
cd /path/to/OGScope
chmod +x scripts/board-update.sh
# 可选：OGSCOPE_GIT_PULL=1  OGSCOPE_MIRROR=cn
# 开发模式（更详细日志）：OGSCOPE_DEVELOPMENT_MODE=1 ./scripts/board-update.sh
./scripts/board-update.sh
```

详情见 **§6.2**。

### 0.6 卸载与健康检查

- 卸载服务与 `.venv`：见 **§6.3**（`scripts/uninstall.sh`）  
- 健康检查与日志：

```bash
curl -s http://127.0.0.1:8000/health
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

### 0.7 常见故障（简表）


| 现象                       | 处理方向                                                   |
| ------------------------ | ------------------------------------------------------ |
| `ImportError: picamera2` | 用 `apt` 装相机栈；venv 由 `install.sh` 配置（**§1.2、§3**）       |
| PEP 668 / 系统 pip 被拒      | 只用项目 `.venv`，勿在系统 Python 上混装（**§1.2**）                 |
| 服务无法启动                   | 查 `WorkingDirectory`、`ExecStart`、`journalctl`（**§10**） |


## 1. Python 版本与项目依赖

### 1.1 Python 版本基线

- 项目版本约束以 `pyproject.toml` 为准：`python = "^3.10"`
- 建议开发板使用 Python 3.10 及以上版本
- 若其他文档出现 `3.9+`，应视为历史描述

### 1.2 Poetry、PEP 668 与虚拟环境（必读）

- **必须使用 Poetry 创建的项目内虚拟环境**（`.venv`），**禁止**全局设置 `virtualenvs.create false` 后在系统 Python 上混装依赖；否则易触发 **PEP 668**（发行版保护系统 site-packages，`pip`/`poetry` 无法改写系统包）。
- 开发板推荐由 `scripts/install.sh` 统一写入：`virtualenvs.create true`、`virtualenvs.in-project true`，并尽量启用 `**virtualenvs.options.system-site-packages true`**，使 venv 能解析通过 `apt` 安装的 `picamera2` 等系统包。
- **生产/板端**默认仅安装运行时依赖：`poetry install --only main`（脚本默认）。若需 pytest、类型检查等，在开发机或板上设置 `OGSCOPE_INSTALL_DEV=1` 后重装。

### 1.3 安装 Poetry 与 Python 依赖

```bash
# 进入项目目录
cd /path/to/OGScope

# 安装 Poetry（若尚未安装）
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"

# 开发机：完整依赖（含 dev）
poetry install

# 开发板（手动维护时）：仅运行时依赖，与 install.sh 默认一致
# poetry install --no-interaction --only main
```

### 1.4 使用安装脚本（推荐首次部署）

仓库提供 `scripts/install.sh`，用于在开发板执行一次性环境准备。脚本会：

- 读取 `/etc/os-release` 识别发行版，**仅支持 Debian/Ubuntu 系**（含 **Raspberry Pi OS**）；非该系将退出，避免误改软件源
- 安装系统依赖与 Poetry
- 配置 Poetry 使用项目 `.venv` 与 `system-site-packages`（Poetry 版本支持时）
- 默认执行 `poetry install --only main`（设 `OGSCOPE_INSTALL_DEV=1` 可装 dev）
- 可选 `OGSCOPE_APT_SLOW=1`：分批 `apt` 并在批次间暂停，减轻低配板内存压力
- `**OGSCOPE_MIRROR`**：`auto`（默认，按 `LANG`/`LC_*` 与系统时区启发）、`cn`（中国大陆镜像：apt 清华源 + PyPI 清华）、`international`（不替换 apt，PyPI 走默认）。在国内但语言为英文时，请显式 `export OGSCOPE_MIRROR=cn`。
- 创建 `logs`、`uploads`、`data/plate_solve` 等目录
- 生成/更新 `systemd` 服务（`ogscope.service`）
- 注入 `PYTHONPATH` 与 `LD_LIBRARY_PATH`（按实际存在的路径）
- 启用服务开机自启

执行方式：

```bash
cd /path/to/OGScope
chmod +x scripts/install.sh
./scripts/install.sh
```

### 1.5 依赖维护建议

- 保持 `poetry.lock` 与仓库同步
- 每次上传较大改动后，在板上执行 `./scripts/board-update.sh`，或手动 `poetry install --only main` 后 `sudo systemctl restart ogscope`
- 服务运行时优先使用固定虚拟环境解释器（见第 5 节）

## 2. 系统环境依赖（重点）

OGScope 除 Python 包依赖外，还依赖开发板系统层的相机生态（如 `picamera2`/`libcamera`）。

建议系统具备以下基础组件（按发行版实际包名调整）：

- Python 与构建工具：`python3`、`python3-venv`、`python3-dev`、`build-essential`
- 相机相关：`python3-picamera2`（依赖系统 `libcamera` 运行库）
- 图像相关：`libjpeg`、`libpng`、OpenCV 对应系统库

示例：

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-dev build-essential \
  python3-picamera2 libjpeg-dev libpng-dev libopencv-dev
```

## 3. 为什么虚拟环境里仍要设置 `PYTHONPATH`

这是本项目在开发板上的关键运行点。

- OGScope 通过 Poetry 虚拟环境运行，但相机相关包常通过 `apt` 安装在系统路径（如 `/usr/lib/python3/dist-packages`）
- 这些系统路径默认不一定在 Poetry 虚拟环境的 `sys.path` 中
- 结果是：服务运行于虚拟环境时，可能找不到 `picamera2` 等系统包

**与 `system-site-packages` 的关系**：启用后，venv 的 `sys.path` 会包含系统 site-packages，一般即可 `import picamera2`；`systemd` 里仍保留 `PYTHONPATH`，用于覆盖不同发行版下 `/usr/local/lib/python3.x/dist-packages` 等路径，二者叠加不冲突。

因此在服务配置中显式注入 `PYTHONPATH`，将系统 Python 包路径加入解释器搜索路径，例如：

```ini
Environment=PYTHONPATH=/usr/lib/python3/dist-packages:/usr/local/lib/python3.13/dist-packages
```

同时，`libcamera` 的动态链接库也可能不在默认加载路径中，通常需要：

```ini
Environment=LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu
```

## 4. 服务启动链路与脚本使用状态

### 4.1 当前实际启动链路（在用）

1. `systemd` 启动服务 `ogscope`
2. `ExecStart` 执行 `python -m ogscope.main`（通常为虚拟环境解释器）
3. `ogscope/main.py` 启动 Uvicorn，加载 `ogscope.web.app:app`

### 4.2 仓库脚本状态说明（避免误用）

- `scripts/install.sh`
  - 作用：安装依赖并生成 service
  - 状态：安装辅助脚本，不是运行时自动调用入口
- `scripts/board-update.sh`
  - 作用：已安装环境下的增量更新（可选 `OGSCOPE_GIT_PULL=1` 执行 `git pull`、`poetry install`、重启 `ogscope`）
  - 状态：日常部署推荐入口
- `scripts/uninstall.sh`
  - 作用：停止并移除 `ogscope` systemd 单元、可选删除 `.venv`；默认保留 `logs/`、`data/` 等；需确认（交互输入 `YES` 或 `OGSCOPE_UNINSTALL_CONFIRM=1`）
  - 状态：卸载辅助脚本；不卸载系统 apt 包与全局 Poetry
- `scripts/start_debug_console.sh`
  - 作用：手动设置 `PYTHONPATH`/`LD_LIBRARY_PATH` 后前台启动
  - 状态：手动调试辅助脚本，不是默认生产启动链路
- `poetry run ...` 与 `scripts/*.sh`
  - 作用：开发效率命令与板端运维入口
  - 状态：推荐直接使用，不再依赖 Makefile 包装

## 5. 配置 `systemd` 服务与开机自启

服务文件建议路径：

- `/etc/systemd/system/ogscope.service`

参考模板（请替换为实际用户名与路径）：

```ini
[Unit]
Description=OGScope Service
After=network.target

[Service]
Type=simple
User=<your-user>
WorkingDirectory=<project-dir>
Environment=PYTHONPATH=/usr/lib/python3/dist-packages:/usr/local/lib/python3.13/dist-packages
Environment=LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu
Environment=OGSCOPE_RELOAD=false
Environment=OGSCOPE_LOG_LEVEL=INFO
ExecStart=<venv-path>/bin/python -m ogscope.main
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启用与启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable ogscope
sudo systemctl start ogscope
sudo systemctl status ogscope
```

## 6. 代码更新与部署流程（团队统一）

### 6.1 首次部署

1. 拉取项目代码
2. 执行 `scripts/install.sh`
3. 启动并验证 `ogscope` 服务

### 6.2 日常代码更新（推荐）

代码更新后（`git pull` 或手动上传）可一键执行（镜像策略与 `install.sh` 相同，通过 `OGSCOPE_MIRROR` 控制）：

```bash
cd /path/to/OGScope
chmod +x scripts/board-update.sh
# 若需先拉取远端代码（仅 git 仓库）：OGSCOPE_GIT_PULL=1 ./scripts/board-update.sh
# 中国大陆：OGSCOPE_MIRROR=cn ./scripts/board-update.sh
# 开发模式（更详细日志）：OGSCOPE_DEVELOPMENT_MODE=1 ./scripts/board-update.sh
./scripts/board-update.sh
```

或手动执行：

```bash
# 进入项目目录
cd /path/to/OGScope

# 同步依赖（有 pyproject.toml/poetry.lock 变更时必须执行；板端建议仅 main）
poetry install --no-interaction --only main

# 重启服务使新代码生效
sudo systemctl restart ogscope

# 检查状态和日志
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

说明：

- 若仅前端模板/静态文件变更，通常不需要 `poetry install`
- 若服务文件配置有改动，需先 `sudo systemctl daemon-reload`
- 脚本会同步主服务 `ExecStart` 与已安装的 `**ogscope-network-boot.service**` 内 `ExecStart`（项目目录变更时）；未安装开机单元则跳过

### 6.3 卸载服务与本地环境（`scripts/uninstall.sh`）

在需要**移除 systemd 服务**、清理项目内 `**.venv`**，或换目录重装时使用 `scripts/uninstall.sh`。脚本**不会**卸载系统已通过 `apt` 安装的包（如 `python3-picamera2`），也**不会**卸载用户级全局 **Poetry**；仅处理 OGScope 服务单元与项目目录内可选内容。

**会执行的操作 / What it does**

- `systemctl stop` / `disable` `ogscope`
- 删除 `/etc/systemd/system/ogscope.service`（若存在）
- 若存在 `**ogscope-network-boot.service`**：`stop` / `disable` 并删除该 unit（与 `install.sh` 安装的引导一致）
- 若存在 `**/etc/systemd/system/ogscope.service.d/ogscope-network-env.conf**`：删除该 drop-in（空目录会尝试 `rmdir`）
- `daemon-reload`
- 默认删除项目根目录下的 `**.venv**`（可用环境变量保留，见下）

**默认保留 / Kept by default**

- `logs/`、`uploads/`、`data/`（含 `data/plate_solve` 等）；若需一并删除，须显式开启（见下）

**环境变量 / Environment**


| 变量                                | 含义                                             |
| --------------------------------- | ---------------------------------------------- |
| `OGSCOPE_UNINSTALL_CONFIRM=1`     | **非交互场景必须设置**（如 CI、脚本），否则脚本在非 TTY 下直接退出        |
| `OGSCOPE_UNINSTALL_KEEP_VENV=1`   | 保留 `.venv`，不删除虚拟环境                             |
| `OGSCOPE_UNINSTALL_REMOVE_DATA=1` | **危险**：删除 `logs/`、`uploads/`、`data/`（含星库等用户数据） |


**交互确认 / Interactive**：在终端前台运行时，若未设置 `OGSCOPE_UNINSTALL_CONFIRM=1`，需输入全大写 `**YES`** 才会继续。

```bash
cd /path/to/OGScope
chmod +x scripts/uninstall.sh

# 交互：按提示输入 YES
./scripts/uninstall.sh

# 非交互：确认后执行
OGSCOPE_UNINSTALL_CONFIRM=1 ./scripts/uninstall.sh

# 保留虚拟环境，仅移除服务
OGSCOPE_UNINSTALL_CONFIRM=1 OGSCOPE_UNINSTALL_KEEP_VENV=1 ./scripts/uninstall.sh

# 同时删除日志与数据目录（慎用）
OGSCOPE_UNINSTALL_CONFIRM=1 OGSCOPE_UNINSTALL_REMOVE_DATA=1 ./scripts/uninstall.sh
```

卸载后若需再次部署，重新执行 `./scripts/install.sh` 即可。

## 7. PyCharm 远程开发（当前实践）

当前采用的是 **“本地 IDE 编辑 + 手动部署到开发板”** 模式，而不是由 IDE 直接接管远程运行。

推荐标准流程：

1. 在 PyCharm 本地完成代码修改
2. 将变更上传到开发板
3. 执行 `sudo systemctl restart ogscope`
4. 通过 `status` 与 `journalctl` 检查启动结果
5. 通过 Web/API 完成功能验证

## 8. 调试 SOP（建议团队统一）

```bash
# 上传代码后重启服务
sudo systemctl restart ogscope

# 查看服务状态
sudo systemctl status ogscope

# 跟踪运行日志
sudo journalctl -u ogscope -f
```

接口快速验证：

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api
```

## 9. API 文档与在线调试

### 9.1 文档入口

服务启动后，FastAPI 自动提供交互式 API 文档：


| 地址                                | 说明                    |
| --------------------------------- | --------------------- |
| `http://<host>:8000/docs`         | Swagger UI — 交互式接口测试  |
| `http://<host>:8000/redoc`        | ReDoc — 结构化接口文档       |
| `http://<host>:8000/openapi.json` | OpenAPI Schema (JSON) |


### 9.2 API 分组（Tags）

所有接口在文档中按模块分组展示，分组通过路由注册时的 `tags` 参数控制：


| 分组               | 模块                          | 说明                            |
| ---------------- | --------------------------- | ----------------------------- |
| Camera - 相机      | `ogscope.web.api.camera`    | 相机控制与图像获取                     |
| Alignment - 极轴校准 | `ogscope.web.api.alignment` | 极轴校准流程与状态                     |
| Network - 网络     | `ogscope.web.api.network`   | WiFi AP/STA 与网络切换             |
| Core - 标准契约      | `ogscope.web.api.core`      | 对外稳定契约（`/api/core/v1/*`）      |
| Dev - 系统状态       | `ogscope.web.api.system`    | 开发者系统状态（`/api/dev/system/*`）  |
| Dev - 调试工具       | `ogscope.web.api.debug`     | 开发者调试能力（`/api/dev/debug/*`）   |
| Dev - 分析实验       | `ogscope.web.api.analysis`  | 分析实验接口（`/api/dev/analysis/*`） |


分组在 `ogscope/web/api/main.py` 中通过 `include_router()` 的 `tags` 参数指定，描述信息在 `ogscope/web/app.py` 的 `openapi_tags` 中定义。

### 9.3 新增 API 模块时的文档配置

新增一个 API 模块后，需在两处添加配置，以确保文档正确分组：

1. `**ogscope/web/app.py**` — 在 `openapi_tags` 列表中添加分组描述：

```python
{
    "name": "NewModule - 新模块",
    "description": "模块说明 / Module description",
},
```

1. `**ogscope/web/api/main.py**` — 注册路由时指定 `tags`：

```python
router.include_router(new_router, tags=["NewModule - 新模块"])
```

### 9.4 ReDoc 自定义说明

项目使用自定义 ReDoc 路由（固定版本 `redoc@2.1.5`），而非 FastAPI 默认的 `redoc@next`，以避免预发布版本不稳定导致页面空白。相关配置见 `ogscope/web/app.py` 中的 `custom_redoc()` 函数。

### 9.5 API 变更防误提清单（提交前）

为减少结构复杂化后的误提交，涉及 API 改动时请在提交前检查：

1. 旧前缀 `"/api/debug/*"`, `"/api/analysis/*"`, `"/api/system/*"` 未被重新引入。
2. 开发接口全部在 `"/api/dev/*"`；标准契约全部在 `"/api/core/v1/*"`。
3. `routes.py` 仅保留 HTTP 适配，业务逻辑放在 `domain/*` 或 `core/application/*`。
4. 至少跑一轮相关测试（建议 `poetry run pytest tests/unit -q`）。
5. 同步更新契约文档：
  - `docs/contracts/core-rest-v1.md`、`docs/contracts/core-rest-v1_EN.md`
  - `docs/contracts/dev-rest-v1.md`、`docs/contracts/dev-rest-v1_EN.md`
  - `docs/contracts/core-compatibility-matrix.md`（段内中英，单文件）

## 10. 常见故障排查

若服务启动失败，优先检查：

- `WorkingDirectory` 是否指向项目根目录
- `ExecStart` 是否使用正确的虚拟环境 Python
- `PYTHONPATH` 是否包含系统 `dist-packages`
- `LD_LIBRARY_PATH` 是否包含 `libcamera` 相关库路径
- 最近代码上传是否完整，依赖是否已重新安装
- `**No module named 'scipy'**`：`board-update.sh` / `install.sh` 会在 `poetry install` 后校验并自动 `--no-cache` 重试与 pip 补装；若仍失败，删除 `.venv` 后执行 `OGSCOPE_MIRROR=cn ./scripts/board-update.sh`（或重装 `./scripts/install.sh`）

## 11. 常用命令速查

```bash
# 安装/更新依赖（开发机）；板端可用 ./scripts/board-update.sh
poetry install

# 前台手动启动（调试时）
poetry run python -m ogscope.main

# systemd 管理
sudo systemctl restart ogscope
sudo systemctl status ogscope
sudo journalctl -u ogscope -f

# 卸载服务与 .venv（详见 §6.3；需确认或 OGSCOPE_UNINSTALL_CONFIRM=1）
# ./scripts/uninstall.sh
# OGSCOPE_UNINSTALL_CONFIRM=1 ./scripts/uninstall.sh
```

