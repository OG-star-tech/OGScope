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


@pytest.fixture
def temp_catalog_dir(tmp_path: Path):
    """重定向星表目录到临时路径 / Redirect catalog directory to temp path."""
    from ogscope.data.catalog.service import catalog_service

    catalog_root = tmp_path / "catalog"
    catalog_service.reconfigure_storage(catalog_root)
    return catalog_root


@pytest.fixture
def temp_analysis_dir(tmp_path: Path):
    """重定向分析目录到临时路径 / Redirect analysis directory to temp path."""
    from ogscope.web.api.analysis.services import analysis_service

    analysis_root = tmp_path / "analysis"
    upload_root = analysis_root / "uploads"
    jobs_root = analysis_root / "jobs"
    results_root = analysis_root / "results"
    upload_root.mkdir(parents=True, exist_ok=True)
    jobs_root.mkdir(parents=True, exist_ok=True)
    results_root.mkdir(parents=True, exist_ok=True)

    analysis_service.upload_root = upload_root
    analysis_service.jobs_root = jobs_root
    analysis_service.results_root = results_root
    analysis_service._jobs = {}
    return analysis_root

