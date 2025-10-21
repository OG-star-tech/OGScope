# 本地测试指南

在没有 Orange Pi 硬件的情况下，也可以在 Mac 上进行开发和测试。

## 🧪 本地测试步骤

### 1. 安装依赖

```bash
cd "/Users/luyifei/Desktop/ogs proj/OGScope "

# 使用 Poetry 安装依赖
poetry install

# 激活虚拟环境
poetry shell
```

### 2. 运行单元测试

```bash
# 运行所有测试
poetry run pytest -v

# 只运行单元测试
poetry run pytest -m unit -v

# 生成覆盖率报告
poetry run pytest --cov=ogscope --cov-report=html
open htmlcov/index.html  # 查看覆盖率报告
```

### 3. 运行 Web 服务

```bash
# 方法 1: 使用主程序
poetry run python -m ogscope.main

# 方法 2: 直接使用 uvicorn
poetry run uvicorn ogscope.web.app:app --reload --host 127.0.0.1 --port 8000
```

然后在浏览器中访问：
- 主页: http://127.0.0.1:8000
- API 文档: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

### 4. 代码质量检查

```bash
# 代码格式化
poetry run black ogscope tests

# 代码检查
poetry run ruff check ogscope tests

# 类型检查
poetry run mypy ogscope

# 或使用 Makefile
make format
make lint
make check  # 运行所有检查
```

### 5. 测试 API

使用 `httpie` 或 `curl` 测试 API：

```bash
# 安装 httpie
pip install httpie

# 测试健康检查
http GET http://127.0.0.1:8000/health

# 测试相机状态
http GET http://127.0.0.1:8000/api/camera/status

# 测试相机设置
http POST http://127.0.0.1:8000/api/camera/settings \
    exposure:=10000 \
    gain:=1.5
```

## 🐛 模拟硬件

由于没有实际硬件，需要实现模拟驱动。

### 创建模拟相机

编辑 `ogscope/hardware/camera_debug.py`:

```python
"""模拟相机驱动（用于开发测试）"""
import numpy as np
from PIL import Image
import time

class DebugCamera:
    """模拟相机，返回测试图像"""
    
    def __init__(self, width=1920, height=1080):
        self.width = width
        self.height = height
        self.is_streaming = False
        
    def start(self):
        """启动相机"""
        self.is_streaming = True
        
    def stop(self):
        """停止相机"""
        self.is_streaming = False
        
    def capture(self):
        """捕获一帧图像"""
        # 生成测试图像：黑色背景 + 随机星点
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # 添加随机星点
        num_stars = 100
        for _ in range(num_stars):
            x = np.random.randint(0, self.width)
            y = np.random.randint(0, self.height)
            brightness = np.random.randint(128, 255)
            img[y, x] = [brightness, brightness, brightness]
        
        return img
```

然后在 `ogscope/config.py` 中设置：

```python
camera_type: str = Field(default="debug", description="相机类型")
```

### 创建模拟显示屏

编辑 `ogscope/hardware/display_debug.py`:

```python
"""模拟 SPI 显示屏"""
from PIL import Image

class DebugDisplay:
    """将显示内容保存为图像文件"""
    
    def __init__(self, width=240, height=320):
        self.width = width
        self.height = height
        
    def show(self, image):
        """显示图像"""
        # 保存到文件而不是显示到屏幕
        image.save("debug_display.png")
        print(f"Display updated: debug_display.png")
```

## 🎨 开发工作流

### 推荐工作流程

1. **功能开发**
   ```bash
   # 创建功能分支
   git checkout -b feature/camera-module
   
   # 开发功能
   # 编辑代码...
   
   # 运行测试
   make test
   
   # 提交
   git add .
   git commit -m "feat: add camera module"
   ```

2. **本地测试**
   ```bash
   # 运行 Web 服务
   make run
   
   # 在浏览器中测试
   open http://127.0.0.1:8000
   ```

3. **代码质量**
   ```bash
   # 运行所有检查
   make check
   ```

4. **推送到 GitHub**
   ```bash
   git push origin feature/camera-module
   # 然后创建 Pull Request
   ```

## 📊 开发进度追踪

使用 GitHub Projects 或简单的 TODO.md 文件：

```markdown
## Phase 1 - MVP

### 相机模块
- [x] 创建相机抽象层
- [x] 实现调试相机
- [ ] 实现 IMX327 驱动
- [ ] 添加单元测试

### Web 服务
- [x] 搭建 FastAPI 框架
- [x] 创建基础 API
- [ ] 实现实时视频流
- [ ] 添加 WebSocket 支持

### 极轴校准
- [ ] 星点检测算法
- [ ] 北极星识别
- [ ] 漂移测试
- [ ] 误差计算
```

## 🔍 调试技巧

### 使用 IPython 调试

在代码中插入断点：

```python
import IPython; IPython.embed()
```

### 使用 Loguru 日志

```python
from loguru import logger

logger.debug("调试信息")
logger.info("普通信息")
logger.warning("警告信息")
logger.error("错误信息")
```

### PyCharm 调试

1. 设置断点（点击行号）
2. 运行调试配置（Bug 图标）
3. 查看变量、调用栈等

## ⚡ 快速命令

```bash
# 开发模式运行（自动重载）
make dev

# 运行测试
make test

# 代码检查
make check

# 清理缓存
make clean

# 查看所有命令
make help
```

## 🎯 本地测试目标

- ✅ 能够启动 Web 服务
- ✅ API 端点返回正确响应
- ✅ 单元测试全部通过
- ✅ 代码风格检查通过
- ✅ Web 界面可以访问
- ✅ 模拟相机可以工作

达成以上目标后，就可以部署到 Orange Pi 进行实际硬件测试了！

## 📝 注意事项

1. **不要提交敏感信息**: 确保 `.env` 和 `config.json` 在 `.gitignore` 中
2. **保持依赖最新**: 定期运行 `poetry update`
3. **编写测试**: 新功能要有对应的单元测试
4. **文档同步**: 代码变更后更新相关文档

Happy coding! 🚀

