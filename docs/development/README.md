# OGScope 开发文档

## 目录

- [PyCharm 远程开发配置](./pycharm-remote.md)
- [FastAPI 开发指南](./fastapi-guide.md)
- [硬件接口开发](./hardware-interface.md)
- [测试指南](./testing-guide.md)

## 技术栈

- **硬件平台**: Orange Pi Zero 2W
- **操作系统**: Debian
- **编程语言**: Python 3.9+
- **包管理**: Poetry
- **Web 框架**: FastAPI
- **日志系统**: Loguru
- **测试框架**: Pytest

## 开发环境设置

### 1. 本地开发（Mac）

```bash
# 克隆项目
git clone https://github.com/your-username/OGScope.git
cd OGScope

# 安装 Poetry（如果未安装）
curl -sSL https://install.python-poetry.org | python3 -

# 安装依赖
poetry install

# 激活虚拟环境
poetry shell

# 运行（模拟模式，不需要硬件）
python -m ogscope.main
```

### 2. 远程开发（Orange Pi）

详见 [PyCharm 远程开发配置](./pycharm-remote.md)

## 项目结构

```
ogscope/
├── core/           # 核心功能模块
│   ├── camera.py           # 相机抽象层
│   ├── image_processor.py  # 图像处理
│   ├── plate_solver.py     # 板块求解
│   └── polar_align.py      # 极轴校准算法
├── hardware/       # 硬件接口层
│   ├── camera_imx327.py    # IMX327 驱动
│   ├── display_spi.py      # SPI 屏幕驱动
│   └── gpio_control.py     # GPIO 控制
├── web/            # Web 服务
│   ├── app.py              # FastAPI 应用
│   ├── api.py              # REST API
│   └── websocket.py        # WebSocket
├── ui/             # SPI 屏幕界面
├── algorithms/     # 算法模块
├── data/           # 数据管理
├── indi/           # INDI 集成
└── utils/          # 工具函数
```

## 开发流程

### 1. 创建新功能

```bash
# 创建新分支
git checkout -b feature/your-feature

# 开发功能
# ...

# 运行测试
poetry run pytest

# 代码格式化
poetry run black ogscope tests
poetry run ruff check ogscope tests

# 提交代码
git add .
git commit -m "feat: add your feature"
git push origin feature/your-feature
```

### 2. 代码规范

- 使用 **Black** 进行代码格式化（行长度 88）
- 使用 **Ruff** 进行代码检查
- 使用 **MyPy** 进行类型检查
- 遵循 **PEP 8** 规范
- 编写清晰的文档字符串（Google 风格）

### 3. 测试

```bash
# 运行所有测试
poetry run pytest

# 运行单元测试
poetry run pytest -m unit

# 运行集成测试
poetry run pytest -m integration

# 生成覆盖率报告
poetry run pytest --cov=ogscope --cov-report=html
```

## 常用命令

```bash
# 安装依赖
poetry install

# 添加新依赖
poetry add <package>

# 添加开发依赖
poetry add --group dev <package>

# 更新依赖
poetry update

# 运行程序
poetry run python -m ogscope.main

# 运行测试
poetry run pytest

# 代码格式化
poetry run black ogscope tests

# 代码检查
poetry run ruff check ogscope tests

# 类型检查
poetry run mypy ogscope
```

## 调试技巧

### 1. 使用 IPython

```python
# 在代码中插入断点
import IPython; IPython.embed()
```

### 2. 使用 Loguru

```python
from loguru import logger

logger.debug("调试信息")
logger.info("普通信息")
logger.warning("警告信息")
logger.error("错误信息")
```

### 3. PyCharm 远程调试

在 PyCharm 中设置断点，然后使用调试模式运行

## 常见问题

### Q: 如何模拟相机进行开发？

A: 在 `ogscope/hardware/camera_debug.py` 中实现模拟相机，返回测试图像

### Q: 如何在 Mac 上测试 SPI 屏幕代码？

A: 使用模拟 SPI 驱动，将显示内容保存为图像文件

### Q: 如何贡献代码？

A: 
1. Fork 项目
2. 创建功能分支
3. 提交代码
4. 创建 Pull Request

## 参考资源

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Poetry 文档](https://python-poetry.org/docs/)
- [Orange Pi 官方文档](http://www.orangepi.org/)
- [PiFinder 项目](https://github.com/brickbots/PiFinder)

