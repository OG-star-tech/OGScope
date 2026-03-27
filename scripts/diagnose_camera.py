#!/usr/bin/env python3
"""
相机诊断脚本
用于检查相机初始化、启动和运行状态
"""
import asyncio
import httpx
import json
import sys
from pathlib import Path

BASE_URL = "http://localhost:8000/api/debug/camera"

async def check_camera_status(client):
    """检查相机状态 / Check camera status"""
    print("🔍 检查相机状态...")
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

async def start_camera(client):
    """启动相机 / Start camera"""
    print("\n🚀 尝试启动相机...")
    try:
        response = await client.post(f"{BASE_URL}/start")
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ 相机启动结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
        return result.get("success", False)
        
    except httpx.HTTPStatusError as e:
        print(f"❌ 启动失败 - HTTP错误: {e.response.status_code} - {e.response.text}")
        return False
    except httpx.RequestError as e:
        print(f"❌ 启动失败 - 请求错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 启动失败 - 意外错误: {e}")
        return False

async def test_preview(client):
    """测试预览功能 / Test preview functionality"""
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

async def test_histogram(client):
    """测试直方图功能 / Test the histogram function"""
    print("\n📈 测试直方图功能...")
    try:
        response = await client.get(f"{BASE_URL}/image-histogram")
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            histogram_data = result.get("histogram", {})
            print("✅ 直方图数据获取成功")
            
            if "error" in histogram_data:
                print(f"⚠️  直方图错误: {histogram_data['error']}")
                return False
            
            if "histogram" in histogram_data and histogram_data["histogram"]:
                print(f"  - 灰度直方图数据点: {len(histogram_data['histogram'])}")
            
            if "statistics" in histogram_data:
                stats = histogram_data["statistics"]
                print(f"  - 平均亮度: {stats.get('mean_brightness', 'N/A')}")
                print(f"  - 暗部像素: {stats.get('dark_pixels_percent', 'N/A')}%")
            
            return True
        else:
            print(f"❌ 直方图获取失败: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 直方图测试失败: {e}")
        return False

async def check_system_dependencies():
    """检查系统依赖 / Check system dependencies"""
    print("\n🔧 检查系统依赖...")
    
    # 检查 Picamera2 / Check Picamera2
    try:
        import picamera2
        print("✅ Picamera2 已安装")
    except ImportError:
        print("❌ Picamera2 未安装")
        print("   请运行: sudo apt install python3-picamera2")
        return False
    
    # 检查 OpenCV / Check OpenCV
    try:
        import cv2
        print("✅ OpenCV 已安装")
    except ImportError:
        print("⚠️  OpenCV 未安装 (直方图功能需要)")
        print("   请运行: sudo apt install python3-opencv")
        print("   或: pip install opencv-python-headless")
    
    # 检查 NumPy / Check NumPy
    try:
        import numpy
        print("✅ NumPy 已安装")
    except ImportError:
        print("❌ NumPy 未安装")
        return False
    
    return True

async def check_camera_hardware():
    """检查相机硬件 / Check camera hardware"""
    print("\n📱 检查相机硬件...")
    
    # 检查相机设备 / Check camera equipment
    camera_devices = [
        "/dev/video0",
        "/dev/video1", 
        "/dev/video2",
        "/dev/video3"
    ]
    
    found_devices = []
    for device in camera_devices:
        if Path(device).exists():
            found_devices.append(device)
    
    if found_devices:
        print(f"✅ 找到相机设备: {', '.join(found_devices)}")
    else:
        print("❌ 未找到相机设备")
        print("   请检查相机连接和驱动")
        return False
    
    # 检查 libcamera / Check libcamera
    try:
        import subprocess
        result = subprocess.run(["libcamera-hello", "--list-cameras"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ libcamera 可用")
            if result.stdout:
                print(f"   检测到的相机: {result.stdout.strip()}")
        else:
            print("⚠️  libcamera-hello 命令失败")
    except Exception as e:
        print(f"⚠️  无法检查 libcamera: {e}")
    
    return True

async def main():
    """主诊断函数 / Main diagnostic function"""
    print("🔍 OGScope 相机诊断工具")
    print("=" * 50)
    
    # 检查系统依赖 / Check system dependencies
    deps_ok = await check_system_dependencies()
    
    # 检查相机硬件 / Check camera hardware
    hw_ok = await check_camera_hardware()
    
    if not deps_ok or not hw_ok:
        print("\n❌ 系统检查失败，请先解决依赖问题")
        sys.exit(1)
    
    # 检查服务状态 / Check service status
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 检查相机状态 / Check camera status
        status_ok = await check_camera_status(client)
        
        if not status_ok:
            # 尝试启动相机 / Try launching the camera
            start_ok = await start_camera(client)
            
            if start_ok:
                # 重新检查状态 / Recheck status
                status_ok = await check_camera_status(client)
        
        if status_ok:
            # 测试预览 / Test preview
            preview_ok = await test_preview(client)
            
            # 测试直方图 / Test histogram
            histogram_ok = await test_histogram(client)
            
            print("\n🎉 诊断完成!")
            print(f"相机状态: {'✅ 正常' if status_ok else '❌ 异常'}")
            print(f"预览功能: {'✅ 正常' if preview_ok else '❌ 异常'}")
            print(f"直方图功能: {'✅ 正常' if histogram_ok else '❌ 异常'}")
            
            if status_ok and preview_ok:
                print("\n✅ 相机系统运行正常!")
                if histogram_ok:
                    print("✅ 直方图功能正常!")
                else:
                    print("⚠️  直方图功能异常，可能需要安装 OpenCV")
            else:
                print("\n❌ 相机系统存在问题，请检查日志")
        else:
            print("\n❌ 相机无法启动，请检查:")
            print("1. 相机硬件连接")
            print("2. 系统服务状态: sudo systemctl status ogscope")
            print("3. 服务日志: sudo journalctl -u ogscope -f")

if __name__ == "__main__":
    asyncio.run(main())
