#!/usr/bin/env python3
"""
启动新的现代化UI演示
在浏览器中打开新的DJI风格界面进行预览
"""

import os
import sys
import time
import webbrowser
import subprocess
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent

def start_demo_server():
    """启动演示服务器"""
    print("🚀 启动OGScope现代化UI演示...")
    print("=" * 50)

    # 检查HTML文件是否存在
    html_file = project_root / "web" / "templates" / "index.html"
    if not html_file.exists():
        print("❌ 错误：找不到HTML文件")
        return False

    # 启动HTTP服务器
    try:
        print("📡 启动本地服务器...")
        server_process = subprocess.Popen([
            sys.executable, "-m", "http.server", "8000"
        ], cwd=project_root)

        # 等待服务器启动
        time.sleep(2)

        # 构建URL
        demo_url = "http://localhost:8000/web/templates/index.html"

        print("✅ 服务器启动成功！"        print(f"🌐 演示地址: {demo_url}")
        print()
        print("📱 演示功能:")
        print("  • 16:9视频区域，红色边框标记")
        print("  • 十字+圆+三角准星组件")
        print("  • 左上角：GPS、海拔、亮度信息")
        print("  • 右上角：信号、电量、WIFI状态")
        print("  • 左下角：极轴校准偏移")
        print("  • 右下角：图像质量指示")
        print("  • 右上：功能菜单按钮")
        print("  • 右侧：缩放控制滑块")
        print("  • 右下：模式切换按钮")
        print("  • 左上：高级模式切换")
        print("  • 横屏强制显示")
        print()
        print("💡 使用提示:")
        print("  • 在手机浏览器中打开以获得最佳体验")
        print("  • 旋转设备到横屏方向")
        print("  • 所有数据都是模拟的实时更新")
        print()

        # 自动打开浏览器
        print("🔍 正在打开浏览器...")
        webbrowser.open(demo_url)

        print("🎯 演示已启动！")
        print("   按Ctrl+C停止服务器")

        # 保持服务器运行
        try:
            server_process.wait()
        except KeyboardInterrupt:
            print("\n🛑 停止服务器...")
            server_process.terminate()
            server_process.wait()

        return True

    except Exception as e:
        print(f"❌ 启动服务器失败: {e}")
        return False

def check_requirements():
    """检查系统要求"""
    print("🔍 检查系统要求...")

    requirements = [
        ("Python 3.6+", sys.version_info >= (3, 6)),
        ("HTML文件存在", (project_root / "web" / "templates" / "index.html").exists()),
        ("模板目录可访问", (project_root / "web" / "templates").is_dir()),
    ]

    all_ok = True
    for req_name, req_check in requirements:
        status = "✅" if req_check else "❌"
        print(f"   {status} {req_name}")
        if not req_check:
            all_ok = False

    return all_ok

def main():
    """主函数"""
    print("🎨 OGScope 现代化DJI风格UI演示启动器")
    print("=" * 50)

    # 检查要求
    if not check_requirements():
        print("❌ 系统要求不满足，无法启动演示")
        return False

    # 启动演示
    success = start_demo_server()

    if success:
        print("\n🎉 演示启动成功！")
        print("   现在可以在浏览器中查看新的UI设计了")
        return True
    else:
        print("\n❌ 演示启动失败")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
