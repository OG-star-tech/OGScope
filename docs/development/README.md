# OGScope 开发指南（开发板部署与调试）

中文 | [English](README_EN.md)

本文档面向项目成员与协作者，说明 OGScope 在开发板（Raspberry Pi / Orange Pi）环境中的实际运行方式、依赖要求与标准调试流程。

测试实践请见：[测试指南](testing-guide.md)。

当前推荐流程为：**本地编辑代码 -> 上传到开发板 -> 使用 `systemd` 重启服务验证**。  
该流程与实际硬件运行环境一致，适合涉及相机与系统库依赖的场景。

## 1. Python 版本与项目依赖

### 1.1 Python 版本基线

- 项目版本约束以 `pyproject.toml` 为准：`python = "^3.10"`
- 建议开发板使用 Python 3.10 及以上版本
- 若其他文档出现 `3.9+`，应视为历史描述

### 1.2 安装 Poetry 与 Python 依赖

```bash
# 进入项目目录
cd /path/to/OGScope

# 安装 Poetry（若尚未安装）
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"

# 安装项目依赖
poetry install
```

### 1.3 使用安装脚本（推荐首次部署）

仓库提供 `scripts/install.sh`，用于在开发板执行一次性环境准备。脚本会：

- 安装系统依赖与 Poetry
- 安装项目 Python 依赖
- 生成/更新 `systemd` 服务（`ogscope.service`）
- 注入 `PYTHONPATH` 与 `LD_LIBRARY_PATH`
- 启用服务开机自启

执行方式：

```bash
cd /path/to/OGScope
chmod +x scripts/install.sh
./scripts/install.sh
```

### 1.4 依赖维护建议

- 保持 `poetry.lock` 与仓库同步
- 每次上传较大改动后，执行一次 `poetry install`
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
- `scripts/start_debug_console.sh`
  - 作用：手动设置 `PYTHONPATH`/`LD_LIBRARY_PATH` 后前台启动
  - 状态：手动调试辅助脚本，不是默认生产启动链路
- `Makefile` 中 `run/dev/deploy`
  - 作用：开发效率命令
  - 状态：辅助入口，不替代 `systemd` 主流程

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

代码更新后（`git pull` 或手动上传）执行以下流程：

```bash
# 进入项目目录
cd /path/to/OGScope

# 同步依赖（有 pyproject.toml/poetry.lock 变更时必须执行）
poetry install

# 重启服务使新代码生效
sudo systemctl restart ogscope

# 检查状态和日志
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

说明：

- 若仅前端模板/静态文件变更，通常不需要 `poetry install`
- 若服务文件配置有改动，需先 `sudo systemctl daemon-reload`

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

| 地址 | 说明 |
|------|------|
| `http://<host>:8000/docs` | Swagger UI — 交互式接口测试 |
| `http://<host>:8000/redoc` | ReDoc — 结构化接口文档 |
| `http://<host>:8000/openapi.json` | OpenAPI Schema (JSON) |

### 9.2 API 分组（Tags）

所有接口在文档中按模块分组展示，分组通过路由注册时的 `tags` 参数控制：

| 分组 | 模块 | 说明 |
|------|------|------|
| Camera - 相机 | `ogscope.web.api.camera` | 相机控制与图像获取 |
| Alignment - 极轴校准 | `ogscope.web.api.alignment` | 极轴校准流程与状态 |
| System - 系统 | `ogscope.web.api.system` | 系统信息与配置管理 |
| Debug - 调试 | `ogscope.web.api.debug` | 调试控制台接口 |

分组在 `ogscope/web/api/main.py` 中通过 `include_router()` 的 `tags` 参数指定，描述信息在 `ogscope/web/app.py` 的 `openapi_tags` 中定义。

### 9.3 新增 API 模块时的文档配置

新增一个 API 模块后，需在两处添加配置，以确保文档正确分组：

1. **`ogscope/web/app.py`** — 在 `openapi_tags` 列表中添加分组描述：

```python
{
    "name": "NewModule - 新模块",
    "description": "模块说明 / Module description",
},
```

2. **`ogscope/web/api/main.py`** — 注册路由时指定 `tags`：

```python
router.include_router(new_router, tags=["NewModule - 新模块"])
```

### 9.4 ReDoc 自定义说明

项目使用自定义 ReDoc 路由（固定版本 `redoc@2.1.5`），而非 FastAPI 默认的 `redoc@next`，以避免预发布版本不稳定导致页面空白。相关配置见 `ogscope/web/app.py` 中的 `custom_redoc()` 函数。

## 10. 常见故障排查

若服务启动失败，优先检查：

- `WorkingDirectory` 是否指向项目根目录
- `ExecStart` 是否使用正确的虚拟环境 Python
- `PYTHONPATH` 是否包含系统 `dist-packages`
- `LD_LIBRARY_PATH` 是否包含 `libcamera` 相关库路径
- 最近代码上传是否完整，依赖是否已重新安装

## 11. 常用命令速查

```bash
# 安装/更新依赖
poetry install

# 前台手动启动（调试时）
poetry run python -m ogscope.main

# systemd 管理
sudo systemctl restart ogscope
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```
