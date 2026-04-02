# OGScope - 电子极轴镜

基于 Raspberry Pi Zero 2W 的智能电子极轴镜系统，用于天文摄影中的精确极轴校准。

[English](README_EN.md) | 中文

## 硬件平台

- **主控**: Raspberry Pi Zero 2W
- **操作系统**: Raspberry Pi OS
- **摄像头**: IMX327 MIPI 传感器
- **显示屏**: 2.4寸 SPI LCD
- **通信**: WiFi 无线控制

## 功能特性

### Phase 1 - 基础功能 (MVP)
- ✅ 实时视频预览
- ✅ Web 远程控制
- ✅ 基础极轴校准
- ✅ 相机参数调整

### Phase 2 - 完整功能
- ⏳ SPI 屏幕显示
- ⏳ 自动板块求解
- ⏳ 移动 App 控制
- ⏳ 校准数据管理

### Phase 3 - 生态集成
- ⏳ INDI 驱动支持
- ⏳ 赤道仪控制
- ⏳ 多设备联动

### 主要特性

- 🔭 **精确校准**: 高精度极轴校准算法
- 📱 **远程控制**: Web 界面和移动 App
- 🖥️ **本地显示**: 2.4寸 SPI LCD 实时显示
- 🌐 **生态集成**: 支持 INDI 协议

### 技术规格

- **处理器**: Raspberry Pi Zero 2W (ARM Cortex-A53)
- **相机**: IMX327 传感器 (1920x1080)
- **显示**: 2.4寸 SPI LCD (240x320)
- **软件**: Python 3.9 + FastAPI

## 快速开始

### 环境要求

- Python 3.9+
- Poetry 1.2+
- Raspberry Pi Zero 2W (Raspberry Pi OS)

### 安装

```bash
# 克隆项目
git clone https://github.com/OG-star-tech/OGScope.git
cd OGScope

# 安装依赖（使用 Poetry）
poetry install

# 激活虚拟环境
poetry shell

# 运行程序
python -m ogscope.main
```

开发板一键部署、WiFi 热点与 **`/debug/system`** 等以 [docs/development/wifi-nm.md](docs/development/wifi-nm.md) 与 [docs/development/README.md](docs/development/README.md) 为准。

### Web 界面访问

启动后访问: http://raspberrypi.local:8000 或 http://<IP>:8000

## 文档

### 用户文档
- [快速开始](docs/QUICK_START.md)
- [用户手册](docs/user_guide/user-manual.md)
- [常见问题](docs/user_guide/faq.md)

### 硬件文档
- [硬件清单 (BOM)](docs/hardware/bom.md)
- [组装指南](docs/hardware/assembly-guide.md)
- [硬件调试](docs/hardware/hardware-debug.md)

### 开发文档
- [开发指南（中文）](docs/development/README.md)
- [开发指南（English）](docs/development/README_EN.md)
- [树莓派 WiFi / AP / STA / 调试页（NetworkManager）](docs/development/wifi-nm.md)
- [FastAPI 开发](docs/development/fastapi-guide.md)
- [测试指南](docs/development/testing-guide.md)

## 开发

详见 [开发文档（中文）](docs/development/README.md) /
[Development Guide (English)](docs/development/README_EN.md)

### 远程开发配置

当前推荐流程详见 [开发指南](docs/development/README.md)：

1. 在本地 IDE 编写代码
2. 手动上传代码到开发板
3. 使用 `systemd` 重启并验证服务

## 项目结构

```
OGScope/
├── ogscope/           # 主应用包
│   ├── core/         # 核心功能模块
│   ├── hardware/     # 硬件接口层
│   ├── web/          # FastAPI Web 服务
│   ├── ui/           # SPI 屏幕界面
│   ├── algorithms/   # 天文算法
│   └── utils/        # 工具函数
├── tests/            # 测试代码
├── docs/             # 文档
├── scripts/          # 部署脚本
└── web/              # Web 前端资源
```


## 许可证

本项目采用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 许可证

- **署名 (BY)**: 必须标明原作者
- **非商业性使用 (NC)**: 禁止商业用途
- **相同方式共享 (SA)**: 衍生作品必须使用相同许可证

详见 [LICENSE](LICENSE) 文件

## 快速链接

- [GitHub 仓库](https://github.com/OG-star-tech/OGScope)
- [问题反馈](https://github.com/OG-star-tech/OGScope/issues)
- [讨论区](https://github.com/OG-star-tech/OGScope/discussions)

## 贡献

欢迎提交 Issue 和 Pull Request！详见 [贡献指南](CONTRIBUTING.md)

