"""
Web API 单元测试
"""
import pytest


@pytest.mark.unit
def test_root(client):
    """测试根路径返回 HTML 页面。 / Testing the root path returns an HTML page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "OGScope" in response.text


@pytest.mark.unit
def test_health_check(client):
    """测试健康检查接口。 / Test the health check interface."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.unit
def test_app_api_root(client):
    """测试应用级 / Test application level"""
    response = client.get("/api")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["docs"] == "/docs"



@pytest.mark.unit
def test_camera_status(client):
    """测试获取相机状态接口结构。 / Test to obtain the camera status interface structure."""
    response = client.get("/api/camera/status")
    assert response.status_code == 200
    data = response.json()
    assert "connected" in data
    assert "streaming" in data
    assert "mode" in data


@pytest.mark.unit
def test_system_info(client):
    """测试系统信息接口结构。 / Test system info endpoint schema."""
    response = client.get("/api/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "platform" in data
    assert "os" in data
    assert "cpu_usage" in data
    assert "memory_usage" in data
    assert "temperature" in data
    assert "wifi_quality" in data
    assert "wifi_signal_dbm" in data
    assert "wifi_interface" in data
    assert "uptime_seconds" in data
    assert "load_average_1m" in data

