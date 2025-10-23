#!/usr/bin/env python3
"""
测试调试控制台修复
验证停止预览和进度条功能是否正常工作
"""

import asyncio
import aiohttp
import json
import time
from pathlib import Path

# 测试配置
BASE_URL = "http://localhost:8000"
DEBUG_URL = f"{BASE_URL}/debug"

async def test_debug_console_fix():
    """测试调试控制台修复"""
    print("🔧 开始测试调试控制台修复...")
    
    async with aiohttp.ClientSession() as session:
        try:
            # 1. 测试相机状态
            print("\n1️⃣ 测试相机状态...")
            async with session.get(f"{BASE_URL}/api/debug/camera/status") as resp:
                if resp.status == 200:
                    status = await resp.json()
                    print(f"   ✅ 相机状态: {status}")
                else:
                    print(f"   ❌ 获取相机状态失败: HTTP {resp.status}")
            
            # 2. 测试启动相机
            print("\n2️⃣ 测试启动相机...")
            async with session.post(f"{BASE_URL}/api/debug/camera/start") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"   ✅ 相机启动: {result}")
                else:
                    error_text = await resp.text()
                    print(f"   ❌ 相机启动失败: HTTP {resp.status} - {error_text}")
            
            # 等待一下确保相机启动
            await asyncio.sleep(2)
            
            # 3. 测试停止相机
            print("\n3️⃣ 测试停止相机...")
            async with session.post(f"{BASE_URL}/api/debug/camera/stop") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"   ✅ 相机停止: {result}")
                else:
                    error_text = await resp.text()
                    print(f"   ❌ 相机停止失败: HTTP {resp.status} - {error_text}")
            
            # 4. 测试进度条相关的API
            print("\n4️⃣ 测试进度条相关功能...")
            
            # 测试分辨率设置（会触发进度条）
            print("   测试分辨率设置...")
            async with session.post(f"{BASE_URL}/api/debug/camera/size?width=1280&height=720") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"   ✅ 分辨率设置: {result}")
                else:
                    error_text = await resp.text()
                    print(f"   ❌ 分辨率设置失败: HTTP {resp.status} - {error_text}")
            
            # 测试采样模式设置（会触发进度条）
            print("   测试采样模式设置...")
            async with session.post(f"{BASE_URL}/api/debug/camera/sampling?mode=supersample") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"   ✅ 采样模式设置: {result}")
                else:
                    error_text = await resp.text()
                    print(f"   ❌ 采样模式设置失败: HTTP {resp.status} - {error_text}")
            
            print("\n✅ 调试控制台修复测试完成！")
            
        except Exception as e:
            print(f"❌ 测试过程中出现错误: {e}")

async def test_frontend_functionality():
    """测试前端功能"""
    print("\n🌐 测试前端功能...")
    
    # 检查HTML文件是否存在
    debug_html = Path("web/templates/debug.html")
    if debug_html.exists():
        print("   ✅ 调试页面HTML文件存在")
        
        # 检查关键元素
        html_content = debug_html.read_text(encoding='utf-8')
        
        required_elements = [
            'id="stop-preview"',
            'id="progress-modal"',
            'id="progress-fill"',
            'id="progress-text"',
            'id="test-progress"'
        ]
        
        for element in required_elements:
            if element in html_content:
                print(f"   ✅ 找到元素: {element}")
            else:
                print(f"   ❌ 缺少元素: {element}")
    else:
        print("   ❌ 调试页面HTML文件不存在")

def main():
    """主函数"""
    print("🚀 OGScope 调试控制台修复测试")
    print("=" * 50)
    
    # 测试前端功能
    test_frontend_functionality()
    
    # 测试后端API
    print("\n" + "=" * 50)
    print("开始API测试...")
    asyncio.run(test_debug_console_fix())
    
    print("\n" + "=" * 50)
    print("📋 修复总结:")
    print("1. ✅ 修复了停止预览按钮的状态检查逻辑")
    print("2. ✅ 改进了相机调试控制器的错误处理")
    print("3. ✅ 增强了进度条管理器的DOM元素初始化")
    print("4. ✅ 添加了后备方案处理DOM元素未找到的情况")
    print("5. ✅ 改进了异步操作的错误处理")
    
    print("\n💡 使用建议:")
    print("- 如果停止预览按钮仍然无法使用，请检查浏览器控制台的错误信息")
    print("- 如果进度条不显示，系统会使用alert作为后备方案")
    print("- 建议在Chrome或Firefox浏览器中测试，确保JavaScript功能正常")

if __name__ == "__main__":
    main()
