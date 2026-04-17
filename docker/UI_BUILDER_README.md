# OGScope UI Builder Container / OGScope UI 构建器容器

Docker Compose 交互式前端构建环境 / Interactive frontend build environment with Docker Compose

## 快速开始 / Quick Start

```bash
# 1. 启动并进入容器 / Start and enter container
./scripts/ui_builder_shell.sh

# 容器内执行 / Inside container:
npm install      # 安装依赖 / Install dependencies
npm run build    # 构建 / Build
exit            # 退出容器 / Exit container
```

## 命令速查 / Command Reference

### 交互式 Shell / Interactive Shell
```bash
./scripts/ui_builder_shell.sh          # 进入容器 / Enter container
./scripts/ui_builder_shell.sh shell    # 同上 / Same as above
```

### 一键命令 / One-Command Actions
```bash
./scripts/ui_builder_shell.sh build    # 构建 UI / Build UI
./scripts/ui_builder_shell.sh install  # 安装依赖 / Install deps
./scripts/ui_builder_shell.sh ci       # 干净安装 / Clean install
./scripts/ui_builder_shell.sh dev      # 开发模式 / Dev mode
./scripts/ui_builder_shell.sh clean    # 清理 / Clean
```

### 容器管理 / Container Management
```bash
./scripts/ui_builder_shell.sh stop     # 停止容器 / Stop
./scripts/ui_builder_shell.sh restart  # 重启容器 / Restart
./scripts/ui_builder_shell.sh logs     # 查看日志 / View logs
```

### 直接使用 Docker Compose / Direct Docker Compose
```bash
# 启动容器 / Start container
docker compose -f docker/compose.yml up -d

# 进入容器 / Attach to container
docker compose -f docker/compose.yml exec ui-builder bash

# 停止容器 / Stop container
docker compose -f docker/compose.yml down
```

## 容器内可用命令 / Commands Inside Container

```bash
# 安装依赖 / Install dependencies
npm install

# 构建生产版本 / Build for production
npm run build

# 开发模式（热重载）/ Dev mode with hot reload
npm run dev

# 预览构建产物 / Preview build
npm run preview

# 查看构建产物 / View build artifacts
ls -lh /workspace/static/analysis-lab/
```

## 目录结构 / Directory Structure

容器内挂载 / Mounted in container:
```
/workspace/
├── analysis-ui/          # UI 源码 / UI source code
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── static/
│   ├── analysis-lab/     # 构建输出 / Build output
│   └── i18n/             # 国际化文件 / i18n files
└── templates/            # FastAPI 模板 / FastAPI templates
```

## 工作流程 / Workflow

### 开发流程 / Development Workflow

1. **首次使用 / First Time**
   ```bash
   ./scripts/ui_builder_shell.sh install
   ./scripts/ui_builder_shell.sh build
   ```

2. **日常开发 / Daily Development**
   ```bash
   # 方式 1：交互式 / Method 1: Interactive
   ./scripts/ui_builder_shell.sh
   > npm run build
   
   # 方式 2：一键构建 / Method 2: One command
   ./scripts/ui_builder_shell.sh build
   ```

3. **开发模式（热重载）/ Dev Mode (Hot Reload)**
   ```bash
   ./scripts/ui_builder_shell.sh dev
   # 访问 / Access: http://localhost:5173
   ```

### 部署到开发板 / Deploy to Dev Board

```bash
# 1. 构建 UI / Build UI
./scripts/ui_builder_shell.sh build

# 2. 同步到开发板 / Sync to dev board
rsync -avz web/static/analysis-lab/ \
  ogstartech@192.168.0.150:/home/ogstartech/OGScope/web/static/analysis-lab/

# 3. 重启服务 / Restart service
ssh ogstartech@192.168.0.150 'sudo systemctl restart ogscope'
```

## 国内镜像加速 / China Mirror Acceleration

```bash
# 使用国内 npm 镜像 / Use China npm mirror
OGSCOPE_NPM_REGISTRY=https://registry.npmmirror.com \
  ./scripts/ui_builder_shell.sh install

# 或在容器内手动设置 / Or set manually inside container
npm config set registry https://registry.npmmirror.com
```

## 故障排除 / Troubleshooting

### 权限问题 / Permission Issues
容器使用宿主机用户 ID，避免生成的文件权限问题 / Container uses host user ID to avoid permission issues

```bash
# 如遇权限问题，检查 UID/GID / If permission issues, check UID/GID
id -u  # 应该输出 1000 或其他 / Should output 1000 or other
id -g

# 手动设置 / Set manually
export UID=$(id -u)
export GID=$(id -g)
./scripts/ui_builder_shell.sh
```

### 清理重建 / Clean Rebuild
```bash
# 清理所有构建产物和依赖 / Clean all build artifacts and deps
./scripts/ui_builder_shell.sh clean

# 重新安装和构建 / Reinstall and rebuild
./scripts/ui_builder_shell.sh ci
./scripts/ui_builder_shell.sh build
```

### 容器问题 / Container Issues
```bash
# 重启容器 / Restart container
./scripts/ui_builder_shell.sh restart

# 完全重建容器 / Completely rebuild container
docker compose -f docker/compose.yml down
docker compose -f docker/compose.yml up -d --build
```

## 环境变量 / Environment Variables

| 变量 / Variable | 描述 / Description | 示例 / Example |
|-----------------|-------------------|----------------|
| `OGSCOPE_NPM_REGISTRY` | npm 镜像源 / npm registry | `https://registry.npmmirror.com` |
| `UID` | 用户 ID / User ID | `1000` (自动) |
| `GID` | 组 ID / Group ID | `1000` (自动) |

## 文件说明 / Files

- `docker/compose.yml` - Docker Compose 配置 / Docker Compose config
- `docker/Dockerfile.ui-builder` - 构建器镜像定义 / Builder image definition
- `scripts/ui_builder_shell.sh` - 交互式脚本 / Interactive script
- `scripts/build_ui_container.sh` - 旧版自动构建脚本 / Legacy auto-build script

## 优势 / Advantages

- ✅ 无需本地安装 Node.js / No local Node.js needed
- ✅ 环境一致性 / Consistent environment
- ✅ 支持交互式开发 / Interactive development support
- ✅ 避免文件权限问题 / Avoids permission issues
- ✅ 快速切换 Node.js 版本 / Easy Node.js version switching
- ✅ 支持热重载开发模式 / Hot reload dev mode support
