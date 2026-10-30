"""冒烟工具失败、占用与清理回归 / Smoke failure, ownership and cleanup regressions."""

import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "core-api-smoke.py"
_SPEC = importlib.util.spec_from_file_location("core_api_smoke", _PATH)
smoke = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(smoke)


class Device:
    """模拟 HTTP 对端，不打开硬件 / Fake HTTP peer without opening hardware."""

    base_url = "http://127.0.0.1:8000"

    def __init__(self):
        self.calls = []
        self.streaming = False
        self.running = False
        self.busy = False
        self.backend = "v4l2"
        self.solver_status = "TOO_FEW"
        self.failure = None
        self.owner = None
        self.lose_start_response = False
        self.quarantined_stop = False
        self.busy_on_start = False

    def json(self, method, path, payload=None):
        path = urlsplit(path).path
        self.calls.append((method, path, payload))
        if self.failure == (method, path):
            raise smoke.SmokeFailure("注入的请求失败 / Injected request failure")
        if path == "/health":
            return {"status": "healthy"}
        if path == "/api":
            return {"role": "standalone"}
        if path.endswith("/system/status"):
            return {"success": True, "version": "0.1.0", "health": "healthy"}
        if path.endswith("/camera/status"):
            counts = dict.fromkeys(smoke.CONSUMERS, 0)
            counts["phase"] = "active" if self.streaming else "sleeping"
            if self.quarantined_stop and any(
                method == "POST" and path.endswith("/camera/stop")
                for method, path, _ in self.calls
            ):
                counts["phase"] = "warm_idle"
            counts["analysis_consumers"] = int(self.running or self.busy)
            return {
                "success": True,
                "streaming": self.streaming,
                "recording": False,
                "configured_backend": self.backend,
                "lifecycle": counts,
            }
        if path.endswith("/camera/lease"):
            return {"success": True, "lease_id": "test-lease"}
        if path.endswith("/camera/start"):
            self.streaming = True
            return {"success": True, "applied": {"ready": True}}
        if path.endswith("/camera/stop"):
            self.streaming = False
            return {"success": True}
        if path.endswith("/analysis/start"):
            if self.busy_on_start:
                self.running = True
                self.owner = "another-owner"
                return {"success": False, "error_code": "ANALYSIS_BUSY"}
            self.owner = payload["owner_token"]
            self.running = True
            if self.lose_start_response:
                raise smoke.SmokeFailure("响应丢失 / Response lost")
            return {
                "success": True,
                "session_id": "test-session",
                "ownership_supported": True,
            }
        if path.endswith("/analysis/stop"):
            assert payload == {"owner_token": self.owner, "session_id": "test-session"}
            self.running = False
            return {"success": True, "state": "stopped"}
        if path.endswith("/analysis/result"):
            return {
                "success": True,
                "ownership_supported": True,
                "state": "running" if self.running else "stopped",
                "session_id": "test-session",
                "fullsolve_count": int(self.running),
                "result": {"status": self.solver_status} if self.running else None,
            }
        raise AssertionError((method, path))

    def preview(self):
        return b"\xff\xd8\xfftest\xff\xd9"


def test_lost_start_reply_never_adopts_an_unowned_successor_session():
    """旧调用方不能借当前会话 ID 停止无 owner 的后继 / Never adopt an ownerless successor."""

    class Successor(Device):
        def json(self, method, path, payload=None):
            if path.endswith("/analysis/start"):
                self.running = True
                self.owner = None
                raise smoke.SmokeFailure("响应丢失 / Reply lost")
            if path.endswith("/analysis/stop"):
                self.calls.append((method, path, payload))
                self.running = False
                return {"success": True, "state": "stopped"}
            return super().json(method, path, payload)

    device = Successor()
    report = run(device)
    assert not report["success"]
    assert device.running
    assert not any(
        path.endswith(("/analysis/stop", "/camera/stop")) for _, path, _ in device.calls
    )


def test_failed_analysis_cleanup_does_not_fall_through_to_camera_stop():
    device = Device()
    device.solver_status = "DATABASE_ERROR"
    device.failure = ("POST", smoke.CORE + "/analysis/stop")
    report = run(device)
    assert report["code"] == 4
    assert not any(path.endswith("/camera/stop") for _, path, _ in device.calls)


def test_cleanup_verifies_release_instead_of_trusting_stop_success():
    device = Device()
    device.solver_status = "DATABASE_ERROR"
    device.quarantined_stop = True
    report = run(device)
    cleanup = [check for check in report["checks"] if check["name"] == "camera_cleanup"]
    assert cleanup and cleanup[0]["status"] == "failed"


def run(device, **overrides):
    options = {
        "dry_run": False,
        "service_commit": "a" * 40,
        "profile": "compatibility",
        "expected_backend": "v4l2",
        "cycles": 2,
        "wait": 5,
    }
    return smoke.run_smoke(device, **{**options, **overrides})


def test_complete_smoke_stops_its_sessions_without_claiming_release_acceptance():
    device = Device()
    report = run(device)
    assert report["success"] and report["code"] == 0
    assert report["release_allowed"] is False
    assert report["release_decision"] == "manual_acceptance_required"
    assert report["deployment"]["provenance"] == "operator_supplied_not_verified_by_api"
    assert (
        len([call for call in device.calls if call[1].endswith("/analysis/stop")]) == 2
    )
    assert not device.running and not device.streaming
    assert device.owner not in str(report)


@pytest.mark.parametrize("change", ["busy", "backend"])
def test_busy_device_or_wrong_backend_never_receives_a_write(change):
    device = Device()
    setattr(device, change, True if change == "busy" else "virtual")
    report = run(device)
    assert report["code"] == 4
    assert all(method == "GET" for method, *_ in device.calls)


