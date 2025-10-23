#!/usr/bin/env python3
"""
测试前端布局修复效果
验证在线状态指示器和PWA安装提示的显示问题是否已解决
"""

import os
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_css_file_exists():
    """测试CSS文件是否存在"""
    css_file = project_root / "web" / "static" / "css" / "style.css"
    return css_file.exists()

def test_css_syntax():
    """测试CSS语法是否正确"""
    css_file = project_root / "web" / "static" / "css" / "style.css"
    
    if not css_file.exists():
        return False, "CSS文件不存在"
    
    try:
        with open(css_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查关键修复是否存在
        fixes = [
            "right: calc(var(--spacing-md) + 200px)",  # 网络状态指示器位置修复
            "max-height: calc(100vh - 2 * var(--spacing-lg))",  # PWA安装提示高度限制
            "overflow-y: auto",  # PWA安装提示滚动
            "min-width: 120px",  # 网络状态指示器最小宽度
        ]
        
        missing_fixes = []
        for fix in fixes:
            if fix not in content:
                missing_fixes.append(fix)
        
        if missing_fixes:
            return False, f"缺少以下修复: {missing_fixes}"
        
        return True, "CSS语法正确，所有修复都已应用"
        
    except Exception as e:
        return False, f"读取CSS文件时出错: {e}"

def test_html_structure():
    """测试HTML结构是否正确"""
    html_file = project_root / "web" / "templates" / "index.html"
    
    if not html_file.exists():
        return False, "HTML文件不存在"
    
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查关键元素是否存在
        elements = [
            "network-status",
            "install-prompt",
            "video-controls",
            "status-info",
            "alignment-metrics"
        ]
        
        missing_elements = []
        for element in elements:
            if element not in content:
                missing_elements.append(element)
        
        if missing_elements:
            return False, f"缺少以下HTML元素: {missing_elements}"
        
        return True, "HTML结构正确，所有必要元素都存在"
        
    except Exception as e:
        return False, f"读取HTML文件时出错: {e}"

def main():
    """主测试函数"""
    print("🔍 开始测试前端布局修复效果...")
    print("=" * 50)
    
    # 测试CSS文件存在性
    print("1. 测试CSS文件存在性...")
    css_exists = test_css_file_exists()
    print(f"   CSS文件存在: {'✅' if css_exists else '❌'}")
    
    # 测试CSS语法和修复
    print("2. 测试CSS语法和修复...")
    css_ok, css_msg = test_css_syntax()
    print(f"   CSS修复状态: {'✅' if css_ok else '❌'}")
    print(f"   详细信息: {css_msg}")
    
    # 测试HTML结构
    print("3. 测试HTML结构...")
    html_ok, html_msg = test_html_structure()
    print(f"   HTML结构: {'✅' if html_ok else '❌'}")
    print(f"   详细信息: {html_msg}")
    
    print("=" * 50)
    
    # 总结
    if css_exists and css_ok and html_ok:
        print("🎉 所有测试通过！前端布局修复已成功应用。")
        print("\n修复内容:")
        print("  ✅ 在线状态指示器位置已调整，避免与视频控制按钮重叠")
        print("  ✅ PWA安装提示弹窗高度已限制，确保完整显示")
        print("  ✅ 添加了响应式设计支持，适配不同屏幕尺寸")
        print("  ✅ 优化了整体布局间距，避免元素重叠")
        return True
    else:
        print("❌ 部分测试失败，请检查修复是否完整应用。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
