"""共享解算工作池的并发与取消边界 / Shared solver concurrency and cancellation boundaries."""

import asyncio
import contextvars
import threading

import numpy as np
import pytest

from ogscope.algorithms.plate_solve.worker import (
    get_solver_executor,
    run_solver_job,
)


@pytest.mark.asyncio
async def test_cancelled_waiter_cannot_overlap_native_work_with_the_next_solve():
    """取消等待时原生线程仍执行，后续工作必须等待 / A cancelled wait cannot overlap native jobs."""
    entered = threading.Event()
    release = threading.Event()
    second_entered = threading.Event()
    worker_ids = []

    def blocked():
        worker_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(timeout=3)

    def next_job():
        worker_ids.append(threading.get_ident())
        second_entered.set()
        return 42

    first = asyncio.create_task(run_solver_job(blocked))
    try:
        while not entered.is_set():
            await asyncio.sleep(0.001)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(run_solver_job(next_job))
        await asyncio.sleep(0.02)
        assert not second_entered.is_set()
        release.set()
        assert await asyncio.wait_for(second, timeout=1) == 42
        assert worker_ids[0] == worker_ids[1]
    finally:
        release.set()


@pytest.mark.asyncio
async def test_worker_preserves_context_keyword_arguments_and_errors():
    """保留原 to_thread 的调用语义 / Preserve context, kwargs and exception behavior."""
    context = contextvars.ContextVar("solver_worker_test", default="empty")
    token = context.set("request")
    try:
        result = await run_solver_job(lambda *, value: (context.get(), value), value=7)
        assert result == ("request", 7)
        with pytest.raises(ValueError, match="solve failed"):
            await run_solver_job(
                lambda: (_ for _ in ()).throw(ValueError("solve failed"))
            )
    finally:
        context.reset(token)


def test_diagnostic_and_realtime_entry_points_share_one_executor():
    """诊断与实时入口共用工作池 / Diagnostic and realtime entry points share the worker."""
    from ogscope.web.api.analysis.services import AnalysisService

    assert AnalysisService()._solver_executor is get_solver_executor()


@pytest.mark.asyncio
async def test_preview_and_analysis_capture_reuse_one_worker(monkeypatch):
    """预览与分析读帧复用线程并保留读锁 / Preview and analysis reads reuse a thread and the read lock."""
    from ogscope.web.camera_shared import CameraManager

    entered = threading.Event()
    release = threading.Event()
    worker_ids = []

    class Camera:
        is_initialized = True
        is_capturing = True

        def get_video_frame(self):
            worker_ids.append(threading.get_ident())
            if len(worker_ids) == 1:
                entered.set()
                assert release.wait(timeout=3)
            return np.zeros((32, 32, 3), dtype=np.uint8)

    manager = CameraManager()
    manager._camera = Camera()
    manager._keep_raw_cache = False
    manager._idle_shutdown_sec = 0

    async def already_started(*args, **kwargs):
        return None

    monkeypatch.setattr(manager, "ensure_started", already_started)
    preview = asyncio.create_task(manager._grabber_loop())
    try:
        while not entered.is_set():
            await asyncio.sleep(0.001)
        analysis = asyncio.create_task(manager.get_raw_frame())
        await asyncio.sleep(0.02)
        release.set()
        frame, _, _ = await asyncio.wait_for(analysis, timeout=1)
        assert frame.shape == (32, 32, 3)
        assert await asyncio.to_thread(manager._probe_stream_health_sync, 0.1)
        assert len(worker_ids) >= 2
        assert len(set(worker_ids)) == 1
    finally:
        release.set()
        preview.cancel()
        with pytest.raises(asyncio.CancelledError):
            await preview
        manager._capture_executor.shutdown(wait=True)
        manager._jpeg_executor.shutdown(wait=True)
