# OGScope 调试控制台

## 📖 简介

OGScope 调试控制台是一个专为开发者设计的相机调试工具，提供实时预览、拍摄控制、参数调节、预设管理和文件管理等功能。

## 🚀 功能特性

### 📷 实时预览
- 15fps 实时相机预览
- 支持启动/停止预览
- 实时状态显示

### 📸 拍摄控制
- **单张拍摄**: 拍摄高质量照片并自动保存
- **视频录制**: 手动控制录制时长，支持MP4格式
- **文件命名**: 自动生成时间戳文件名
- **参数记录**: 每次拍摄自动生成参数记录文件

### ⚙️ 参数设置
- **曝光时间**: 1ms - 100ms (微秒级调节)
- **模拟增益**: 1x - 16x (0.1x步进)
- **数字增益**: 1x - 4x (0.1x步进)
- **实时应用**: 参数修改立即生效
- **一键重置**: 恢复到默认设置

### 💾 预设管理
- **保存预设**: 最多10个预设
- **快速应用**: 一键应用保存的预设
- **预设描述**: 支持预设描述信息
- **预设删除**: 删除不需要的预设

### 📁 文件管理
- **文件列表**: 查看所有拍摄文件
- **文件下载**: 直接下载到本地
- **文件信息**: 查看详细的拍摄参数
- **自动刷新**: 拍摄后自动更新文件列表

## 🛠️ 安装和运行

### 1. 安装依赖

```bash
# 安装Python依赖（建议在虚拟环境中）
pip install -U pip setuptools wheel
pip install opencv-python-headless fastapi uvicorn numpy pillow

# 安装相机驱动 (树莓派)
sudo apt install -y python3-picamera2 libcamera-apps
```

### 2. 启动服务

```bash
# 使用Poetry启动 (推荐) - 主入口
poetry run python -m ogscope.main

# 或直接启动
python -m ogscope.web.app
```

### 3. 访问调试控制台

打开浏览器访问: `http://localhost:8000/debug`

## 📱 使用指南

### 基本操作流程

1. **启动相机预览**
   - 点击 "启动预览" 按钮
   - 等待相机初始化完成
   - 查看实时画面

2. **调整相机参数**
   - 切换到 "参数设置" 标签页
   - 拖动滑块调整曝光和增益
   - 点击 "应用设置" 使参数生效

3. **拍摄照片**
   - 切换到 "拍摄控制" 标签页
   - 点击 "拍摄照片" 按钮
   - 照片自动保存到 `~/dev_captures/` 目录

4. **录制视频**
   - 点击 "开始录制" 按钮
   - 录制过程中显示计时器
   - 点击 "停止录制" 结束录制

5. **管理预设**
   - 切换到 "预设管理" 标签页
   - 输入预设名称和描述
   - 点击 "保存预设" 保存当前设置
   - 点击预设卡片上的 "应用" 快速切换

6. **查看文件**
   - 切换到 "文件管理" 标签页
   - 查看所有拍摄文件
   - 点击 "下载" 下载文件到本地
   - 点击 "详情" 查看拍摄参数

### 键盘快捷键

- `空格键`: 启动/停止预览
- `C`: 拍摄照片
- `R`: 开始/停止录制
- `1-5`: 切换标签页
- `Esc`: 停止录制

## 📂 文件结构

```
~/dev_captures/           # 拍摄文件存储目录
├── IMG_20241201_143022.jpg    # 拍摄的照片
├── IMG_20241201_143022.txt    # 对应的参数文件
├── VID_20241201_143045.mp4    # 录制的视频
├── VID_20241201_143045.txt    # 对应的参数文件
└── presets.json              # 预设配置文件
```

### 参数文件格式

每个拍摄文件都会生成对应的 `.txt` 参数文件，包含以下信息：

