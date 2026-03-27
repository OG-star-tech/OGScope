"""
Web API 单元测试
"""
import pytest


@pytest.mark.unit
def test_root(client):
    """测试根路径返回 HTML 页面。"""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "OGScope" in response.text


@pytest.mark.unit
def test_health_check(client):
    """测试健康检查接口。"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.unit
def test_app_api_root(client):
    """测试应用级 /api 根接口。"""
    response = client.get("/api")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["docs"] == "/docs"


@pytest.mark.unit
def test_router_api_root(client):
    """测试路由模块级 /api/api 根接口。"""
    response = client.get("/api/api")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "OGScope API"
    assert "debug" in data["modules"]


@pytest.mark.unit
def test_camera_status(client):
    """测试获取相机状态接口结构。"""
    response = client.get("/api/camera/status")
    assert response.status_code == 200
    data = response.json()
    assert "connected" in data
    assert "streaming" in data
    assert "mode" in data

