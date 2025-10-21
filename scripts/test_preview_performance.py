#!/usr/bin/env python3
"""
测试调试控制台预览性能优化效果
"""
import asyncio
import time
import requests
from pathlib import Path
import sys

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def test_preview_performance():
    """测试预览性能"""
    base_url = "http://localhost:8000"
    
    print("🔧 OGScope 调试控制台预览性能测试")
    print("=" * 50)
    
    # 1. 检查服务是否运行
    try:
        response = requests.get(f"{base_url}/api/debug/camera/status", timeout=5)
        if response.status_code != 200:
            print("❌ 调试控制台服务未运行")
            return False
        print("✅ 调试控制台服务运行正常")
    except requests.exceptions.RequestException:
        print("❌ 无法连接到调试控制台服务")
        print("请确保服务正在运行: poetry run python -m ogscope.main")
        return False
    
    # 2. 启动相机预览
    try:
        response = requests.post(f"{base_url}/api/debug/camera/start", timeout=10)
        if response.status_code != 200:
            print("❌ 启动相机预览失败")
            return False
        print("✅ 相机预览已启动")
    except requests.exceptions.RequestException as e:
        print(f"❌ 启动相机预览失败: {e}")
        return False
    
    # 3. 测试预览帧获取性能
    print("\n📊 测试预览帧获取性能...")
    frame_times = []
    successful_requests = 0
    failed_requests = 0
    
    start_time = time.time()
    test_duration = 10  # 测试10秒
    
    while time.time() - start_time < test_duration:
        request_start = time.time()
        try:
            response = requests.get(f"{base_url}/api/debug/camera/preview?t={int(time.time()*1000)}", timeout=2)
            request_time = time.time() - request_start
            
            if response.status_code == 200:
                frame_times.append(request_time)
                successful_requests += 1
                print(f"✅ 帧 {successful_requests}: {request_time:.3f}s, 大小: {len(response.content)} bytes")
            else:
                failed_requests += 1
                print(f"❌ 请求失败: HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            failed_requests += 1
            print("⏰ 请求超时")
        except requests.exceptions.RequestException as e:
            failed_requests += 1
            print(f"❌ 请求异常: {e}")
        
        # 短暂等待，模拟前端请求间隔
        await asyncio.sleep(0.067)  # ~15fps
    
    # 4. 分析结果
    print("\n📈 性能分析结果:")
    print("-" * 30)
    
    if frame_times:
        avg_time = sum(frame_times) / len(frame_times)
        min_time = min(frame_times)
        max_time = max(frame_times)
        actual_fps = len(frame_times) / test_duration
        
        print(f"总请求数: {successful_requests + failed_requests}")
        print(f"成功请求: {successful_requests}")
        print(f"失败请求: {failed_requests}")
        print(f"成功率: {successful_requests/(successful_requests + failed_requests)*100:.1f}%")
        print(f"平均响应时间: {avg_time:.3f}s")
        print(f"最快响应时间: {min_time:.3f}s")
        print(f"最慢响应时间: {max_time:.3f}s")
        print(f"实际帧率: {actual_fps:.1f} fps")
        
        # 性能评估
        if avg_time < 0.1 and actual_fps > 10:
            print("🎉 性能优秀！预览流畅度很好")
        elif avg_time < 0.2 and actual_fps > 5:
            print("✅ 性能良好，预览基本流畅")
        else:
            print("⚠️  性能需要优化，预览可能卡顿")
    else:
        print("❌ 没有成功获取到预览帧")
    
    # 5. 停止相机预览
    try:
        response = requests.post(f"{base_url}/api/debug/camera/stop", timeout=5)
        if response.status_code == 200:
            print("\n✅ 相机预览已停止")
        else:
            print("\n⚠️  停止相机预览失败")
    except requests.exceptions.RequestException:
        print("\n⚠️  停止相机预览时发生异常")
    
    return True

if __name__ == "__main__":
    print("开始测试预览性能...")
    asyncio.run(test_preview_performance())
    print("\n测试完成！")
