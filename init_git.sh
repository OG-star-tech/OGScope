#!/bin/bash
# OGScope Git 仓库初始化脚本

set -e

echo "======================================"
echo "  OGScope Git 仓库初始化"
echo "======================================"

# 确认当前目录
echo "当前目录: $(pwd)"
read -p "确认在正确的项目目录中吗？(y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 1
fi

# 初始化 Git 仓库
if [ -d ".git" ]; then
    echo "⚠️  Git 仓库已存在"
    read -p "是否重新初始化？这将删除现有 Git 历史！(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf .git
        git init
        echo "✅ 已重新初始化 Git 仓库"
    else
        echo "保持现有 Git 仓库"
    fi
else
    git init
    echo "✅ Git 仓库已初始化"
fi

# 添加所有文件
echo "📦 添加文件到暂存区..."
git add .

# 首次提交
echo "💾 创建初始提交..."
git commit -m "Initial commit: OGScope project structure

- Setup Poetry project with pyproject.toml
- Add FastAPI web service framework
- Create basic project structure
- Add PyCharm remote development guide
- Setup GitHub Actions CI/CD
- Add comprehensive documentation
- Include installation scripts for Orange Pi

Project Features:
- Electronic Polar Scope for astrophotography
- Orange Pi Zero 2W + IMX327 camera
- Web control interface
- SPI LCD display support (planned)
- INDI integration (planned)
"

echo ""
echo "======================================"
echo "  ✅ Git 仓库初始化完成！"
echo "======================================"
echo ""
echo "下一步："
echo ""
echo "1. 在 GitHub 上创建新仓库："
echo "   https://github.com/new"
echo "   仓库名: OGScope"
echo "   ⚠️  不要初始化 README、.gitignore 或 LICENSE"
echo ""
echo "2. 添加远程仓库并推送："
echo "   git remote add origin https://github.com/your-username/OGScope.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "3. 或使用 SSH："
echo "   git remote add origin git@github.com:your-username/OGScope.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""

