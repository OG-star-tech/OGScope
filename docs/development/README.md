# OGScope 开发指引

## 项目启动

### 本地开发环境

```bash
# 1. 克隆项目
git clone https://github.com/OG-star-tech/OGScope.git
cd OGScope

# 2. 安装依赖
poetry install

# 3. 激活虚拟环境
poetry shell

# 4. 运行项目
python -m ogscope.main
```

### 开发板环境

```bash
# 1. SSH连接到开发板
ssh [用户名]@[开发板IP]

# 2. 进入项目目录
cd [项目目录]

# 3. 激活虚拟环境
source [虚拟环境路径]/bin/activate

# 4. 设置环境变量（重要）
export PYTHONPATH=[系统Python路径]
export LD_LIBRARY_PATH=[系统库路径]

# 5. 运行项目
python -m ogscope.main
```

## 开发模式

### 推荐开发流程

1. **本地开发** - 在Mac上进行代码编写和测试
2. **文件同步** - 使用PyCharm自动同步到开发板
3. **远程测试** - 在开发板上测试硬件功能
4. **混合调试** - 结合本地和远程环境

### PyCharm配置

详见 [PyCharm文件同步开发指南](pycharm-remote.md)

### 测试策略

```bash
# 本地单元测试
poetry run pytest tests/unit/

# 本地集成测试
poetry run pytest tests/integration/

# 硬件相关测试（需要在开发板上运行）
poetry run pytest tests/ -m hardware
```

## 项目结构说明

```
ogscope/
├── core/          # 核心功能：相机、图像处理、板块求解
├── hardware/      # 硬件接口：相机驱动、显示驱动
├── web/           # FastAPI Web 服务
├── ui/            # SPI 屏幕界面
├── algorithms/    # 天文算法
├── data/          # 数据管理
├── indi/          # INDI 集成（Phase 3）
└── utils/         # 工具函数
```

## 开发阶段

### Phase 1 - MVP (当前)
- ✅ 项目结构搭建
- ✅ 基础相机功能
- ✅ Web 界面和 API
- 🔄 简单极轴校准算法

### Phase 2 - 完整功能
- ⏳ SPI 屏幕支持
- ⏳ 高级板块求解
- ⏳ 移动 App

### Phase 3 - 生态集成
- ⏳ INDI 驱动
- ⏳ 赤道仪控制

## 代码规范

- 行长度: 88 字符 (Black 默认)
- 类型提示: 使用 Python 类型注解
- 文档字符串: Google 风格
- 导入顺序: 标准库 → 第三方库 → 本地模块

## 测试标记

- `@pytest.mark.unit`: 单元测试
- `@pytest.mark.integration`: 集成测试
- `@pytest.mark.hardware`: 需要实际硬件的测试
- `@pytest.mark.slow`: 运行较慢的测试

## 配置管理

- 默认配置: `default_config.json`
- 环境变量: `.env` (从 `.env.example` 复制)
- 运行时配置: `ogscope/config.py` (Pydantic Settings)

## 注意事项

- 避免在代码中硬编码路径，使用配置系统
- 硬件相关代码应提供模拟实现，便于在开发机上测试
- 所有 API 端点应编写单元测试
- 日志使用 Loguru，不要使用 print()

## 参考项目

- **PiFinder**: 板块求解寻星器架构参考
- **OpenMV Polar Scope**: 极轴镜算法参考