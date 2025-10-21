.PHONY: help install test lint format clean run deploy

help:  ## 显示帮助信息
	@echo "OGScope 开发命令"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## 安装依赖
	poetry install

test:  ## 运行测试
	poetry run pytest -v

test-unit:  ## 运行单元测试
	poetry run pytest -m unit -v

test-cov:  ## 运行测试并生成覆盖率报告
	poetry run pytest --cov=ogscope --cov-report=html --cov-report=term

lint:  ## 代码检查
	poetry run ruff check ogscope tests
	poetry run mypy ogscope

format:  ## 代码格式化
	poetry run black ogscope tests
	poetry run ruff check --fix ogscope tests

clean:  ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache htmlcov dist build
	@echo "清理完成"

run:  ## 运行程序（开发模式）
	poetry run python -m ogscope.main

run-prod:  ## 运行程序（生产模式）
	OGSCOPE_ENVIRONMENT=production poetry run python -m ogscope.main

dev:  ## 开发模式（自动重载）
	poetry run uvicorn ogscope.web.app:app --reload --host 0.0.0.0 --port 8000

shell:  ## 进入 Poetry shell
	poetry shell

update:  ## 更新依赖
	poetry update

lock:  ## 锁定依赖版本
	poetry lock

build:  ## 构建包
	poetry build

deploy:  ## 部署到 Orange Pi（需要配置 SSH）
	@echo "同步代码到 Orange Pi..."
	rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
		--exclude '.venv' --exclude 'PiFinder-release' \
		. orangepi:~/OGScope/
	@echo "重启服务..."
	ssh orangepi "cd ~/OGScope && poetry install && sudo systemctl restart ogscope"
	@echo "部署完成"

logs:  ## 查看日志
	ssh orangepi "journalctl -u ogscope -f"

status:  ## 查看服务状态
	ssh orangepi "sudo systemctl status ogscope"

ssh:  ## SSH 到 Orange Pi
	ssh orangepi

docs:  ## 生成文档（如果使用 Sphinx）
	@echo "文档功能待实现"

pre-commit:  ## 安装 pre-commit hooks
	poetry run pre-commit install

check:  ## 运行所有检查（格式、lint、测试）
	@echo "运行代码格式化..."
	@make format
	@echo "运行代码检查..."
	@make lint
	@echo "运行测试..."
	@make test
	@echo "所有检查完成✅"