```json
{
  "filename": "IMG_20241201_143022",
  "timestamp": "2024-12-01T14:30:22.123456",
  "exposure_us": 10000,
  "analogue_gain": 2.0,
  "digital_gain": 1.0,
  "resolution": "1920x1080",
  "file_size": 2048576,
  "camera_type": "imx327_mipi",
  "fps": 15
}
```

## 🔧 API 接口

调试控制台提供以下API接口：

### 相机控制
- `GET /api/debug/camera/status` - 获取相机状态
- `POST /api/debug/camera/start` - 启动相机
- `POST /api/debug/camera/stop` - 停止相机
- `GET /api/debug/camera/preview` - 获取预览图像

### 拍摄功能
- `POST /api/debug/camera/capture` - 拍摄照片
- `POST /api/debug/camera/record/start` - 开始录制
- `POST /api/debug/camera/record/stop` - 停止录制

### 参数设置
- `POST /api/debug/camera/settings` - 更新相机设置
- `POST /api/debug/camera/reset` - 重置到默认设置

### 预设管理
- `GET /api/debug/camera/presets` - 获取预设列表
- `POST /api/debug/camera/presets` - 保存预设
- `POST /api/debug/camera/presets/{name}/apply` - 应用预设
- `DELETE /api/debug/camera/presets/{name}` - 删除预设

### 文件管理
- `GET /api/debug/files` - 获取文件列表
- `GET /api/debug/files/{filename}` - 下载文件
- `GET /api/debug/files/{filename}/info` - 获取文件信息

## 🧪 测试

运行测试脚本验证功能：

```bash
# 运行完整测试
python scripts/test_debug_console.py

# 只测试API
python scripts/test_debug_console.py --test api

# 只测试Web界面
python scripts/test_debug_console.py --test web

# 只检查依赖
python scripts/test_debug_console.py --test deps
```

## ⚠️ 注意事项

1. **硬件要求**: 需要支持Picamera2的树莓派设备
2. **权限要求**: 相机访问需要适当的系统权限
3. **存储空间**: 确保有足够的存储空间保存拍摄文件
4. **网络访问**: 调试控制台通过Web界面访问，确保网络连接正常

## 🐛 故障排除

### 常见问题

1. **相机初始化失败**
   - 检查 Picamera2 是否正确安装：`python3 -c "from picamera2 import Picamera2; print('OK')"`
   - 确认相机硬件连接正常：`ls /dev/video*`
   - 检查系统权限
   - 服务进程需能访问系统的 Picamera2 与 libcamera，必要时为服务设置环境变量：
     - `PYTHONPATH=/usr/lib/python3/dist-packages:/usr/local/lib/python3.13/dist-packages`
     - `LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu`

2. **预览无法显示**
   - 确认相机已启动
   - 检查OpenCV是否正确安装
   - 查看浏览器控制台错误信息

3. **文件保存失败**
   - 检查存储目录权限
   - 确认磁盘空间充足
   - 查看服务器日志

4. **预设保存失败**
   - 检查预设名称是否重复
   - 确认预设数量未超过限制(10个)
   - 检查文件写入权限

### 日志查看

```bash
# 查看应用日志
tail -f /home/<user>/ogscope_server.log

# 查看系统日志
journalctl -u ogscope.service -f
```

## 🔧 树莓派部署要点（AI工具重要备注）

- 本项目在树莓派上使用系统自带的 Picamera2 与 libcamera。
- 如在虚拟环境中运行，需要将系统的 Python 包路径注入到服务进程：
  - `PYTHONPATH=/usr/lib/python3/dist-packages:/usr/local/lib/python3.13/dist-packages`
  - `LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu`
- 推荐将上述环境变量固化到启动脚本或 systemd 服务的 Environment 配置，以避免重复调试。

## 📞 技术支持

如果遇到问题，请：

1. 查看本文档的故障排除部分
2. 运行测试脚本检查系统状态
3. 查看应用日志获取详细错误信息
4. 提交Issue到项目仓库

---

**OGScope 调试控制台** - 让相机调试更简单！ 🎯
