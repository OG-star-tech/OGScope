#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API重构测试脚本
验证模块化API结构是否正常工作
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_api_imports():
    """测试API模块导入"""
    print("🔍 测试API模块导入...")
    
    try:
        # 测试主API模块
        from ogscope.web.api.main import router as main_router
        print("✅ 主API模块导入成功")
        
        # 测试各个子模块
        from ogscope.web.api.camera.routes import router as camera_router
        print("✅ 相机API模块导入成功")
        
        from ogscope.web.api.alignment.routes import router as alignment_router
        print("✅ 极轴校准API模块导入成功")
        
        from ogscope.web.api.system.routes import router as system_router
        print("✅ 系统API模块导入成功")
        
        from ogscope.web.api.debug.routes import router as debug_router
        print("✅ 调试控制台API模块导入成功")
        
        # 测试数据模型
        from ogscope.web.api.models.schemas import (
            CameraSettings, 
            PolarAlignStatus, 
            CameraPreset,
            CaptureInfo,
            SystemInfo,
            AlignmentStatus
        )
        print("✅ 数据模型导入成功")
        
        # 测试调试服务
        from ogscope.web.api.debug.services import (
            DebugCameraService,
            DebugPresetService,
            DebugFileService
        )
        print("✅ 调试服务模块导入成功")
        
        return True
        
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False


def test_router_registration():
    """测试路由注册"""
    print("\n🔍 测试路由注册...")
    
    try:
        from ogscope.web.api.main import router as main_router
        
        # 检查路由数量
        routes = [route for route in main_router.routes]
        print(f"✅ 主路由器包含 {len(routes)} 个路由")
        
        # 检查各个模块的路由
        route_paths = [route.path for route in routes if hasattr(route, 'path')]
        
        # 检查相机路由
        camera_routes = [path for path in route_paths if path.startswith('/camera')]
        print(f"✅ 相机路由: {len(camera_routes)} 个")
        
        # 检查极轴校准路由
        alignment_routes = [path for path in route_paths if 'alignment' in path or 'polar-align' in path]
        print(f"✅ 极轴校准路由: {len(alignment_routes)} 个")
        
        # 检查系统路由
        system_routes = [path for path in route_paths if path.startswith('/system')]
        print(f"✅ 系统路由: {len(system_routes)} 个")
        
        # 检查调试路由
        debug_routes = [path for path in route_paths if path.startswith('/debug')]
        print(f"✅ 调试控制台路由: {len(debug_routes)} 个")
        
        return True
        
    except Exception as e:
        print(f"❌ 路由注册测试失败: {e}")
        return False


def test_data_models():
    """测试数据模型"""
    print("\n🔍 测试数据模型...")
    
    try:
        from ogscope.web.api.models.schemas import (
            CameraSettings, 
            PolarAlignStatus, 
            CameraPreset,
            CaptureInfo,
            SystemInfo,
            AlignmentStatus
        )
        
        # 测试CameraSettings
        camera_settings = CameraSettings(exposure=10000, gain=2.0)
        assert camera_settings.exposure == 10000
        assert camera_settings.gain == 2.0
        print("✅ CameraSettings 模型测试通过")
        
        # 测试PolarAlignStatus
        polar_status = PolarAlignStatus(
            is_running=True,
            progress=50.0,
            azimuth_error=1.5,
            altitude_error=2.0
        )
        assert polar_status.is_running == True
        assert polar_status.progress == 50.0
        print("✅ PolarAlignStatus 模型测试通过")
        
        # 测试CameraPreset
        preset = CameraPreset(
            name="测试预设",
            description="测试描述",
            exposure_us=15000,
            analogue_gain=3.0,
            digital_gain=1.5
        )
        assert preset.name == "测试预设"
        assert preset.exposure_us == 15000
        print("✅ CameraPreset 模型测试通过")
        
        return True
        
    except Exception as e:
        print(f"❌ 数据模型测试失败: {e}")
        return False


def test_app_integration():
    """测试应用集成"""
    print("\n🔍 测试应用集成...")
    
    try:
        from ogscope.web.app import app
        
        # 检查应用是否正确创建
        assert app is not None
        print("✅ FastAPI应用创建成功")
        
        # 检查路由是否正确注册
        routes = [route for route in app.routes]
        api_routes = [route for route in routes if hasattr(route, 'path') and route.path.startswith('/api')]
        print(f"✅ API路由注册成功: {len(api_routes)} 个")
        
        return True
        
    except Exception as e:
        print(f"❌ 应用集成测试失败: {e}")
        return False


def test_directory_structure():
    """测试目录结构"""
    print("\n🔍 测试目录结构...")
    
    import os
    from pathlib import Path
    
    api_dir = Path("ogscope/web/api")
    
    # 检查主要目录
    required_dirs = [
        "camera",
        "debug", 
        "alignment",
        "system",
        "models"
    ]
    
    for dir_name in required_dirs:
        dir_path = api_dir / dir_name
        if dir_path.exists():
            print(f"✅ 目录存在: {dir_name}")
        else:
            print(f"❌ 目录缺失: {dir_name}")
            return False
    
    # 检查主要文件
    required_files = [
        "main.py",
        "camera/routes.py",
        "debug/routes.py",
        "debug/services.py",
        "alignment/routes.py",
        "system/routes.py",
        "models/schemas.py"
    ]
    
    for file_name in required_files:
        file_path = api_dir / file_name
        if file_path.exists():
            print(f"✅ 文件存在: {file_name}")
        else:
            print(f"❌ 文件缺失: {file_name}")
            return False
    
    return True


def main():
    """主测试函数"""
    print("🚀 开始API重构测试...")
    print("=" * 50)
    
    tests = [
        ("目录结构", test_directory_structure),
        ("模块导入", test_api_imports),
        ("路由注册", test_router_registration),
        ("数据模型", test_data_models),
        ("应用集成", test_app_integration),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} 测试通过")
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！API重构成功！")
        print("\n📁 新的API结构:")
        print("ogscope/web/api/")
        print("├── main.py              # 主路由文件")
        print("├── camera/")
        print("│   └── routes.py         # 相机API路由")
        print("├── debug/")
        print("│   ├── routes.py         # 调试控制台API路由")
        print("│   └── services.py       # 调试控制台服务层")
        print("├── alignment/")
        print("│   └── routes.py         # 极轴校准API路由")
        print("├── system/")
        print("│   └── routes.py         # 系统API路由")
        print("└── models/")
        print("    └── schemas.py        # 数据模型定义")
        
        print("\n✨ 重构优势:")
        print("- 模块化设计，职责清晰")
        print("- 易于维护和扩展")
        print("- 代码复用性更好")
        print("- 符合最佳实践")
    else:
        print("⚠️ 部分测试失败，请检查错误信息并修复问题。")
    
    return passed == total


if __name__ == "__main__":
    main()
