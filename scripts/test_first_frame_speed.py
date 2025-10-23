#!/usr/bin/env python3
"""
测试第一帧画面出现速度优化效果
"""
import asyncio
import time
import requests
from pathlib import Path
import sys

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def test_first_frame_speed():
    """测试第一帧画面出现速度"""
    base_url = "http://localhost:8000"
    
    print("🔧 OGScope 第一帧画面出现速度测试")
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
    
    # 2. 停止相机（如果正在运行）
    try:
        requests.post(f"{base_url}/api/debug/camera/stop", timeout=5)
        print("🔄 停止现有相机预览")
        await asyncio.sleep(1)  # 等待停止完成
    except:
        pass
    
    # 3. 测试多次启动，测量第一帧出现时间
    test_results = []
    num_tests = 5
    
    print(f"\n📊 开始测试第一帧出现速度（共{num_tests}次）...")
    
    for i in range(num_tests):
        print(f"\n--- 测试 {i+1}/{num_tests} ---")
        
        # 启动相机
        start_time = time.time()
        try:
            response = requests.post(f"{base_url}/api/debug/camera/start", timeout=10)
            if response.status_code != 200:
                print(f"❌ 第{i+1}次启动失败")
                continue
            camera_start_time = time.time() - start_time
            print(f"✅ 相机启动耗时: {camera_start_time:.3f}s")
        except requests.exceptions.RequestException as e:
            print(f"❌ 第{i+1}次启动失败: {e}")
            continue
        
        # 等待并获取第一帧
        first_frame_time = None
        max_wait_time = 5.0  # 最多等待5秒
        check_interval = 0.1  # 每100ms检查一次
        
        print("⏳ 等待第一帧出现...")
        frame_start_time = time.time()
        
        while time.time() - frame_start_time < max_wait_time:
            try:
                response = requests.get(f"{base_url}/api/debug/camera/preview?t={int(time.time()*1000)}", timeout=2)
                if response.status_code == 200 and len(response.content) > 1000:  # 确保不是空帧
                    first_frame_time = time.time() - frame_start_time
                    print(f"✅ 第一帧出现耗时: {first_frame_time:.3f}s")
                    break
            except requests.exceptions.RequestException:
                pass
            
            await asyncio.sleep(check_interval)
        
        if first_frame_time is None:
            print(f"❌ 第{i+1}次测试：5秒内未获取到第一帧")
            continue
        
        # 记录结果
        total_time = camera_start_time + first_frame_time
        test_results.append({
            'test_num': i + 1,
            'camera_start_time': camera_start_time,
            'first_frame_time': first_frame_time,
            'total_time': total_time
        })
        
        print(f"📈 总耗时: {total_time:.3f}s")
        
        # 停止相机
        try:
            requests.post(f"{base_url}/api/debug/camera/stop", timeout=5)
            await asyncio.sleep(1)  # 等待停止完成
        except:
            pass
    
    # 4. 分析结果
    if not test_results:
        print("\n❌ 没有成功的测试结果")
        return False
    
    print("\n📈 测试结果分析:")
    print("-" * 40)
    
    camera_times = [r['camera_start_time'] for r in test_results]
    frame_times = [r['first_frame_time'] for r in test_results]
    total_times = [r['total_time'] for r in test_results]
    
    print(f"测试次数: {len(test_results)}")
    print(f"相机启动平均时间: {sum(camera_times)/len(camera_times):.3f}s")
    print(f"第一帧出现平均时间: {sum(frame_times)/len(frame_times):.3f}s")
    print(f"总平均时间: {sum(total_times)/len(total_times):.3f}s")
    print(f"最快总时间: {min(total_times):.3f}s")
    print(f"最慢总时间: {max(total_times):.3f}s")
    
    # 性能评估
    avg_total_time = sum(total_times) / len(total_times)
    if avg_total_time < 1.0:
        print("🎉 性能优秀！第一帧出现很快")
    elif avg_total_time < 2.0:
        print("✅ 性能良好，第一帧出现较快")
    elif avg_total_time < 3.0:
        print("⚠️  性能一般，第一帧出现较慢")
    else:
        print("❌ 性能需要优化，第一帧出现很慢")
    
    # 详细结果
    print("\n📋 详细结果:")
    for result in test_results:
        print(f"测试{result['test_num']}: 相机启动{result['camera_start_time']:.3f}s + 第一帧{result['first_frame_time']:.3f}s = 总计{result['total_time']:.3f}s")
    
    return True

if __name__ == "__main__":
    print("开始测试第一帧出现速度...")
    asyncio.run(test_first_frame_speed())
    print("\n测试完成！")
