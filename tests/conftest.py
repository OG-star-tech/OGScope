"""
Pytest 配置和共享 fixtures
"""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from ogscope.web.app import app


@pytest.fixture
def client():
    """FastAPI 测试客户端 / FastAPI test client"""
    return TestClient(app)


@pytest.fixture
def temp_debug_dir(monkeypatch, tmp_path: Path):
    """将调试目录重定向到临时目录，避免污染用户目录。 / Redirect the debug directory to a temporary directory to avoid polluting the user directory."""
    from ogscope.web.api.debug import services as debug_services

    debug_root = tmp_path / "dev_captures"
    debug_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(debug_services, "DEBUG_CAPTURES_DIR", debug_root)
    monkeypatch.setattr(debug_services, "camera_instance", None)
    monkeypatch.setattr(debug_services, "is_recording", False)
    monkeypatch.setattr(debug_services, "recording_task", None)
    monkeypatch.setattr(debug_services, "latest_preview_jpeg", None)
    monkeypatch.setattr(debug_services, "last_preview_time", None)
    monkeypatch.setattr(debug_services, "latest_preview_id", 0)
    monkeypatch.setattr(debug_services, "preview_grabber_task", None)

    return debug_root

