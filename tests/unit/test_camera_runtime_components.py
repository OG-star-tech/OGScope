"""组件所有权与中性边界的行为保护 / Behavioral protection for component ownership and neutral boundaries."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ogscope.application.camera_resources import CameraResources
from ogscope.domain.camera.media import CameraMediaCatalog
from ogscope.domain.camera.ownership import CameraOwnership
from ogscope.domain.camera.services import FileDomainService


@pytest.mark.asyncio
async def test_lease_limits_and_expiry_do_not_release_another_consumer(monkeypatch):
    """过期操作不能释放分析占用或复活旧租约 / Expired operations cannot release analysis or revive old leases."""
    from ogscope.domain.camera import ownership as module

    clock = [100.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    resources = CameraResources()
    inactive = Mock()
    owner = CameraOwnership(
        spawn=resources.spawn,
        check_accepting_work=lambda: None,
        on_active=lambda: None,
        on_inactive=inactive,
    )
    try:
        owner.acquire("analysis")
        leases = [owner.update_lease(ttl_seconds=10)["lease_id"] for _ in range(8)]
        assert owner.update_lease()["error"] == "camera_lease_limit"
        assert owner.snapshot()["operation_consumers"] == 8
        clock[0] = 111.0
        for lease in leases:
            assert owner.update_lease(lease_id=lease)["error"] == "camera_lease_expired"
        assert owner.blocks_stop
        assert owner.snapshot()["analysis_consumers"] == 1
        owner.release("analysis")
        assert not owner.active
        assert owner.update_lease(lease_id=leases[0], release=True)["released"]
    finally:
        owner.begin_shutdown()
        await asyncio.gather(*resources.background_tasks, return_exceptions=True)
        resources.close_executors()


@pytest.mark.asyncio
async def test_core_and_dev_read_same_media_without_debug_domain_adapter(
    monkeypatch, tmp_path
):
    """读取同一目录与侧车，保留排序、字段和路径拒绝 / Preserve catalog order, sidecars and basename rejection across callers."""
    from ogscope.web.api.debug import services

    (tmp_path / "video.avi").write_bytes(b"owned-test-video")
    (tmp_path / "video.txt").write_text(
        json.dumps({"camera": {"fps": 8, "width": 640, "height": 360}})
    )
    (tmp_path / "image.jpg").write_bytes(b"owned-test-image")
    (tmp_path / "ignored.tmp").write_text("ignored")
    monkeypatch.setattr(services, "DEBUG_CAPTURES_DIR", tmp_path)
    domain = FileDomainService(CameraMediaCatalog(tmp_path))
    assert await domain.list_files() == await services.DebugFileService.get_files()
    names = {item["name"] for item in (await domain.list_files())["files"]}
    assert names == {"image.jpg", "video.avi"}
    info = await domain.get_file_info("video.avi")
    assert info == await services.DebugFileService.get_file_info("video.avi")
    assert info["fps"] == 8 and info["resolution"] == "640x360"
    for call in (domain.get_file_info, services.DebugFileService.get_file_info):
        with pytest.raises(ValueError, match="invalid filename"):
            await call("../video.avi")


def test_moved_streaming_implementation_has_one_owner():
    """路由引用唯一 HTTP 流实现，Domain 不保留反向转发 / Routes use one HTTP stream owner without a reverse Domain forwarder."""
    from ogscope.web import camera_streaming
    from ogscope.web.api.core import routes as core
    from ogscope.web.api.debug import routes as dev

    assert core.build_camera_mjpeg_stream is camera_streaming.build_camera_mjpeg_stream
    assert dev.build_camera_mjpeg_stream is camera_streaming.build_camera_mjpeg_stream
    root = Path(__file__).parents[2]
    assert not (root / "ogscope/platform/adapters/debug_services.py").exists()
