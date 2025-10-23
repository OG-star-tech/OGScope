#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试噪点水平修复
验证噪点水平不再显示为0
"""

import asyncio
import sys
import os
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ogscope.hardware.camera import IMX327MIPICamera


def test_noise_level_calculation():
    """测试噪点水平计算"""
    print("🔍 测试噪点水平计算...")
    
    # 创建测试配置
    test_configs = [
        {
            "name": "低增益测试",
            "config": {
                "width": 640,
                "height": 360,
                "fps": 5,
                "exposure_us": 10000,
                "analogue_gain": 1.0,
                "digital_gain": 1.0,
                "noise_reduction": 0,
                "night_mode": False
            }
        },
        {
            "name": "中等增益测试",
            "config": {
                "width": 640,
                "height": 360,
                "fps": 5,
                "exposure_us": 20000,
                "analogue_gain": 4.0,
                "digital_gain": 1.0,
                "noise_reduction": 0,
                "night_mode": False
            }
        },
        {
            "name": "高增益测试",
            "config": {
                "width": 640,
                "height": 360,
                "fps": 5,
                "exposure_us": 30000,
                "analogue_gain": 8.0,
                "digital_gain": 2.0,
                "noise_reduction": 1,
                "night_mode": False
            }
        },
        {
            "name": "夜间模式测试",
            "config": {
                "width": 640,
                "height": 360,
                "fps": 5,
                "exposure_us": 50000,
                "analogue_gain": 12.0,
                "digital_gain": 2.0,
                "noise_reduction": 2,
                "night_mode": True
            }
        }
    ]
    
    results = []
    
    for test_case in test_configs:
        print(f"\n📊 {test_case['name']}:")
        
        # 创建相机实例（不初始化硬件）
        camera = IMX327MIPICamera(test_case['config'])
        
        # 手动设置参数（模拟初始化后的状态）
        camera.exposure_us = test_case['config']['exposure_us']
        camera.analogue_gain = test_case['config']['analogue_gain']
        camera.digital_gain = test_case['config']['digital_gain']
        camera.noise_reduction = test_case['config']['noise_reduction']
        camera.night_mode = test_case['config']['night_mode']
        camera.is_initialized = True  # 模拟初始化状态
        
        # 获取质量指标
        quality_metrics = camera.get_image_quality_metrics()
        
        # 检查结果
        noise_level = quality_metrics.get('noise_level', 0.0)
        exposure_adequacy = quality_metrics.get('exposure_adequacy', 0.0)
        gain_level = quality_metrics.get('gain_level', 0.0)
        recommendations = quality_metrics.get('recommended_adjustments', [])
        
        print(f"  噪点水平: {noise_level:.3f} ({noise_level*100:.0f}%)")
        print(f"  曝光充足度: {exposure_adequacy:.3f} ({exposure_adequacy*100:.0f}%)")
        print(f"  增益水平: {gain_level:.3f} ({gain_level*100:.0f}%)")
        print(f"  建议数量: {len(recommendations)}")
        
        # 验证噪点水平不为0
        if noise_level > 0:
            print(f"  ✅ 噪点水平正常: {noise_level:.3f}")
            test_passed = True
        else:
            print(f"  ❌ 噪点水平异常: {noise_level}")
            test_passed = False
        
        results.append({
            "test_name": test_case['name'],
            "noise_level": noise_level,
            "exposure_adequacy": exposure_adequacy,
            "gain_level": gain_level,
            "passed": test_passed,
            "config": test_case['config']
        })
    
    return results


def test_different_gain_levels():
    """测试不同增益级别的噪点水平"""
    print("\n🔬 测试不同增益级别的噪点水平...")
    
    gain_levels = [1.0, 1.5, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0]
    results = []
    
    for gain in gain_levels:
        config = {
            "width": 640,
            "height": 360,
            "fps": 5,
            "exposure_us": 20000,
            "analogue_gain": gain,
            "digital_gain": 1.0,
            "noise_reduction": 0,
            "night_mode": False
        }
        
        camera = IMX327MIPICamera(config)
        camera.exposure_us = config['exposure_us']
        camera.analogue_gain = config['analogue_gain']
        camera.digital_gain = config['digital_gain']
        camera.noise_reduction = config['noise_reduction']
        camera.night_mode = config['night_mode']
        camera.is_initialized = True
        
        quality_metrics = camera.get_image_quality_metrics()
        noise_level = quality_metrics.get('noise_level', 0.0)
        
        print(f"  增益 {gain:4.1f}x -> 噪点水平: {noise_level:.3f} ({noise_level*100:.0f}%)")
        
        results.append({
            "gain": gain,
            "noise_level": noise_level
        })
    
    return results


def test_noise_reduction_effect():
    """测试降噪效果"""
    print("\n🔇 测试降噪效果...")
    
    noise_reduction_levels = [0, 1, 2, 3, 4]
    base_config = {
        "width": 640,
        "height": 360,
        "fps": 5,
        "exposure_us": 20000,
        "analogue_gain": 8.0,
        "digital_gain": 2.0,
        "night_mode": False
    }
    
    results = []
    
    for nr_level in noise_reduction_levels:
        config = {**base_config, "noise_reduction": nr_level}
        
        camera = IMX327MIPICamera(config)
        camera.exposure_us = config['exposure_us']
        camera.analogue_gain = config['analogue_gain']
        camera.digital_gain = config['digital_gain']
        camera.noise_reduction = config['noise_reduction']
        camera.night_mode = config['night_mode']
        camera.is_initialized = True
        
        quality_metrics = camera.get_image_quality_metrics()
        noise_level = quality_metrics.get('noise_level', 0.0)
        
        print(f"  降噪级别 {nr_level} -> 噪点水平: {noise_level:.3f} ({noise_level*100:.0f}%)")
        
        results.append({
            "noise_reduction": nr_level,
            "noise_level": noise_level
        })
    
    return results


async def main():
    """主测试函数"""
    print("🚀 开始噪点水平修复测试")
    print("=" * 50)
    
    try:
        # 测试基本噪点计算
        basic_results = test_noise_level_calculation()
        
        # 测试不同增益级别
        gain_results = test_different_gain_levels()
        
        # 测试降噪效果
        nr_results = test_noise_reduction_effect()
        
        # 汇总结果
        print("\n📋 测试结果汇总:")
        print("=" * 50)
        
        passed_tests = sum(1 for r in basic_results if r['passed'])
        total_tests = len(basic_results)
        
        print(f"基本测试: {passed_tests}/{total_tests} 通过")
        
        # 检查是否有噪点水平为0的情况
        zero_noise_cases = [r for r in basic_results if r['noise_level'] == 0.0]
        if zero_noise_cases:
            print(f"❌ 发现 {len(zero_noise_cases)} 个噪点水平为0的测试用例:")
            for case in zero_noise_cases:
                print(f"   - {case['test_name']}")
        else:
            print("✅ 所有测试用例的噪点水平都不为0")
        
        # 检查增益与噪点的关系
        print(f"\n增益测试: 测试了 {len(gain_results)} 个增益级别")
        min_noise = min(r['noise_level'] for r in gain_results)
        max_noise = max(r['noise_level'] for r in gain_results)
        print(f"噪点水平范围: {min_noise:.3f} - {max_noise:.3f}")
        
        # 检查降噪效果
        print(f"\n降噪测试: 测试了 {len(nr_results)} 个降噪级别")
        nr_levels = [r['noise_level'] for r in nr_results]
        if nr_levels[0] > nr_levels[-1]:
            print("✅ 降噪效果正常：降噪级别越高，噪点水平越低")
        else:
            print("⚠️ 降噪效果异常：降噪级别与噪点水平关系不符合预期")
        
        # 保存测试结果
        test_summary = {
            "timestamp": "2024-01-01T00:00:00Z",
            "basic_tests": basic_results,
            "gain_tests": gain_results,
            "noise_reduction_tests": nr_results,
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "zero_noise_cases": len(zero_noise_cases),
                "min_noise_level": min_noise,
                "max_noise_level": max_noise
            }
        }
        
        output_file = project_root / "test_noise_level_results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(test_summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 测试结果已保存到: {output_file}")
        
        if passed_tests == total_tests and len(zero_noise_cases) == 0:
            print("\n🎉 所有测试通过！噪点水平修复成功！")
            return True
        else:
            print(f"\n⚠️ 测试未完全通过，需要进一步检查")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)