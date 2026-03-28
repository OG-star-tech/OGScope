# OGScope 开发板部署简表（爱好者复刻）

中文 | [English](DEPLOY_EN.md)

本文档为单页清单，与 [开发指南](README.md) 配合使用。

## 系统要求

- 单板计算机：Raspberry Pi / Orange Pi 等，**ARM**（`aarch64` 或 `armhf`）
- 操作系统：基于 Debian/apt 的常见镜像（与 `picamera2`/`libcamera` 文档一致）
- Python：**3.10+**（以 `pyproject.toml` 为准）
- 网络：首次安装需下载 Poetry wheel；浏览器访问 Web 界面需可达设备 **TCP 8000**（按需配置防火墙）

## 一键安装（首次）

```bash
cd /path/to/OGScope
chmod +x scripts/install.sh
./scripts/install.sh
```

说明：

- 默认 **`poetry install --only main`**，不装 dev 依赖；开发协作可设 `OGSCOPE_INSTALL_DEV=1`
- 低配板可设 **`OGSCOPE_APT_SLOW=1`**，减轻 `apt` 峰值内存压力
- **网络与镜像**：国内访问 PyPI/官方源可能较慢或不稳定，可 **`export OGSCOPE_MIRROR=cn`** 后执行脚本（apt 与 pip 使用清华镜像）；境外用户使用默认 **`auto`** 或显式 **`OGSCOPE_MIRROR=international`**
- 安装结束后按提示执行：`sudo systemctl start ogscope`

## 星图解算数据

将 **`default_database.npz`** 放到项目下 **`data/plate_solve/`**（不随仓库分发）。详见 [plate-solve-data.md](plate-solve-data.md)。

## 日常更新

```bash
cd /path/to/OGScope
chmod +x scripts/board-update.sh
# 使用 git 且需拉取：OGSCOPE_GIT_PULL=1 ./scripts/board-update.sh
# 国内镜像：OGSCOPE_MIRROR=cn ./scripts/board-update.sh
./scripts/board-update.sh
```

## 健康检查与日志

```bash
curl -s http://127.0.0.1:8000/health
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

## 常见故障

- **ImportError: picamera2**：确认已用 `apt` 安装相机栈；虚拟环境需由 `install.sh` 配置（含 `system-site-packages` 与 `PYTHONPATH`）
- **PEP 668 / 系统 pip 被拒绝**：勿在系统 Python 上 `poetry install`；使用项目 `.venv`，见 [README §1.2](README.md#12-poetrypep-668-与虚拟环境必读)
- 服务起不来：检查 `WorkingDirectory`、`ExecStart` 是否为 `.venv` 内 `python`，以及 `journalctl` 中具体报错
