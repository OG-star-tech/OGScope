# OGScope API 架构图

## 📁 目录结构

```
ogscope/web/api/
├── __init__.py
├── main.py                    # 🎯 主路由文件
├── camera/                    # 📷 相机模块
│   ├── __init__.py
│   └── routes.py              # 相机API路由 (7个端点)
├── debug/                     # 🔧 调试控制台模块
│   ├── __init__.py
│   ├── routes.py              # 调试API路由 (16个端点)
│   └── services.py            # 调试服务层
├── alignment/                 # 🎯 极轴校准模块
│   ├── __init__.py
│   └── routes.py              # 校准API路由 (6个端点)
├── system/                    # 💻 系统模块
│   ├── __init__.py
│   └── routes.py              # 系统API路由 (1个端点)
└── models/                    # 📋 数据模型模块
    ├── __init__.py
    └── schemas.py             # Pydantic模型定义
```

## 🔄 数据流向

```
HTTP Request
     ↓
┌─────────────┐
│ API Routes  │ ← 处理HTTP请求，参数验证
└─────────────┘
     ↓
┌─────────────┐
│ Services    │ ← 业务逻辑处理，数据操作
└─────────────┘
     ↓
┌─────────────┐
│ Models      │ ← 数据模型定义，序列化
└─────────────┘
     ↓
HTTP Response
```

## 📊 API端点分布

### 📷 Camera Module (7个端点)
- `GET /api/camera/status` - 获取相机状态
- `POST /api/camera/settings` - 更新相机设置
- `GET /api/camera/config` - 获取相机配置
- `POST /api/camera/config` - 更新相机配置
- `POST /api/camera/start` - 启动相机
- `POST /api/camera/stop` - 停止相机
- `GET /api/camera/preview` - 获取预览图

### 🔧 Debug Module (16个端点)
- `GET /api/debug/camera/status` - 调试相机状态
- `POST /api/debug/camera/start` - 启动调试相机
- `POST /api/debug/camera/stop` - 停止调试相机
- `GET /api/debug/camera/preview` - 调试相机预览
- `POST /api/debug/camera/capture` - 拍摄照片
- `POST /api/debug/camera/record/start` - 开始录制
- `POST /api/debug/camera/record/stop` - 停止录制
- `POST /api/debug/camera/settings` - 更新调试设置
- `POST /api/debug/camera/reset` - 重置相机
- `GET /api/debug/camera/presets` - 获取预设列表
- `POST /api/debug/camera/presets` - 保存预设
- `POST /api/debug/camera/presets/{name}/apply` - 应用预设
- `DELETE /api/debug/camera/presets/{name}` - 删除预设
- `GET /api/debug/files` - 获取文件列表
- `GET /api/debug/files/{filename}` - 下载文件
- `GET /api/debug/files/{filename}/info` - 获取文件信息

### 🎯 Alignment Module (6个端点)
- `POST /api/polar-align/start` - 开始极轴校准
- `POST /api/alignment/start` - 开始校准
- `POST /api/alignment/stop` - 停止校准
- `GET /api/alignment/status` - 获取校准状态
- `GET /api/polar-align/status` - 获取极轴校准状态
- `POST /api/polar-align/stop` - 停止极轴校准

### 💻 System Module (1个端点)
- `GET /api/system/info` - 获取系统信息

### 🎯 Main Module (2个端点)
- `GET /api` - API根路径
- `GET /api/` - API根路径（备用）

## 🏗️ 架构优势

### 1. 模块化设计
- ✅ 按业务领域划分
- ✅ 职责单一明确
- ✅ 低耦合高内聚

### 2. 分层架构
- ✅ 路由层：HTTP处理
- ✅ 服务层：业务逻辑
- ✅ 模型层：数据结构

### 3. 可维护性
- ✅ 文件大小合理
- ✅ 代码结构清晰
- ✅ 易于定位问题

### 4. 可扩展性
- ✅ 新模块独立添加
- ✅ 不影响现有功能
- ✅ 遵循统一模式

### 5. 可测试性
- ✅ 模块独立测试
- ✅ 服务层可复用
- ✅ 测试覆盖完整

## 🚀 使用示例

### 启动应用
```bash
poetry run python -m ogscope.web.app
```

### 访问API
```bash
# API文档
curl http://localhost:8000/docs

# 相机状态
curl http://localhost:8000/api/camera/status

# 调试控制台
curl http://localhost:8000/api/debug/camera/status
```

### 测试验证
```bash
# 重构测试
poetry run python scripts/test_api_refactor.py

# 功能测试
poetry run python scripts/test_debug_console.py
```

---

**OGScope API 重构完成！** 🎉

新的模块化架构为项目的长期发展奠定了坚实的基础！
