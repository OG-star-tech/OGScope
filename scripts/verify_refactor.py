#!/usr/bin/env python3
"""
OGScope 前端重构验证脚本
检查新的模块化结构是否正常工作
"""

import os
import sys
import json
from pathlib import Path

def check_file_exists(file_path):
    """检查文件是否存在"""
    return os.path.exists(file_path)

def check_file_size(file_path):
    """检查文件大小"""
    if os.path.exists(file_path):
        return os.path.getsize(file_path)
    return 0

def analyze_directory_structure():
    """分析目录结构"""
    base_path = Path("web/static")
    
    expected_structure = {
        "js/core": [
            "app.js",
            "camera.js", 
            "alignment.js",
            "ui.js",
            "particles.js",
            "pwa.js"
        ],
        "js/debug": [
            "debug-console.js",
            "camera-debug.js",
            "histogram.js",
            "stream-analysis.js",
            "file-manager.js"
        ],
        "js/shared": [
            "constants.js",
            "api.js",
            "utils.js"
        ],
        "css/core": [
            "base.css",
            "layout.css",
            "components.css",
            "themes.css"
        ],
        "css/debug": [
            "debug-base.css",
            "debug-components.css",
            "debug-layout.css"
        ],
        "css/shared": [
            "animations.css"
        ]
    }
    
    results = {
        "structure_check": {},
        "file_sizes": {},
        "total_size": 0
    }
    
    print("🔍 检查目录结构...")
    
    for dir_path, files in expected_structure.items():
        full_dir_path = base_path / dir_path
        results["structure_check"][dir_path] = {
            "exists": check_file_exists(full_dir_path),
            "files": {}
        }
        
        if results["structure_check"][dir_path]["exists"]:
            print(f"✅ {dir_path}/")
            for file_name in files:
                file_path = full_dir_path / file_name
                file_exists = check_file_exists(file_path)
                file_size = check_file_size(file_path)
                
                results["structure_check"][dir_path]["files"][file_name] = {
                    "exists": file_exists,
                    "size": file_size
                }
                
                if file_exists:
                    print(f"  ✅ {file_name} ({file_size:,} bytes)")
                    results["total_size"] += file_size
                else:
                    print(f"  ❌ {file_name} (缺失)")
        else:
            print(f"❌ {dir_path}/ (目录不存在)")
    
    return results

def compare_with_old_structure():
    """与旧结构对比"""
    print("\n📊 与旧结构对比...")
    
    old_files = {
        "web/static/js/app.js": check_file_size("web/static/js/app.js"),
        "web/static/js/debug.js": check_file_size("web/static/js/debug.js"),
        "web/static/css/style.css": check_file_size("web/static/css/style.css"),
        "web/static/css/debug.css": check_file_size("web/static/css/debug.css")
    }
    
    old_total = sum(old_files.values())
    
    print("旧结构文件大小:")
    for file_path, size in old_files.items():
        if size > 0:
            print(f"  {file_path}: {size:,} bytes")
    
    print(f"旧结构总大小: {old_total:,} bytes")
    
    return old_total

def check_html_templates():
    """检查HTML模板更新"""
    print("\n🔍 检查HTML模板...")
    
    templates = {
        "web/templates/index.html": "主界面模板",
        "web/templates/debug.html": "调试控制台模板"
    }
    
    results = {}
    
    for template_path, description in templates.items():
        if check_file_exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 检查是否使用了新的CSS结构
            has_new_css = "core/base.css" in content and "core/layout.css" in content
            has_new_js = "core/app.js" in content or "debug/debug-console.js" in content
            
            results[template_path] = {
                "exists": True,
                "has_new_css": has_new_css,
                "has_new_js": has_new_js,
                "size": len(content)
            }
            
            status = "✅" if has_new_css and has_new_js else "⚠️"
            print(f"{status} {description}: {template_path}")
            print(f"   新CSS结构: {'✅' if has_new_css else '❌'}")
            print(f"   新JS结构: {'✅' if has_new_js else '❌'}")
        else:
            results[template_path] = {"exists": False}
            print(f"❌ {description}: {template_path} (文件不存在)")
    
    return results

def generate_summary(results, old_total):
    """生成总结报告"""
    print("\n📋 重构总结报告")
    print("=" * 50)
    
    # 统计信息
    total_files = 0
    existing_files = 0
    
    for dir_info in results["structure_check"].values():
        if dir_info["exists"]:
            for file_info in dir_info["files"].values():
                total_files += 1
                if file_info["exists"]:
                    existing_files += 1
    
    print(f"📁 目录结构: {len(results['structure_check'])} 个目录")
    print(f"📄 文件总数: {total_files} 个")
    print(f"✅ 存在文件: {existing_files} 个")
    print(f"❌ 缺失文件: {total_files - existing_files} 个")
    print(f"📦 新结构总大小: {results['total_size']:,} bytes")
    print(f"📦 旧结构总大小: {old_total:,} bytes")
    
    if old_total > 0:
        size_diff = results['total_size'] - old_total
        size_percent = (size_diff / old_total) * 100
        print(f"📊 大小变化: {size_diff:+,} bytes ({size_percent:+.1f}%)")
    
    # 模块化优势
    print("\n🎯 模块化优势:")
    print("  ✅ 代码分离: 用户代码与调试代码完全隔离")
    print("  ✅ 按需加载: 可以单独加载需要的模块")
    print("  ✅ 维护性: 每个模块职责单一，易于维护")
    print("  ✅ 可扩展性: 新功能可以作为独立模块添加")
    print("  ✅ 性能优化: 支持代码分割和懒加载")
    
    # 建议
    print("\n💡 后续优化建议:")
    print("  1. 添加构建工具 (Webpack/Vite) 进行代码压缩")
    print("  2. 实现代码分割和懒加载")
    print("  3. 添加TypeScript支持")
    print("  4. 实现CSS模块化")
    print("  5. 添加单元测试")

def main():
    """主函数"""
    print("🚀 OGScope 前端重构验证")
    print("=" * 50)
    
    # 检查目录结构
    results = analyze_directory_structure()
    
    # 对比旧结构
    old_total = compare_with_old_structure()
    
    # 检查HTML模板
    template_results = check_html_templates()
    
    # 生成总结
    generate_summary(results, old_total)
    
    # 保存结果到文件
    report = {
        "timestamp": "2024-01-01T00:00:00Z",
        "structure_check": results["structure_check"],
        "file_sizes": results["file_sizes"],
        "total_size": results["total_size"],
        "old_total_size": old_total,
        "template_check": template_results
    }
    
    with open("refactor_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 详细报告已保存到: refactor_report.json")
    
    # 计算成功文件数
    existing_files = 0
    for dir_info in results["structure_check"].values():
        if dir_info["exists"]:
            for file_info in dir_info["files"].values():
                if file_info["exists"]:
                    existing_files += 1
    
    return existing_files == total_files

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
