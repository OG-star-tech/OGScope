"""
Pytest 配置和共享 fixtures
"""
import pytest
from fastapi.testclient import TestClient

from ogscope.web.app import app


@pytest.fixture
def client():
    """FastAPI 测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_camera():
    """模拟相机"""
    # TODO: 实现模拟相机
    pass


@pytest.fixture
def sample_image():
    """示例图像"""
    # TODO: 提供测试用图像
    pass

