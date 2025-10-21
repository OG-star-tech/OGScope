#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超采样功能验证测试脚本

此脚本用于验证 OGScope 的超采样设置是否有效，
确保后续开发中获取的视频流是经过超采样的高质量视频流。

使用方法:
    python scripts/test_supersample.py

测试内容:
1. 验证超采样设置的基本配置
2. 测试不同分辨率下的超采样效果
3. 验证实际捕获图像的尺寸
4. 检查超采样比例和质量评估
"""

import sys
import os
import asyncio
import requests
import json
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ogscope.hardware.camera import create_camera
from ogscope.config import get_settings


class SupersampleTester:
    """超采样测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.test_results = []
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        print(f"[{level}] {message}")
    
    def test_camera_direct(self):
        """直接测试相机类的超采样功能"""
        self.log("=== 直接相机类测试 ===")
        
        try:
            # 创建相机实例
            config = {
                "type": "imx327_mipi",
                "width": 640,
                "height": 360,
                "fps": 5,
                "exposure_us": 10000,
                "analogue_gain": 1.0,
                "rotation": 180,
                "sampling_mode": "supersample",
            }
            
            camera = create_camera(config)
            if not camera:
                self.log("无法创建相机实例", "ERROR")
                return False
            
            # 初始化相机
            if not camera.initialize():
                self.log("相机初始化失败", "ERROR")
                return False
            
            # 获取相机信息
            info = camera.get_camera_info()
            self.log(f"相机信息: {json.dumps(info, indent=2, ensure_ascii=False)}")
            
            # 验证超采样设置
            sampling_mode = info.get('sampling_mode', 'unknown')
            capture_width = info.get('capture_width', 0)
            capture_height = info.get('capture_height', 0)
            output_width = info.get('output_width', 0)
            output_height = info.get('output_height', 0)
            
            if sampling_mode == 'supersample':
                self.log("✓ 超采样模式已启用", "SUCCESS")
                
                if capture_width > output_width and capture_height > output_height:
                    ratio = min(capture_width / output_width, capture_height / output_height)
                    self.log(f"✓ 超采样比例: {ratio:.2f}x", "SUCCESS")
                    
                    if ratio >= 1.5:
                        self.log("✓ 超采样质量: 优秀", "SUCCESS")
                    elif ratio >= 1.2:
                        self.log("✓ 超采样质量: 良好", "SUCCESS")
                    else:
                        self.log("⚠ 超采样质量: 较低", "WARNING")
                else:
                    self.log("✗ 捕获分辨率不高于输出分辨率", "ERROR")
                    return False
            else:
                self.log(f"✗ 当前不是超采样模式: {sampling_mode}", "ERROR")
                return False
            
            # 测试图像捕获
            if camera.start_capture():
                self.log("✓ 相机开始捕获", "SUCCESS")
                
                # 捕获一张图像
                image = camera.capture_image()
                if image is not None:
                    actual_height, actual_width = image.shape[:2]
                    self.log(f"✓ 捕获图像尺寸: {actual_width}x{actual_height}", "SUCCESS")
                    
                    # 验证尺寸是否匹配
                    if actual_width == output_width and actual_height == output_height:
                        self.log("✓ 图像尺寸与预期输出尺寸匹配", "SUCCESS")
                    else:
                        self.log(f"✗ 图像尺寸不匹配！预期: {output_width}x{output_height}, 实际: {actual_width}x{actual_height}", "ERROR")
                        return False
                else:
                    self.log("✗ 无法捕获图像", "ERROR")
                    return False
                
                camera.stop_capture()
            else:
                self.log("✗ 无法启动相机捕获", "ERROR")
                return False
            
            return True
            
        except Exception as e:
            self.log(f"直接测试失败: {e}", "ERROR")
            return False
    
    async def test_api_endpoints(self):
        """测试 API 端点"""
        self.log("=== API 端点测试 ===")
        
        try:
            # 测试超采样验证端点
            response = requests.get(f"{self.base_url}/debug/camera/verify-supersample")
            if response.status_code == 200:
                data = response.json()
                self.log("✓ 超采样验证 API 调用成功", "SUCCESS")
                
                verification = data.get('verification', {})
                self.log(f"验证结果: {json.dumps(verification, indent=2, ensure_ascii=False)}")
                
                if verification.get('is_supersample_active'):
                    self.log("✓ API 确认超采样已激活", "SUCCESS")
                else:
                    self.log("✗ API 确认超采样未激活", "ERROR")
                    return False
            else:
                self.log(f"✗ 超采样验证 API 调用失败: {response.status_code}", "ERROR")
                return False
            
            # 测试图像尺寸验证端点
            response = requests.post(f"{self.base_url}/debug/camera/test-image-size")
            if response.status_code == 200:
                data = response.json()
                self.log("✓ 图像尺寸测试 API 调用成功", "SUCCESS")
                
                test_result = data.get('test_result', {})
                self.log(f"测试结果: {json.dumps(test_result, indent=2, ensure_ascii=False)}")
                
                if test_result.get('supersample_working'):
                    self.log("✓ API 确认超采样功能正常工作", "SUCCESS")
                else:
                    self.log("✗ API 确认超采样功能未正常工作", "ERROR")
                    return False
            else:
                self.log(f"✗ 图像尺寸测试 API 调用失败: {response.status_code}", "ERROR")
                return False
            
            return True
            
        except Exception as e:
            self.log(f"API 测试失败: {e}", "ERROR")
            return False
    
    async def test_different_resolutions(self):
        """测试不同分辨率下的超采样效果"""
        self.log("=== 多分辨率测试 ===")
        
        test_resolutions = [
            {"width": 320, "height": 240, "name": "QVGA"},
            {"width": 640, "height": 360, "name": "360p"},
            {"width": 640, "height": 480, "name": "VGA"},
            {"width": 1280, "height": 720, "name": "720p"},
        ]
        
        results = []
        
        for res in test_resolutions:
            self.log(f"测试分辨率: {res['name']} ({res['width']}x{res['height']})")
            
            try:
                # 设置分辨率
                response = requests.post(
                    f"{self.base_url}/debug/camera/size",
                    params={"width": res["width"], "height": res["height"]}
                )
                
                if response.status_code == 200:
                    self.log(f"✓ {res['name']} 分辨率设置成功", "SUCCESS")
                    
                    # 验证超采样状态
                    response = requests.get(f"{self.base_url}/debug/camera/verify-supersample")
                    if response.status_code == 200:
                        data = response.json()
                        verification = data.get('verification', {})
                        
                        if verification.get('is_supersample_active'):
                            ratio = verification.get('supersample_ratio', 1.0)
                            status = verification.get('verification_status', 'unknown')
                            self.log(f"✓ {res['name']} 超采样比例: {ratio:.2f}x, 状态: {status}", "SUCCESS")
                            results.append({
                                "resolution": res['name'],
                                "width": res["width"],
                                "height": res["height"],
                                "ratio": ratio,
                                "status": status,
                                "success": True
                            })
                        else:
                            self.log(f"✗ {res['name']} 超采样未激活", "ERROR")
                            results.append({
                                "resolution": res['name'],
                                "success": False
                            })
                    else:
                        self.log(f"✗ {res['name']} 验证失败", "ERROR")
                        results.append({
                            "resolution": res['name'],
                            "success": False
                        })
                else:
                    self.log(f"✗ {res['name']} 分辨率设置失败", "ERROR")
                    results.append({
                        "resolution": res['name'],
                        "success": False
                    })
                    
            except Exception as e:
                self.log(f"✗ {res['name']} 测试异常: {e}", "ERROR")
                results.append({
                    "resolution": res['name'],
                    "success": False,
                    "error": str(e)
                })
        
        # 汇总结果
        success_count = sum(1 for r in results if r.get('success', False))
        total_count = len(results)
        
        self.log(f"多分辨率测试完成: {success_count}/{total_count} 成功", 
                "SUCCESS" if success_count == total_count else "WARNING")
        
        return results
    
    def generate_report(self, results: dict):
        """生成测试报告"""
        self.log("=== 测试报告 ===")
        
        report = {
            "timestamp": asyncio.get_event_loop().time(),
            "direct_test": results.get('direct_test', False),
            "api_test": results.get('api_test', False),
            "resolution_tests": results.get('resolution_tests', []),
            "overall_status": "PASS" if all([
                results.get('direct_test', False),
                results.get('api_test', False),
                len([r for r in results.get('resolution_tests', []) if r.get('success', False)]) > 0
            ]) else "FAIL"
        }
        
        self.log(f"总体状态: {report['overall_status']}", 
                "SUCCESS" if report['overall_status'] == "PASS" else "ERROR")
        
        # 保存报告到文件
        report_file = project_root / "test_supersample_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self.log(f"测试报告已保存到: {report_file}")
        
        return report
    
    async def run_all_tests(self):
        """运行所有测试"""
        self.log("开始超采样功能验证测试...")
        
        results = {}
        
        # 1. 直接相机类测试
        results['direct_test'] = self.test_camera_direct()
        
        # 2. API 端点测试
        results['api_test'] = await self.test_api_endpoints()
        
        # 3. 多分辨率测试
        results['resolution_tests'] = await self.test_different_resolutions()
        
        # 4. 生成报告
        report = self.generate_report(results)
        
        return report


async def main():
    """主函数"""
    print("OGScope 超采样功能验证测试")
    print("=" * 50)
    
    # 检查是否在开发环境中运行
    if len(sys.argv) > 1 and sys.argv[1] == "--api-only":
        # 仅测试 API 端点（适用于远程测试）
        base_url = sys.argv[2] if len(sys.argv) > 2 else "http://192.168.31.18:8000"
        tester = SupersampleTester(base_url)
        
        api_result = await tester.test_api_endpoints()
        resolution_results = await tester.test_different_resolutions()
        
        results = {
            'api_test': api_result,
            'resolution_tests': resolution_results
        }
        
        report = tester.generate_report(results)
    else:
        # 完整测试（包括直接相机类测试）
        tester = SupersampleTester()
        report = await tester.run_all_tests()
    
    print("\n" + "=" * 50)
    if report['overall_status'] == 'PASS':
        print("✅ 超采样功能验证通过！")
        print("✅ 后续开发中的视频流将使用超采样的高质量图像")
    else:
        print("❌ 超采样功能验证失败！")
        print("❌ 请检查相机配置和超采样设置")
    
    return report['overall_status'] == 'PASS'


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试过程中发生错误: {e}")
        sys.exit(1)
