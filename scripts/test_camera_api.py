#!/usr/bin/env python3
"""
简单的相机API测试脚本
"""
import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000/api/debug/camera"

async def test_api():
    """测试相机API"""
    print("🔍 测试相机API...")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. 检查状态
        print("\n1. 检查相机状态...")
        try:
            response = await client.get(f"{BASE_URL}/status")
            print(f"状态码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"状态数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
                if not data.get("connected"):
                    print("❌ 相机未连接，尝试启动...")
                    
                    # 2. 尝试启动相机
                    print("\n2. 尝试启动相机...")
                    try:
                        start_response = await client.post(f"{BASE_URL}/start")
                        print(f"启动状态码: {start_response.status_code}")
                        if start_response.status_code == 200:
                            start_data = start_response.json()
                            print(f"启动结果: {json.dumps(start_data, indent=2, ensure_ascii=False)}")
                            
                            if start_data.get("success"):
                                print("✅ 相机启动成功")
                                
                                # 3. 重新检查状态
                                print("\n3. 重新检查状态...")
                                status_response = await client.get(f"{BASE_URL}/status")
                                if status_response.status_code == 200:
                                    status_data = status_response.json()
                                    print(f"新状态: {json.dumps(status_data, indent=2, ensure_ascii=False)}")
                                    
                                    if status_data.get("streaming"):
                                        print("✅ 相机正在流式传输")
                                        
                                        # 4. 测试预览
                                        print("\n4. 测试预览...")
                                        try:
                                            preview_response = await client.get(f"{BASE_URL}/preview")
                                            print(f"预览状态码: {preview_response.status_code}")
                                            print(f"预览内容类型: {preview_response.headers.get('content-type', 'unknown')}")
                                            print(f"预览数据大小: {len(preview_response.content)} bytes")
                                            
                                            if preview_response.status_code == 200 and preview_response.headers.get('content-type', '').startswith('image/'):
                                                print("✅ 预览功能正常")
                                                
                                                # 5. 测试直方图
                                                print("\n5. 测试直方图...")
                                                try:
                                                    hist_response = await client.get(f"{BASE_URL}/image-histogram")
                                                    print(f"直方图状态码: {hist_response.status_code}")
                                                    if hist_response.status_code == 200:
                                                        hist_data = hist_response.json()
                                                        print(f"直方图结果: {json.dumps(hist_data, indent=2, ensure_ascii=False)}")
                                                        
                                                        if hist_data.get("success"):
                                                            print("✅ 直方图功能正常")
                                                        else:
                                                            print("❌ 直方图功能异常")
                                                    else:
                                                        print(f"❌ 直方图请求失败: {hist_response.text}")
                                                except Exception as e:
                                                    print(f"❌ 直方图测试异常: {e}")
                                            else:
                                                print("❌ 预览功能异常")
                                        except Exception as e:
                                            print(f"❌ 预览测试异常: {e}")
                                    else:
                                        print("❌ 相机未在流式传输")
                                else:
                                    print(f"❌ 状态检查失败: {status_response.status_code}")
                            else:
                                print("❌ 相机启动失败")
                        else:
                            print(f"❌ 启动请求失败: {start_response.text}")
                    except Exception as e:
                        print(f"❌ 启动测试异常: {e}")
                else:
                    print("✅ 相机已连接")
                    if data.get("streaming"):
                        print("✅ 相机正在流式传输")
                    else:
                        print("⚠️  相机未在流式传输")
            else:
                print(f"❌ 状态检查失败: {response.text}")
        except Exception as e:
            print(f"❌ 状态检查异常: {e}")

if __name__ == "__main__":
    asyncio.run(test_api())