def test_dry_run_only_uses_get_and_returns_incomplete():
    device = Device()
    report = run(device, dry_run=True)
    assert report["code"] == 5 and not report["success"]
    assert all(method == "GET" for method, *_ in device.calls)


@pytest.mark.parametrize("failure", ["DATABASE_ERROR", "EXTRACTION_ERROR", None])
def test_solver_failure_cleans_up_owned_analysis_and_lease(failure):
    device = Device()
    device.solver_status = failure
    report = run(device)
    assert not report["success"] and report["code"] == 4
    assert not device.running and not device.streaming
    assert any(payload and payload.get("release") for _, _, payload in device.calls)


def test_lost_start_response_reports_unknown_session_without_guessing_cleanup():
    device = Device()
    device.lose_start_response = True
    report = run(device)
    assert not report["success"]
    assert device.running
    assert not any(
        path.endswith(("/analysis/stop", "/camera/stop")) for _, path, _ in device.calls
    )
    assert any(
        check["name"] == "analysis_cleanup" and check["status"] == "failed"
        for check in report["checks"]
    )


def test_another_owner_arriving_after_preflight_is_not_stopped():
    device = Device()
    device.busy_on_start = True
    report = run(device)
    assert report["code"] == 4
    assert device.running and device.owner == "another-owner"
    assert not any(
        path.endswith(("/analysis/stop", "/camera/stop")) for _, path, _ in device.calls
    )
    assert any(payload and payload.get("release") for _, _, payload in device.calls)


def test_failed_camera_stop_is_not_automatically_retried():
    device = Device()
    device.failure = ("POST", smoke.CORE + "/camera/stop")
    report = run(device)
    assert report["code"] == 4
    assert len([call for call in device.calls if call[:2] == device.failure]) == 1


def test_non_streaming_quarantined_handle_does_not_count_as_a_successful_stop():
    device = Device()
    device.quarantined_stop = True
    report = run(device)
    assert report["code"] == 4
    assert not report["success"]
    assert len([call for call in device.calls if call[1].endswith("/camera/stop")]) == 1


def test_missing_exclusive_confirmation_cannot_contact_device():
    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--expected-backend",
                "v4l2",
                "--service-commit",
                "a" * 40,
                "--profile",
                "compatibility",
            ]
        )
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/test",
        "http://user:secret@localhost",
        "http://localhost/?token=secret",
    ],
)
def test_client_rejects_non_origin_targets(url):
    with pytest.raises(smoke.SmokeFailure):
        smoke.CoreClient(url, 1)


def test_transport_reads_one_complete_jpeg_and_closes_stream():
    response = io.BytesIO(
        b"--frame\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8\xffdata\xff\xd9\r\n"
    )
    response.headers = {"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
    client = smoke.CoreClient(Device.base_url, 1)
    client.opener = SimpleNamespace(open=lambda *a, **kw: response)
    assert client.preview() == b"\xff\xd8\xffdata\xff\xd9"
    assert response.closed


def test_transport_rejects_truncated_jpeg():
    response = io.BytesIO(b"--frame\r\n\xff\xd8\xfftruncated")
    response.headers = {"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
    client = smoke.CoreClient(Device.base_url, 1)
    client.opener = SimpleNamespace(open=lambda *a, **kw: response)
    with pytest.raises(smoke.SmokeFailure, match="JPEG"):
        client.preview()
    assert response.closed


def test_old_service_without_ownership_support_receives_no_writes():
    class OldService(Device):
        def json(self, method, path, payload=None):
            result = super().json(method, path, payload)
            result.pop("ownership_supported", None)
            return result

    device = OldService()
    assert run(device)["code"] == 4
    assert all(method == "GET" for method, *_ in device.calls)


def test_uncertain_camera_start_does_not_trigger_an_inverse_stop():
    device = Device()
    device.failure = ("POST", smoke.CORE + "/camera/start")
    report = run(device)
    assert report["code"] == 4
    assert not any(path.endswith("/camera/stop") for _, path, _ in device.calls)
    assert any(
        check["name"] == "camera_cleanup" and check["status"] == "skipped"
        for check in report["checks"]
    )


def test_normal_analysis_stop_failure_is_not_retried_in_finally():
    device = Device()
    device.failure = ("POST", smoke.CORE + "/analysis/stop")
    assert run(device)["code"] == 4
    assert len([call for call in device.calls if call[:2] == device.failure]) == 1
    assert not any(path.endswith("/camera/stop") for _, path, _ in device.calls)


def test_preview_arriving_before_cleanup_prevents_camera_stop():
    class ArrivingPreview(Device):
        def json(self, method, path, payload=None):
            result = super().json(method, path, payload)
            if path.endswith("/camera/status") and self.owner:
                result["lifecycle"]["preview_consumers"] = 1
            return result

    device = ArrivingPreview()
    device.solver_status = "DATABASE_ERROR"
    report = run(device)
    assert report["code"] == 4
    assert not any(path.endswith("/camera/stop") for _, path, _ in device.calls)


def test_failed_result_response_does_not_include_owner_token_in_report():
    class FailedResult(Device):
        def json(self, method, path, payload=None):
            result = super().json(method, path, payload)
            if "/analysis/result?" in path:
                return {"success": False}
            return result

    device = FailedResult()
    report = run(device)
    assert report["code"] == 4
    assert device.owner and device.owner not in str(report)


def test_unconfirmed_lease_receipt_is_reported_without_starting_camera():
    device = Device()
    device.failure = ("POST", smoke.CORE + "/camera/lease")
    report = run(device)
    assert report["code"] == 4
    assert not any(path.endswith("/camera/start") for _, path, _ in device.calls)
    assert any(
        check["name"] == "lease_cleanup" and check["status"] == "failed"
        for check in report["checks"]
    )
