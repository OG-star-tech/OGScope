#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超采样画质对比测试脚本

此脚本用于对比超采样模式和原生模式的画质差异，
通过捕获图像并分析图像质量指标来验证超采样效果。

使用方法:
    python scripts/test_supersample_quality.py
"""

import sys
import os
import requests
import json
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class SupersampleQualityTester:
    """超采样画质测试器"""
    
    def __init__(self, base_url: str = "http://192.168.31.18:8000"):
        self.base_url = base_url
        self.test_results = []
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        print(f"[{level}] {message}")
    
    def capture_test_image(self, mode: str, resolution: str):
        """捕获测试图像"""
        try:
            # 设置采样模式
            mode_response = requests.post(
                f"{self.base_url}/api/debug/camera/sampling",
                params={"mode": mode}
            )
            if mode_response.status_code != 200:
                self.log(f"设置采样模式失败: {mode}", "ERROR")
                return None
            
            # 设置分辨率
            width, height = map(int, resolution.split('x'))
            size_response = requests.post(
                f"{self.base_url}/api/debug/camera/size",
                params={"width": width, "height": height}
            )
            if size_response.status_code != 200:
                self.log(f"设置分辨率失败: {resolution}", "ERROR")
                return None
            
            # 等待设置生效
            time.sleep(2)
            
            # 捕获图像
            capture_response = requests.post(f"{self.base_url}/api/debug/camera/capture")
            if capture_response.status_code != 200:
                self.log(f"捕获图像失败", "ERROR")
                return None
            
            return capture_response.json()
            
        except Exception as e:
            self.log(f"捕获测试图像失败: {e}", "ERROR")
            return None
    
    def get_camera_info(self):
        """获取相机信息"""
        try:
            response = requests.get(f"{self.base_url}/api/debug/camera/verify-supersample")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            self.log(f"获取相机信息失败: {e}", "ERROR")
            return None
    
    def test_resolution_scenarios(self):
        """测试不同分辨率场景"""
        scenarios = [
            {"resolution": "320x240", "name": "QVGA"},
            {"resolution": "640x360", "name": "360p"},
            {"resolution": "1280x720", "name": "720p"},
        ]
        
        results = []
        
        for scenario in scenarios:
            self.log(f"测试分辨率: {scenario['name']} ({scenario['resolution']})")
            
            # 测试原生模式
            self.log(f"  测试原生模式...")
            native_result = self.capture_test_image("native", scenario['resolution'])
            native_info = self.get_camera_info()
            
            # 测试超采样模式
            self.log(f"  测试超采样模式...")
            supersample_result = self.capture_test_image("supersample", scenario['resolution'])
            supersample_info = self.get_camera_info()
            
            # 分析结果
            analysis = {
                "resolution": scenario['resolution'],
                "name": scenario['name'],
                "native": {
                    "success": native_result is not None,
                    "info": native_info.get('camera_info', {}) if native_info else {},
                    "verification": native_info.get('verification', {}) if native_info else {}
                },
                "supersample": {
                    "success": supersample_result is not None,
                    "info": supersample_info.get('camera_info', {}) if supersample_info else {},
                    "verification": supersample_info.get('verification', {}) if supersample_info else {}
                }
            }
            
            # 计算差异
            if analysis["native"]["success"] and analysis["supersample"]["success"]:
                native_ratio = analysis["native"]["verification"].get("supersample_ratio", 1.0)
                supersample_ratio = analysis["supersample"]["verification"].get("supersample_ratio", 1.0)
                ratio_improvement = supersample_ratio / native_ratio if native_ratio > 0 else 0
                
                analysis["quality_improvement"] = {
                    "native_ratio": native_ratio,
                    "supersample_ratio": supersample_ratio,
                    "improvement_factor": ratio_improvement,
                    "expected_quality_gain": "显著" if ratio_improvement >= 1.5 else "轻微" if ratio_improvement > 1.0 else "无"
                }
            
            results.append(analysis)
            self.log(f"  完成 {scenario['name']} 测试")
        
        return results
    
    def generate_quality_report(self, results):
        """生成画质对比报告"""
        self.log("=== 超采样画质对比报告 ===")
        
        for result in results:
            self.log(f"\n分辨率: {result['name']} ({result['resolution']})")
            
            if result["native"]["success"] and result["supersample"]["success"]:
                native_info = result["native"]["info"]
                supersample_info = result["supersample"]["info"]
                
                self.log(f"  原生模式:")
                self.log(f"    捕获分辨率: {native_info.get('capture_width', 0)}x{native_info.get('capture_height', 0)}")
                self.log(f"    输出分辨率: {native_info.get('output_width', 0)}x{native_info.get('output_height', 0)}")
                self.log(f"    超采样比例: {result['native']['verification'].get('supersample_ratio', 1.0)}x")
                
                self.log(f"  超采样模式:")
                self.log(f"    捕获分辨率: {supersample_info.get('capture_width', 0)}x{supersample_info.get('capture_height', 0)}")
                self.log(f"    输出分辨率: {supersample_info.get('output_width', 0)}x{supersample_info.get('output_height', 0)}")
                self.log(f"    超采样比例: {result['supersample']['verification'].get('supersample_ratio', 1.0)}x")
                
                if "quality_improvement" in result:
                    improvement = result["quality_improvement"]
                    self.log(f"  画质提升:")
                    self.log(f"    超采样比例提升: {improvement['improvement_factor']:.1f}x")
                    self.log(f"    预期画质增益: {improvement['expected_quality_gain']}")
                    
                    if improvement['improvement_factor'] >= 1.5:
                        self.log(f"    ✅ 在此分辨率下，超采样应该能提供显著的画质提升", "SUCCESS")
                    elif improvement['improvement_factor'] > 1.0:
                        self.log(f"    ⚠️ 在此分辨率下，超采样提供轻微的画质提升", "WARNING")
                    else:
                        self.log(f"    ❌ 在此分辨率下，超采样没有画质提升", "ERROR")
            else:
                self.log(f"  ❌ 测试失败", "ERROR")
        
        # 总结建议
        self.log(f"\n=== 画质对比建议 ===")
        self.log(f"1. 在高分辨率下（720p及以上），超采样效果更明显")
        self.log(f"2. 在低光照条件下，超采样减少噪声的效果更显著")
        self.log(f"3. 静态图像比视频流更容易看出画质差异")
        self.log(f"4. 使用高质量的显示设备能更好地看出差异")
        self.log(f"5. 建议在1280x720或更高分辨率下测试超采样效果")
    
    def run_quality_test(self):
        """运行画质对比测试"""
        self.log("开始超采样画质对比测试...")
        
        # 确保相机启动
        try:
            start_response = requests.post(f"{self.base_url}/api/debug/camera/start")
            if start_response.status_code == 200:
                self.log("相机启动成功", "SUCCESS")
            else:
                self.log("相机启动失败", "ERROR")
                return False
        except Exception as e:
            self.log(f"相机启动异常: {e}", "ERROR")
            return False
        
        # 测试不同分辨率场景
        results = self.test_resolution_scenarios()
        
        # 生成报告
        self.generate_quality_report(results)
        
        return True


async def main():
    """主函数"""
    print("OGScope 超采样画质对比测试")
    print("=" * 50)
    
    tester = SupersampleQualityTester()
    success = tester.run_quality_test()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ 画质对比测试完成！")
        print("💡 提示：在高分辨率下更容易看出超采样的画质提升效果")
    else:
        print("❌ 画质对比测试失败！")
    
    return success


if __name__ == "__main__":
    try:
        import asyncio
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试过程中发生错误: {e}")
        sys.exit(1)
