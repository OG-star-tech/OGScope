"""
环境检测模块
检测是否在树莓派环境中运行
"""
import os
import platform
import subprocess
from pathlib import Path
from typing import Optional


def is_raspberry_pi() -> bool:
    """
    检测是否在树莓派环境中运行
    
    Returns:
        bool: 如果是树莓派环境返回True，否则返回False
    """
    try:
        # 方法1: 检查 /proc/cpuinfo 中的硬件信息
        if Path("/proc/cpuinfo").exists():
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
                if "BCM" in cpuinfo or "Raspberry Pi" in cpuinfo:
                    return True
        
        # 方法2: 检查 /proc/device-tree/model
        if Path("/proc/device-tree/model").exists():
            with open("/proc/device-tree/model", "r") as f:
                model = f.read()
                if "Raspberry Pi" in model:
                    return True
        
        # 方法3: 检查环境变量
        if os.environ.get("RASPBERRY_PI") == "1":
            return True
        
        # 方法4: 检查是否存在树莓派特有的GPIO库
        try:
            import RPi.GPIO
            return True
        except ImportError:
            pass
        
        # 方法5: 检查是否存在picamera2库
        try:
            import picamera2
            return True
        except ImportError:
            pass
            
    except Exception:
        pass
    
    return False


def get_device_info() -> dict:
    """
    获取设备信息
    
    Returns:
        dict: 设备信息字典
    """
    info = {
        "platform": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "is_raspberry_pi": is_raspberry_pi(),
        "python_version": platform.python_version(),
    }
    
    # 如果是Linux系统，尝试获取更多信息
    if platform.system() == "Linux":
        try:
            # 获取CPU信息
            if Path("/proc/cpuinfo").exists():
                with open("/proc/cpuinfo", "r") as f:
                    cpuinfo = f.read()
                    if "Hardware" in cpuinfo:
                        for line in cpuinfo.split("\n"):
                            if line.startswith("Hardware"):
                                info["hardware"] = line.split(":")[1].strip()
                                break
                    if "Model" in cpuinfo:
                        for line in cpuinfo.split("\n"):
                            if line.startswith("Model"):
                                info["model"] = line.split(":")[1].strip()
                                break
            
            # 获取内存信息
            if Path("/proc/meminfo").exists():
                with open("/proc/meminfo", "r") as f:
                    meminfo = f.read()
                    for line in meminfo.split("\n"):
                        if line.startswith("MemTotal"):
                            info["memory_total"] = line.split(":")[1].strip()
                            break
            
        except Exception:
            pass
    
    return info


def get_camera_capabilities() -> dict:
    """
    获取相机能力信息
    
    Returns:
        dict: 相机能力信息
    """
    capabilities = {
        "has_picamera2": False,
        "has_opencv_camera": False,
        "has_usb_camera": False,
        "available_cameras": [],
    }
    
    # 检查picamera2
    try:
        import picamera2
        capabilities["has_picamera2"] = True
        capabilities["available_cameras"].append("picamera2")
    except ImportError:
        pass
    
    # 检查OpenCV相机
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            capabilities["has_opencv_camera"] = True
            capabilities["available_cameras"].append("opencv")
            cap.release()
    except Exception:
        pass
    
    # 检查USB相机
    try:
        import cv2
        for i in range(5):  # 检查前5个设备
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                capabilities["has_usb_camera"] = True
                capabilities["available_cameras"].append(f"usb_camera_{i}")
                cap.release()
                break
    except Exception:
        pass
    
    return capabilities


def should_use_simulation_mode() -> bool:
    """
    判断是否应该使用模拟模式
    
    Returns:
        bool: 如果应该使用模拟模式返回True
    """
    # 强制使用模拟模式的环境变量
    if os.environ.get("OGSCOPE_SIMULATION_MODE") == "1":
        return True
    
    # 强制禁用模拟模式的环境变量
    if os.environ.get("OGSCOPE_SIMULATION_MODE") == "0":
        return False
    
    # 默认逻辑：非树莓派环境使用模拟模式
    return not is_raspberry_pi()


def get_simulation_config() -> dict:
    """
    获取模拟模式配置
    
    Returns:
        dict: 模拟模式配置
    """
    return {
        "enabled": should_use_simulation_mode(),
        "virtual_resolution": (1920, 1080),
        "virtual_fps": 30,
        "virtual_exposure": 10000,  # 微秒
        "virtual_gain": 1.0,
        "star_field_density": 0.1,  # 星点密度
        "polar_star_position": (0.5, 0.3),  # 极轴星位置 (x, y)
        "noise_level": 0.05,  # 噪声水平
        "atmospheric_turbulence": True,  # 大气湍流效果
    }
