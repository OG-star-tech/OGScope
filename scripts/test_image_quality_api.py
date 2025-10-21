#!/usr/bin/env python3
"""
快速测试图像质量API
"""
import asyncio
import httpx
import json

async def test_image_quality_api():
    """测试图像质量API"""
    print("🔍 测试图像质量API...")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 测试图像质量API
            response = await client.get("http://localhost:8000/api/debug/camera/image-quality")
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"响应数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
                if data.get("success"):
                    quality = data.get("quality", {})
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
                    print(f"❌ API返回失败: {data}")
                    return False
            else:
                print(f"❌ HTTP错误: {response.status_code}")
                print(f"响应内容: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(test_image_quality_api())
