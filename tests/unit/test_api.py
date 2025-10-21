"""
Web API 单元测试
"""
import pytest


@pytest.mark.unit
def test_root(client):
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "OGScope"
    assert "version" in data


@pytest.mark.unit
def test_health_check(client):
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.unit
def test_camera_status(client):
    """测试获取相机状态"""
    response = client.get("/api/camera/status")
    assert response.status_code == 200
    data = response.json()
    assert "connected" in data
    assert "streaming" in data

