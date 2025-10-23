# PyCharm Professional 文件同步开发配置指南

本指南适用于 **PyCharm Professional 2025** 版本，推荐使用文件同步方式进行开发

## 前置准备

### 1. Raspberry Pi Zero 2W 配置

```bash
# SSH 连接到 Raspberry Pi
ssh pi@raspberrypi.local  # 或使用 IP 地址

# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装必要工具
sudo apt install -y python3.9 python3-pip python3-venv git

# 安装 Poetry
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# 验证安装
poetry --version
```

### 2. Mac 本地配置

```bash
# 配置 SSH 免密登录（强烈推荐）
ssh-keygen -t ed25519 -C "ogscope-dev"
ssh-copy-id pi@orangepi.local

# 配置 SSH config
cat >> ~/.ssh/config << EOF
Host orangepi
    HostName orangepi.local  # 或固定 IP
    User pi
    Port 22
    ForwardAgent yes
    ServerAliveInterval 60
    ServerAliveCountMax 3
EOF

# 测试连接
ssh orangepi
```

## PyCharm Professional 配置步骤

### 步骤 1: 配置文件同步（推荐方式）

1. **打开项目**
   - 在 Mac 上用 PyCharm 打开 OGScope 项目目录

2. **配置部署服务器**
   - `Tools` → `Deployment` → `Configuration`
   - 点击 `+` 添加服务器
   - Name: `Raspberry Pi Zero 2W`
   - Type: `SFTP`

3. **Connection 标签配置**
   ```
   SSH configuration: orangepi (使用前面配置的)
   Root path: /home/pi/OGScope
   Web server URL: http://orangepi.local:8000 (可选)
   ```

4. **Mappings 标签配置**
   ```
   Local path: /Users/你的用户名/Desktop/ogs proj/OGScope
   Deployment path: /
   Web path: /
   ```

5. **Excluded Paths 标签** (添加不需要同步的目录)
   ```
   .venv
   __pycache__
   .pytest_cache
   .mypy_cache
   *.pyc
   .git
   node_modules
   ```

6. **启用自动上传**
   - `Tools` → `Deployment` → `Automatic Upload` (打勾)
   - 或设置为 `On explicit save action` (Cmd+S 时上传)

### 步骤 2: 配置本地运行环境

1. **配置本地Python解释器**
   - `File` → `Settings` (macOS: `PyCharm` → `Preferences`)
   - 导航到: `Project: OGScope` → `Python Interpreter`
   - 选择本地 Poetry 虚拟环境: `~/.cache/pypoetry/virtualenvs/ogscope-xxx/bin/python`

2. **配置运行配置**
   - `Run` → `Edit Configurations...`
   - 点击 `+` → `Python`

3. **配置参数**
   ```
   Name: OGScope Local
   Script path: (留空)
   Module name: ogscope.main
   Parameters: --host 0.0.0.0 --port 8000 --reload
   Python interpreter: <选择本地Poetry解释器>
   Working directory: /Users/你的用户名/Desktop/ogs proj/OGScope
   ```

### 步骤 3: 配置远程运行（可选）

1. **创建远程运行配置**
   - `Run` → `Edit Configurations...`
   - 点击 `+` → `Python`

2. **配置参数**
   ```
   Name: OGScope Remote
   Script path: (留空)
   Module name: ogscope.main
   Parameters: --host 0.0.0.0 --port 8000 --reload
   Python interpreter: <选择远程解释器>
   Working directory: /home/pi/OGScope
   ```

3. **环境变量** (可选)
   ```
   OGSCOPE_ENV=development
   LOG_LEVEL=DEBUG
   ```

4. **远程调试配置**
   - 确保 `Path mappings` 正确:
     ```
     Local: /Users/你的用户名/Desktop/ogs proj/OGScope
     Remote: /home/pi/OGScope
     ```

### 步骤 4: 使用远程终端

1. **添加 SSH 会话**
   - `Tools` → `Start SSH Session...`
   - 选择 `orangepi` 配置

2. **或使用内置终端**
   - 打开 Terminal 面板 (Alt+F12 或 ⌥F12)
   - PyCharm 会自动连接到远程服务器

## 推荐开发工作流程

### 1. 本地开发（主要方式）

```bash
# 在本地进行代码开发和测试
# 使用本地运行配置 "OGScope Local"
# 大部分功能可以在本地测试（除了硬件相关功能）
```

