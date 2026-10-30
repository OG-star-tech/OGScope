"""Cross-caller analysis isolation / 跨调用者分析隔离。"""

import asyncio
from types import SimpleNamespace

import pytest

from ogscope.core.realtime import service as module
from ogscope.core.realtime.service import RealtimeSolveService


@pytest.fixture
def service(monkeypatch):
    manager = SimpleNamespace(get_camera_instance=lambda: None)
    monkeypatch.setattr(module, "get_camera_manager", lambda: manager)
    service = RealtimeSolveService()

    async def wait(*_args):
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_loop", wait)
    return service


@pytest.mark.asyncio
async def test_other_callers_cannot_join_change_or_stop_owned_analysis(service):
    first = await service.start(owner_token="alignment", solve_timeout_ms=8000)
    for owner in [None, "guard", "developer"]:
        rejected = await service.start(owner_token=owner, solve_timeout_ms=15000)
        assert rejected["success"] is False
        assert rejected["error_code"] == "ANALYSIS_BUSY"
        assert rejected["session_id"] == first["session_id"]
        stopped = await service.stop(session_id=first["session_id"], owner_token=owner)
        assert stopped["success"] is False
        assert service.state.running
    assert service._solve_timeout_ms == 8000
    assert (
        await service.stop(session_id=first["session_id"], owner_token="alignment")
    )["success"]


@pytest.mark.asyncio
async def test_late_cleanup_does_not_stop_a_new_session(service):
    first = await service.start(owner_token="a")
    await service.stop(session_id=first["session_id"], owner_token="a")
    second = await service.start(owner_token="b")
    assert second["session_id"] != first["session_id"]
    result = await service.stop(session_id=first["session_id"], owner_token="a")
    assert not result["success"] and service.state.running
    assert service.state.session_id == second["session_id"]
    await service.stop(force=True)


@pytest.mark.asyncio
async def test_two_simultaneous_starts_have_exactly_one_owner(service):
    results = await asyncio.gather(
        service.start(owner_token="a"), service.start(owner_token="b")
    )
    assert sum(result["success"] for result in results) == 1
    await service.stop(force=True)


@pytest.mark.asyncio
async def test_new_session_waits_for_old_camera_cleanup(service, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_cleanup(*_args):
        try:
            await asyncio.Event().wait()
        finally:
            entered.set()
            await release.wait()

    monkeypatch.setattr(service, "_loop", delayed_cleanup)
    first = await service.start(owner_token="a")
    await asyncio.sleep(0)
    stopping = asyncio.create_task(
        service.stop(session_id=first["session_id"], owner_token="a")
    )
    await entered.wait()
    starting = asyncio.create_task(service.start(owner_token="b"))
    await asyncio.sleep(0)
    assert not starting.done()
    release.set()
    await stopping
    assert (await starting)["success"]
    await service.stop(force=True)


@pytest.mark.asyncio
async def test_failed_session_cleanup_cannot_write_into_its_successor(
    service, monkeypatch
):
    cleaned = []

    async def failed(*_args):
        service.state.running = False
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.append(service.state.session_id)

    monkeypatch.setattr(service, "_loop", failed)
    first = await service.start(owner_token="a")
    await asyncio.sleep(0)
    second = await service.start(owner_token="b")
    assert cleaned == [first["session_id"]]
    assert second["session_id"] != first["session_id"]
    await service.stop(force=True)


@pytest.mark.asyncio
async def test_disconnected_owner_expires_even_if_other_clients_poll(service):
    service._ownership_timeout_s = 0.025
    await service.start(owner_token="a")
    for _ in range(6):
        await asyncio.sleep(0.01)
        await service.get_status(owner_token="another-reader")
    assert not service.state.running


@pytest.mark.asyncio
async def test_only_matching_owner_can_renew_its_analysis(service):
    service._ownership_timeout_s = 0.04
    first = await service.start(owner_token="a")
    for _ in range(6):
        await asyncio.sleep(0.01)
        assert (await service.get_status(owner_token="a"))["running"]
    await service.stop(session_id=first["session_id"], owner_token="a")


def test_core_and_developer_routes_share_one_owner(client, service, monkeypatch):
    from ogscope.core.application import core_service
    from ogscope.web.api.debug import routes as debug_routes

    monkeypatch.setattr(core_service, "realtime_solve_service", service)
    monkeypatch.setattr(debug_routes, "realtime_solve_service", service)
    first = client.post(
        "/api/core/v1/analysis/start",
        json={"owner_token": "alignment", "solve_timeout_ms": 8000},
    ).json()
    assert first["success"] and first["ownership_supported"]
    rejected = client.post("/api/dev/debug/analysis/realtime/start").json()
    assert not rejected["success"] and rejected["error_code"] == "ANALYSIS_BUSY"
    assert not client.post("/api/core/v1/analysis/stop", json={}).json()["success"]
    assert not client.post("/api/dev/debug/analysis/realtime/stop").json()["success"]
    assert (
        client.get(
            "/api/core/v1/analysis/result", params={"owner_token": "alignment"}
        ).json()["session_id"]
        == first["session_id"]
    )
    assert client.post(
        "/api/core/v1/analysis/stop",
        json={"session_id": first["session_id"], "owner_token": "alignment"},
    ).json()["success"]


@pytest.mark.asyncio
async def test_start_exception_does_not_leave_a_phantom_busy_session(
    service, monkeypatch
):
    original = service._start_locked

    async def fail(**_kwargs):
        service.state.running = True
        raise RuntimeError("capture startup failed")

    monkeypatch.setattr(service, "_start_locked", fail)
    with pytest.raises(RuntimeError, match="startup failed"):
        await service.start(owner_token="a")
    assert not service.state.running and service._owner_token is None
    monkeypatch.setattr(service, "_start_locked", original)
    assert (await service.start(owner_token="b"))["success"]
    await service.stop(force=True)


def test_stopped_watchdog_from_closed_loop_does_not_break_stop(service):
    """已结束的监护任务无需跨循环等待 / A finished watchdog needs no cross-loop join."""

    async def create_finished_watchdog():
        task = asyncio.create_task(asyncio.sleep(60))
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        service._ownership_watchdog = task

    asyncio.run(create_finished_watchdog())
    assert asyncio.run(service.stop(force=True))["success"]
    assert service._ownership_watchdog is None
