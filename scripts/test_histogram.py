#!/usr/bin/env python3
"""
测试直方图功能
"""
import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000/api/debug/camera"

async def test_histogram_endpoint(client):
    """测试直方图API端点"""
    print("\n--- 测试直方图API端点 ---")
    try:
        response = await client.get(f"{BASE_URL}/image-histogram")
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            histogram_data = result.get("histogram", {})
            print("✅ 直方图数据获取成功")
            
            # 检查数据结构
            if "histogram" in histogram_data:
                print(f"  - 灰度直方图数据点数量: {len(histogram_data['histogram'])}")
            
            if "rgb_histogram" in histogram_data:
                rgb_data = histogram_data["rgb_histogram"]
                if rgb_data.get("r"):
                    print(f"  - RGB直方图数据点数量: {len(rgb_data['r'])}")
            
            if "statistics" in histogram_data:
                stats = histogram_data["statistics"]
                print(f"  - 平均亮度: {stats.get('mean_brightness', 'N/A')}")
                print(f"  - 亮度标准差: {stats.get('std_brightness', 'N/A')}")
                print(f"  - 暗部像素比例: {stats.get('dark_pixels_percent', 'N/A')}%")
                print(f"  - 亮部像素比例: {stats.get('bright_pixels_percent', 'N/A')}%")
                print(f"  - 中部像素比例: {stats.get('mid_pixels_percent', 'N/A')}%")
            
            if "exposure_analysis" in histogram_data:
                analysis = histogram_data["exposure_analysis"]
                print(f"  - 曝光分析:")
                print(f"    * 曝光不足: {analysis.get('is_underexposed', False)}")
                print(f"    * 曝光过度: {analysis.get('is_overexposed', False)}")
                print(f"    * 曝光良好: {analysis.get('is_well_exposed', False)}")
                print(f"    * 动态范围: {analysis.get('dynamic_range', 'N/A')}")
            
            return True
        else:
            print(f"❌ 直方图数据获取失败: {result}")
            return False
            
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP错误: {e.response.status_code} - {e.response.text}")
        return False
    except httpx.RequestError as e:
        print(f"❌ 请求错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        return False

async def test_image_quality_with_histogram(client):
    """测试图像质量指标（包含直方图集成）"""
    print("\n--- 测试图像质量指标（含直方图集成）---")
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

async def test_camera_status(client):
    """测试相机状态"""
    print("\n--- 测试相机状态 ---")
    try:
        response = await client.get(f"{BASE_URL}/status")
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ 相机状态: {result}")
        return True
        
    except Exception as e:
        print(f"❌ 获取相机状态失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("🔍 开始测试直方图功能...")
    
    async with httpx.AsyncClient() as client:
        # 测试相机状态
        await test_camera_status(client)
        
        # 测试图像质量指标
        await test_image_quality_with_histogram(client)
        
        # 测试直方图端点
        await test_histogram_endpoint(client)
    
    print("\n🎉 直方图功能测试完成！")
    print("\n📋 使用说明:")
    print("1. 启动调试控制台: http://localhost:8000/debug")
    print("2. 在'图像质量监控'部分找到'曝光直方图'")
    print("3. 点击'显示直方图'按钮")
    print("4. 选择'灰度直方图'或'RGB直方图'")
    print("5. 查看实时直方图和曝光分析")

if __name__ == "__main__":
    asyncio.run(main())