### 2. 文件同步

```bash
# 自动同步（推荐）
# 保存文件时自动上传到开发板

# 手动同步
Tools → Deployment → Upload to Raspberry Pi Zero 2W

# 上传整个项目
右键项目根目录 → Deployment → Upload to Orange Pi Zero 2W

# 从远程下载
Tools → Deployment → Download from Raspberry Pi Zero 2W

# 比较本地和远程
Tools → Deployment → Compare with Deployed Version on Raspberry Pi Zero 2W
```

### 3. 远程测试

```bash
# 需要测试硬件功能时
# 1. 先同步文件到开发板
# 2. 使用远程运行配置 "OGScope Remote"
# 3. 或通过SSH终端手动运行
```

### 运行和调试

```bash
# 本地运行（推荐）
选择 "OGScope Local" 配置
点击工具栏的 ▶️ 运行按钮
或按 Shift+F10 (macOS: ^R)

# 远程运行（硬件测试）
选择 "OGScope Remote" 配置
点击工具栏的 ▶️ 运行按钮

# 调试程序
点击工具栏的 🐞 调试按钮
或按 Shift+F9 (macOS: ^D)

# 在代码中设置断点
点击行号左侧设置断点 (红点)
```

### 远程 Poetry 管理

```python
# 在远程终端中执行
poetry install          # 安装依赖
poetry add <package>    # 添加包
poetry remove <package> # 移除包
poetry update           # 更新依赖
poetry shell            # 激活虚拟环境
```

## 常见问题

### 问题 1: 连接超时

**解决方案**:
```bash
# 检查 Raspberry Pi 网络
ping orangepi.local

# 检查 SSH 服务
ssh orangepi
sudo systemctl status ssh

# 增加 SSH 超时时间
# 在 ~/.ssh/config 中添加:
ServerAliveInterval 60
ServerAliveCountMax 3
```

### 问题 2: 文件同步慢

**解决方案**:
```bash
# 方案1: 排除不必要的文件
Tools → Deployment → Configuration → Excluded Paths
添加: .venv, .git, __pycache__, *.pyc

# 方案2: 使用增量同步
Tools → Deployment → Options
勾选: Upload changed files automatically

# 方案3: 手动同步
只同步修改的文件，避免全量上传
```

### 问题 3: 远程解释器找不到包

**解决方案**:
```bash
# 在远程终端重新安装
cd ~/OGScope
poetry install

# 刷新 PyCharm 解释器缓存
Settings → Project → Python Interpreter
点击 🔄 刷新按钮
```

### 问题 4: 调试断点不生效

**解决方案**:
```bash
# 检查路径映射
Run → Edit Configurations → Path mappings
确保本地和远程路径正确对应

# 重新同步项目
Tools → Deployment → Sync with Deployed to Raspberry Pi Zero 2W
```

## 性能优化建议

### 1. 使用 .gitignore 和排除路径

确保 `.venv`, `__pycache__`, `.pytest_cache` 等目录不被同步

### 2. 启用智能同步

```
Tools → Deployment → Options:
☑ Upload changed files automatically
☑ Skip external changes
```

### 3. 使用有线网络

如果 WiFi 不稳定，考虑使用 USB 网卡 + 有线连接

### 4. 混合开发模式

```python
# 本地开发（推荐）
# 1. 在本地进行代码编写和单元测试
poetry run pytest tests/unit/

# 2. 本地运行Web服务测试API
python -m ogscope.main

# 3. 需要硬件测试时同步到远程
Tools → Deployment → Upload to Raspberry Pi Zero 2W

# 4. 远程运行测试硬件功能
ssh orangepi
cd /home/pi/OGScope
poetry run python -m ogscope.main
```

## 快捷键速查表

| 操作 | macOS | Windows/Linux |
|------|-------|---------------|
| 运行 | ^R | Shift+F10 |
| 调试 | ^D | Shift+F9 |
| 停止 | ⌘F2 | Ctrl+F2 |
| 同步文件 | ⌥⌘Y | Ctrl+Alt+Y |
| 远程终端 | ⌥F12 | Alt+F12 |
| 查找文件 | ⌘⇧O | Ctrl+Shift+N |

## 下一步

配置完成后，可以开始开发了！参考:
- [FastAPI 开发指南](./fastapi-guide.md)
- [硬件接口开发](./hardware-interface.md)
- [测试指南](./testing-guide.md)

