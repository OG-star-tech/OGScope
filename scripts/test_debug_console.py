#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OGScope 调试控制台测试脚本
用于验证调试控制台的基本功能
"""

import asyncio
import json
import requests
from pathlib import Path
import time


class DebugConsoleTester:
    """调试控制台测试器"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.api_base = f"{base_url}/api/debug"
        
    def test_camera_status(self):
        """测试相机状态API"""
        print("🔍 测试相机状态API...")
        try:
            response = requests.get(f"{self.api_base}/camera/status")
            if response.status_code == 200:
                status = response.json()
                print(f"✅ 相机状态: {status}")
                return True
            else:
                print(f"❌ 相机状态API失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 相机状态API异常: {e}")
            return False
    
    def test_camera_start(self):
        """测试相机启动API"""
        print("🔍 测试相机启动API...")
        try:
            response = requests.post(f"{self.api_base}/camera/start")
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 相机启动: {result}")
                return True
            else:
                print(f"❌ 相机启动API失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 相机启动API异常: {e}")
            return False
    
    def test_camera_stop(self):
        """测试相机停止API"""
        print("🔍 测试相机停止API...")
        try:
            response = requests.post(f"{self.api_base}/camera/stop")
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 相机停止: {result}")
                return True
            else:
                print(f"❌ 相机停止API失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 相机停止API异常: {e}")
            return False
    
    def test_camera_preview(self):
        """测试相机预览API"""
        print("🔍 测试相机预览API...")
        try:
            response = requests.get(f"{self.api_base}/camera/preview")
            if response.status_code == 200:
                print(f"✅ 相机预览: 获取到 {len(response.content)} 字节的图像数据")
                return True
            else:
                print(f"❌ 相机预览API失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 相机预览API异常: {e}")
            return False
    
    def test_camera_settings(self):
        """测试相机设置API"""
        print("🔍 测试相机设置API...")
        try:
            settings = {
                "exposure": 15000,
                "gain": 2.0
            }
            response = requests.post(
                f"{self.api_base}/camera/settings",
                json=settings
            )
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 相机设置: {result}")
                return True
            else:
                print(f"❌ 相机设置API失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 相机设置API异常: {e}")
            return False
    
    def test_presets(self):
        """测试预设管理API"""
        print("🔍 测试预设管理API...")
        try:
            # 获取预设列表
            response = requests.get(f"{self.api_base}/camera/presets")
            if response.status_code == 200:
                presets = response.json()
                print(f"✅ 获取预设列表: {len(presets.get('presets', []))} 个预设")
            
            # 保存测试预设
            test_preset = {
                "name": "测试预设",
                "description": "这是一个测试预设",
                "exposure_us": 20000,
                "analogue_gain": 3.0,
                "digital_gain": 1.5
            }
            
            response = requests.post(
                f"{self.api_base}/camera/presets",
                json=test_preset
            )
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 保存预设: {result}")
                return True
            else:
                print(f"❌ 保存预设API失败: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 预设管理API异常: {e}")
            return False
    
    def test_files(self):
        """测试文件管理API"""
        print("🔍 测试文件管理API...")
        try:
            response = requests.get(f"{self.api_base}/files")
            if response.status_code == 200:
                files = response.json()
                print(f"✅ 获取文件列表: {len(files.get('files', []))} 个文件")
                return True
            else:
                print(f"❌ 文件管理API失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 文件管理API异常: {e}")
            return False
    
    def test_web_interface(self):
        """测试Web界面"""
        print("🔍 测试Web界面...")
        try:
            # 测试主页面
            response = requests.get(f"{self.base_url}/")
            if response.status_code == 200:
                print("✅ 主页面加载正常")
            else:
                print(f"❌ 主页面加载失败: {response.status_code}")
                return False
            
            # 测试调试控制台页面
            response = requests.get(f"{self.base_url}/debug")
            if response.status_code == 200:
                print("✅ 调试控制台页面加载正常")
                return True
            else:
                print(f"❌ 调试控制台页面加载失败: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Web界面测试异常: {e}")
            return False
    
    def check_dependencies(self):
        """检查依赖项"""
        print("🔍 检查依赖项...")
        
        # 检查OpenCV
        try:
            import cv2
            print("✅ OpenCV 已安装")
        except ImportError:
            print("❌ OpenCV 未安装，请运行: pip install opencv-python")
            return False
        
        # 检查Picamera2
        try:
            import picamera2
            print("✅ Picamera2 已安装")
        except ImportError:
            print("❌ Picamera2 未安装，请运行: sudo apt install python3-picamera2")
            return False
        
        # 检查存储目录
        captures_dir = Path.home() / "dev_captures"
        if captures_dir.exists():
            print(f"✅ 存储目录存在: {captures_dir}")
        else:
            print(f"⚠️ 存储目录不存在，将自动创建: {captures_dir}")
            captures_dir.mkdir(exist_ok=True)
        
        return True
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始调试控制台测试...")
        print("=" * 50)
        
        tests = [
            ("依赖项检查", self.check_dependencies),
            ("Web界面", self.test_web_interface),
            ("相机状态", self.test_camera_status),
            ("相机启动", self.test_camera_start),
            ("相机预览", self.test_camera_preview),
            ("相机设置", self.test_camera_settings),
            ("相机停止", self.test_camera_stop),
            ("预设管理", self.test_presets),
            ("文件管理", self.test_files),
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
            print("🎉 所有测试通过！调试控制台可以正常使用。")
            print("\n📖 使用说明:")
            print("1. 访问 http://localhost:8000/debug 打开调试控制台")
            print("2. 点击 '启动预览' 开始相机预览")
            print("3. 使用 '拍摄控制' 标签页进行拍照和录制")
            print("4. 使用 '参数设置' 标签页调整相机参数")
            print("5. 使用 '预设管理' 标签页保存和加载预设")
            print("6. 使用 '文件管理' 标签页查看和下载文件")
        else:
            print("⚠️ 部分测试失败，请检查错误信息并修复问题。")
        
        return passed == total


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="OGScope 调试控制台测试")
    parser.add_argument("--url", default="http://localhost:8000", 
                       help="服务器URL (默认: http://localhost:8000)")
    parser.add_argument("--test", choices=["all", "api", "web", "deps"], 
                       default="all", help="测试类型")
    
    args = parser.parse_args()
    
    tester = DebugConsoleTester(args.url)
    
    if args.test == "all":
        tester.run_all_tests()
    elif args.test == "api":
        tester.test_camera_status()
        tester.test_camera_start()
        tester.test_camera_preview()
        tester.test_camera_stop()
    elif args.test == "web":
        tester.test_web_interface()
    elif args.test == "deps":
        tester.check_dependencies()


if __name__ == "__main__":
    main()
