#!/usr/bin/env python3
"""
测试图像质量监控功能修复
"""
import asyncio
import httpx
import json
import sys

BASE_URL = "http://localhost:8000/api/debug/camera"

async def test_camera_initialization():
    """测试相机初始化"""
    print("🔍 测试相机初始化...")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 测试相机状态
            response = await client.get(f"{BASE_URL}/status")
            response.raise_for_status()
            result = response.json()
            
            print(f"相机状态: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            if result.get("connected", False):
                print("✅ 相机已连接")
                return True
            else:
                print("❌ 相机未连接")
                return False
                
        except Exception as e:
            print(f"❌ 相机初始化测试失败: {e}")
            return False

async def test_image_quality_api():
    """测试图像质量API"""
    print("\n📊 测试图像质量API...")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{BASE_URL}/image-quality")
            response.raise_for_status()
            result = response.json()
            
            print(f"API响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            if result.get("success", False):
                quality = result.get("quality", {})
                print("\n✅ 图像质量数据:")
                print(f"  - 噪点水平: {quality.get('noise_level', 0):.3f}")
                print(f"  - 曝光充足度: {quality.get('exposure_adequacy', 0):.3f}")
                print(f"  - 增益水平: {quality.get('gain_level', 0):.3f}")
                print(f"  - 夜间模式: {quality.get('night_mode', False)}")
                
                recommendations = quality.get('recommended_adjustments', [])
                if recommendations:
                    print("  - 调整建议:")
                    for rec in recommendations:
                        print(f"    * {rec}")
                else:
                    print("  - 无调整建议")
                
                return True
            else:
                print(f"❌ API返回失败: {result}")
                return False
                
        except Exception as e:
            print(f"❌ 图像质量API测试失败: {e}")
            return False

async def test_camera_start():
    """测试相机启动"""
    print("\n🚀 测试相机启动...")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(f"{BASE_URL}/start")
            response.raise_for_status()
            result = response.json()
            
            print(f"启动结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            if result.get("success", False):
                print("✅ 相机启动成功")
                return True
            else:
                print(f"❌ 相机启动失败: {result}")
                return False
                
        except Exception as e:
            print(f"❌ 相机启动测试失败: {e}")
            return False

async def test_preview_functionality():
    """测试预览功能"""
    print("\n📷 测试预览功能...")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{BASE_URL}/preview")
            response.raise_for_status()
            
            content_type = response.headers.get("content-type", "")
            content_length = len(response.content)
            
            print(f"预览响应:")
            print(f"  - Content-Type: {content_type}")
            print(f"  - Content-Length: {content_length} bytes")
            
            if content_type.startswith("image/"):
                print("✅ 预览图像正常")
                return True
            else:
                print("❌ 预览不是图像格式")
                return False
                
        except Exception as e:
            print(f"❌ 预览功能测试失败: {e}")
            return False

async def main():
    """主测试函数"""
    print("🔧 开始测试图像质量监控功能修复...")
    print("=" * 60)
    
    # 测试相机初始化
    init_ok = await test_camera_initialization()
    
    if not init_ok:
        print("\n❌ 相机初始化失败，请检查:")
        print("1. 相机硬件连接")
        print("2. 系统服务状态: sudo systemctl status ogscope")
        print("3. 服务日志: sudo journalctl -u ogscope -f")
        return False
    
    # 测试相机启动
    start_ok = await test_camera_start()
    
    if start_ok:
        # 等待相机稳定
        print("\n⏳ 等待相机稳定...")
        await asyncio.sleep(2)
        
        # 测试预览功能
        preview_ok = await test_preview_functionality()
        
        # 测试图像质量API
        quality_ok = await test_image_quality_api()
        
        print("\n🎉 测试完成!")
        print(f"相机初始化: {'✅ 正常' if init_ok else '❌ 异常'}")
        print(f"相机启动: {'✅ 正常' if start_ok else '❌ 异常'}")
        print(f"预览功能: {'✅ 正常' if preview_ok else '❌ 异常'}")
        print(f"图像质量API: {'✅ 正常' if quality_ok else '❌ 异常'}")
        
        if init_ok and start_ok and preview_ok and quality_ok:
            print("\n✅ 图像质量监控功能修复成功!")
            print("\n📋 功能说明:")
            print("1. 图像质量指标每3秒自动更新")
            print("2. 支持噪点水平、曝光充足度、增益水平监控")
            print("3. 提供智能调整建议")
            print("4. 支持夜间模式检测")
            print("5. 前端直方图功能已优化")
            print("\n🌐 访问调试控制台: http://localhost:8000/debug")
            return True
        else:
            print("\n❌ 部分功能异常，请检查日志")
            return False
    else:
        print("\n❌ 相机启动失败，无法继续测试")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
