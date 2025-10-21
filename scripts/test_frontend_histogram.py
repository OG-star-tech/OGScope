#!/usr/bin/env python3
"""
测试前端直方图功能
"""
import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000/api/debug/camera"

async def test_camera_status(client):
    """测试相机状态"""
    print("🔍 测试相机状态...")
    try:
        response = await client.get(f"{BASE_URL}/status")
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ 相机状态: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if not result.get("connected", False):
            print("❌ 相机未连接")
            return False
        
        if not result.get("streaming", False):
            print("⚠️  相机未在流式传输")
            return False
            
        print("✅ 相机状态正常")
        return True
        
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP错误: {e.response.status_code} - {e.response.text}")
        return False
    except httpx.RequestError as e:
        print(f"❌ 请求错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        return False

async def test_preview(client):
    """测试预览功能"""
    print("\n📷 测试预览功能...")
    try:
        response = await client.get(f"{BASE_URL}/preview")
        response.raise_for_status()
        
        content_type = response.headers.get("content-type", "")
        content_length = len(response.content)
        
        print(f"✅ 预览响应:")
        print(f"  - Content-Type: {content_type}")
        print(f"  - Content-Length: {content_length} bytes")
        
        if content_type.startswith("image/"):
            print("✅ 预览图像正常")
            return True
        else:
            print("❌ 预览不是图像格式")
            return False
            
    except httpx.HTTPStatusError as e:
        print(f"❌ 预览失败 - HTTP错误: {e.response.status_code} - {e.response.text}")
        return False
    except httpx.RequestError as e:
        print(f"❌ 预览失败 - 请求错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 预览失败 - 意外错误: {e}")
        return False

async def test_image_quality(client):
    """测试图像质量指标"""
    print("\n📊 测试图像质量指标...")
    try:
        response = await client.get(f"{BASE_URL}/image-quality")
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            quality = result.get("quality", {})
            print("✅ 图像质量指标获取成功")
            print(f"  - 噪点水平: {quality.get('noise_level', 0):.2f}")
            print(f"  - 曝光充足度: {quality.get('exposure_adequacy', 0):.2f}")
            print(f"  - 增益水平: {quality.get('gain_level', 0):.2f}")
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
            print(f"❌ 图像质量指标获取失败: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 测试图像质量指标失败: {e}")
        return False

async def test_histogram_api_removed(client):
    """测试直方图API是否已移除"""
    print("\n🚫 测试直方图API是否已移除...")
    try:
        response = await client.get(f"{BASE_URL}/image-histogram")
        if response.status_code == 404:
            print("✅ 直方图API已成功移除")
            return True
        else:
            print(f"❌ 直方图API仍然存在: {response.status_code}")
            return False
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print("✅ 直方图API已成功移除")
            return True
        else:
            print(f"❌ 直方图API状态异常: {e.response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 测试直方图API失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("🔍 开始测试前端直方图功能...")
    print("=" * 50)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 测试相机状态
        status_ok = await test_camera_status(client)
        
        if status_ok:
            # 测试预览
            preview_ok = await test_preview(client)
            
            # 测试图像质量指标
            quality_ok = await test_image_quality(client)
            
            # 测试直方图API是否已移除
            api_removed_ok = await test_histogram_api_removed(client)
            
            print("\n🎉 测试完成!")
            print(f"相机状态: {'✅ 正常' if status_ok else '❌ 异常'}")
            print(f"预览功能: {'✅ 正常' if preview_ok else '❌ 异常'}")
            print(f"图像质量: {'✅ 正常' if quality_ok else '❌ 异常'}")
            print(f"直方图API移除: {'✅ 成功' if api_removed_ok else '❌ 失败'}")
            
            if status_ok and preview_ok and quality_ok and api_removed_ok:
                print("\n✅ 前端直方图功能准备就绪!")
                print("\n📋 使用说明:")
                print("1. 启动调试控制台: http://localhost:8000/debug")
                print("2. 在'图像质量监控'部分找到'曝光直方图'")
                print("3. 点击'显示直方图'按钮")
                print("4. 选择'灰度直方图'或'RGB直方图'")
                print("5. 查看实时直方图和曝光分析（前端计算）")
                print("\n💡 优势:")
                print("- 减轻开发板计算负担")
                print("- 提高响应速度")
                print("- 无需安装OpenCV")
                print("- 实时图像分析")
            else:
                print("\n❌ 部分功能异常，请检查日志")
        else:
            print("\n❌ 相机无法启动，请检查:")
            print("1. 相机硬件连接")
            print("2. 系统服务状态: sudo systemctl status ogscope")
            print("3. 服务日志: sudo journalctl -u ogscope -f")

if __name__ == "__main__":
    asyncio.run(main())
