#!/usr/bin/env python3
"""
测试重构后的调试控制台功能
"""
import requests
import time
import json
from pathlib import Path

def test_debug_console():
    """测试调试控制台的基本功能"""
    base_url = "http://localhost:8000"
    
    print("🧪 开始测试重构后的调试控制台...")
    
    # 测试1: 检查调试控制台页面是否正常加载
    print("\n1. 测试调试控制台页面加载...")
    try:
        response = requests.get(f"{base_url}/debug")
        if response.status_code == 200:
            print("✅ 调试控制台页面加载成功")
        else:
            print(f"❌ 调试控制台页面加载失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到服务器: {e}")
        return False
    
    # 测试2: 检查相机状态API
    print("\n2. 测试相机状态API...")
    try:
        response = requests.get(f"{base_url}/api/debug/camera/status")
        if response.status_code == 200:
            status = response.json()
            print(f"✅ 相机状态API正常: {status}")
        else:
            print(f"❌ 相机状态API失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 相机状态API异常: {e}")
    
    # 测试3: 检查预设管理API
    print("\n3. 测试预设管理API...")
    try:
        response = requests.get(f"{base_url}/api/debug/camera/presets")
        if response.status_code == 200:
            presets = response.json()
            print(f"✅ 预设管理API正常: {len(presets.get('presets', []))} 个预设")
        else:
            print(f"❌ 预设管理API失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 预设管理API异常: {e}")
    
    # 测试4: 检查文件管理API
    print("\n4. 测试文件管理API...")
    try:
        response = requests.get(f"{base_url}/api/debug/files")
        if response.status_code == 200:
            files = response.json()
            print(f"✅ 文件管理API正常: {len(files.get('files', []))} 个文件")
        else:
            print(f"❌ 文件管理API失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 文件管理API异常: {e}")
    
    # 测试5: 检查JavaScript文件是否存在
    print("\n5. 测试JavaScript文件...")
    try:
        response = requests.get(f"{base_url}/static/js/debug.js")
        if response.status_code == 200:
            print("✅ debug.js 文件存在且可访问")
        else:
            print(f"❌ debug.js 文件访问失败: {response.status_code}")
    except Exception as e:
        print(f"❌ debug.js 文件异常: {e}")
    
    print("\n🎉 调试控制台重构测试完成!")
    return True

if __name__ == "__main__":
    test_debug_console()
