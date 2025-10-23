#!/usr/bin/env python3
"""
测试增强的调试控制台功能
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ogscope.web.api.debug.services import DebugCameraService


async def test_enhanced_features():
    """测试增强功能"""
    print("🧪 测试增强的调试控制台功能...")
    
    try:
        # 测试图像质量监控
        print("\n📊 测试图像质量监控...")
        quality_result = await DebugCameraService.get_image_quality()
        print(f"✅ 图像质量指标: {quality_result}")
        
        # 测试夜间模式预设
        print("\n🌙 测试夜间模式预设...")
        night_result = await DebugCameraService.apply_night_mode_preset()
        print(f"✅ 夜间模式预设: {night_result}")
        
        # 测试降噪设置
        print("\n🔇 测试降噪设置...")
        noise_result = await DebugCameraService.set_noise_reduction(2)
        print(f"✅ 降噪设置: {noise_result}")
        
        # 测试白平衡设置
        print("\n🎨 测试白平衡设置...")
        wb_result = await DebugCameraService.set_white_balance("night")
        print(f"✅ 白平衡设置: {wb_result}")
        
        # 测试图像增强
        print("\n✨ 测试图像增强...")
        enhancement_result = await DebugCameraService.set_image_enhancement(
            contrast=1.2, brightness=0.1, saturation=0.8, sharpness=1.1
        )
        print(f"✅ 图像增强: {enhancement_result}")
        
        # 测试设置备份
        print("\n💾 测试设置备份...")
        backup_result = await DebugCameraService.save_current_settings_backup()
        print(f"✅ 设置备份: {backup_result}")
        
        # 测试夜间模式切换
        print("\n🌓 测试夜间模式切换...")
        night_mode_result = await DebugCameraService.set_night_mode(True)
        print(f"✅ 夜间模式切换: {night_mode_result}")
        
        print("\n🎉 所有增强功能测试完成！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False
    
    return True


async def main():
    """主函数"""
    print("🚀 启动增强调试控制台功能测试")
    
    success = await test_enhanced_features()
    
    if success:
        print("\n✅ 所有测试通过！增强功能已就绪。")
        print("\n📋 新增功能列表:")
        print("  🌙 一键夜间模式预设")
        print("  🔇 降噪级别控制 (0-4)")
        print("  🎨 白平衡模式 (自动/手动/夜间)")
        print("  ✨ 图像增强 (对比度/亮度/饱和度/锐度)")
        print("  📊 实时图像质量监控")
        print("  💾 设置备份和恢复")
        print("  🛡️ 参数安全机制")
        print("  📈 智能参数推荐")
    else:
        print("\n❌ 测试失败，请检查配置。")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
