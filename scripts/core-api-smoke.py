#!/usr/bin/env python3
"""经 Core API 检查相机链路，不替代人工验收 / Exercise Core without replacing acceptance."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

CORE = "/api/core/v1"
CONSUMERS = (
    "preview_consumers",
    "analysis_consumers",
    "recording_consumers",
    "operation_consumers",
)
MANUAL_CHECKS = [
    "确认服务实际 commit、后端和生效配置 / Confirm deployed commit, backend and effective config",
    "长曝光停止、预览/分析/录像竞争 / Stop during long exposure and test competing consumers",
    "服务重启与失败后的资源恢复 / Check service restart and recovery after hardware failure",
    "持续运行的 PSS、swap、CMA 和 OOM / Inspect sustained PSS, swap, CMA and OOM",
    "画面方向、色序、FOV 与真实星空精度 / Verify orientation, RGB, FOV and real-sky accuracy",
]


class SmokeFailure(RuntimeError):
    """保留稳定错误，不记录请求令牌 / Keep stable failures without logging request tokens."""


def require(condition, message):
    """条件不满足即失败 / Fail when a required condition is absent."""
    if not condition:
        raise SmokeFailure(message)


class NoRedirect(HTTPRedirectHandler):
    """检查目标不能被重定向替换 / Do not redirect device checks to another target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SmokeFailure("HTTP 重定向被拒绝 / HTTP redirect refused")


class CoreClient:
    """仅使用标准库，所有请求都有预算 / Standard-library client with bounded requests."""

    def __init__(self, base_url, timeout):
        parts = urlsplit(base_url)
        require(
            parts.scheme in {"http", "https"}
            and parts.hostname
            and not parts.username
            and not parts.password
            and parts.path in {"", "/"}
            and not parts.query
            and not parts.fragment,
            "使用不含凭据或路径的 HTTP 地址 / Use an HTTP origin without credentials or paths",
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())

    def _read(self, method, path, payload=None, *, jpeg=False):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        deadline = time.monotonic() + self.timeout
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if jpeg:
                    require(
                        "multipart/x-mixed-replace"
                        in response.headers.get("Content-Type", ""),
                        "预览不是 MJPEG / Preview is not MJPEG",
                    )
                content = bytearray()
                while time.monotonic() < deadline:
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    content.extend(chunk)
                    require(
                        len(content) <= 8 * 1024 * 1024, "响应过大 / Response too large"
                    )
                    if jpeg:
                        start = content.find(b"\xff\xd8\xff")
                        end = content.find(b"\xff\xd9", max(0, start))
                        if start >= 0 and end > start:
                            return bytes(content[start : end + 2])
                if jpeg:
                    raise SmokeFailure("未收到完整 JPEG / No complete JPEG received")
                require(
                    time.monotonic() < deadline, "请求超时 / Request deadline exceeded"
                )
                return bytes(content)
        except HTTPError as exc:
            raise SmokeFailure(f"HTTP {exc.code}") from None
        except (URLError, OSError, TimeoutError) as exc:
            raise SmokeFailure(
                f"网络请求失败 / Request failed: {type(exc).__name__}"
            ) from None

    def json(self, method, path, payload=None):
        try:
            result = json.loads(self._read(method, path, payload))
        except (ValueError, UnicodeError):
            raise SmokeFailure("响应不是有效 JSON / Invalid JSON response") from None
        require(
            isinstance(result, dict), "JSON 响应必须是对象 / Expected a JSON object"
        )
        return result

    def preview(self):
        return self._read("GET", CORE + "/camera/preview/stream?quality=50", jpeg=True)


def run_smoke(
    client, *, dry_run, service_commit, profile, expected_backend, cycles, wait
):
    """只清理本次申请的资源，失败后停止 / Clean up only this run's resources and fail closed."""
    report = {
        "schema_version": 1,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": client.base_url,
        "success": False,
        "code": 4,
        "summary": "检查未完成 / Checks incomplete",
        "deployment": {
            "service_commit": service_commit,
            "profile": profile,
            "expected_backend": expected_backend,
            "provenance": "operator_supplied_not_verified_by_api",
        },
        "checks": [],
        "release_allowed": False,
        "release_decision": "blocked",
        "manual_checks": MANUAL_CHECKS,
    }
    owner = uuid.uuid4().hex
    session = None
    analysis_pending = False
    lease = None
    camera_touched = False
    stop_attempted = False

    def record(name, detail=None):
        report["checks"].append({"name": name, "status": "passed", "detail": detail})

    def call(method, path, payload=None):
        result = client.json(method, CORE + path, payload)
        require(
            result.get("success") is True,
            f"Core 操作失败 / Core operation failed: {path}",
        )
        return result

    def stop_analysis():
        nonlocal analysis_pending, session
        if not session:
            current = call(
                "GET", "/analysis/result?" + urlencode({"owner_token": owner})
            )
            session = current.get("session_id")
        require(bool(session), "无法确认待清理会话 / Cannot identify cleanup session")
        payload = {"owner_token": owner}
        payload["session_id"] = session
        stopped = call("POST", "/analysis/stop", payload)
        require(stopped.get("state") == "stopped", "分析未停止 / Analysis did not stop")
        analysis_pending = False
        session = None

    try:
        health = client.json("GET", "/health")
        require(
            health.get("status") == "healthy", "进程不健康 / Process is not healthy"
        )
        directory = client.json("GET", "/api")
        system = call("GET", "/system/status")
        require(bool(system.get("version")), "缺少服务版本 / Missing service version")
        camera = call("GET", "/camera/status")
        analysis = call("GET", "/analysis/result")
        report["deployment"].update(
            version=system.get("version"),
            role=directory.get("role"),
            configured_backend=camera.get("configured_backend"),
        )
        ownership = camera.get("lifecycle", {})
        require(
            all(ownership.get(key) == 0 for key in CONSUMERS)
            and camera.get("recording") is False
            and analysis.get("state") in {"stopped", "completed"},
            "设备已有消费者或缺少占用遥测 / Device busy or ownership telemetry missing",
        )
        require(
            camera.get("configured_backend") == expected_backend,
            "后端与预期不符 / Backend does not match expectation",
        )
        record(
            "preflight",
            {
                "health": system.get("health"),
                "health_reasons": system.get("health_reasons", []),
            },
        )
        if dry_run:
            report.update(code=5, summary="仅完成 GET 预检 / GET preflight only")
        else:
            for cycle in range(1, cycles + 1):
                stop_attempted = False
                lease = call("POST", "/camera/lease", {"ttl_seconds": 120})["lease_id"]
                camera_touched = True
                started = call("POST", "/camera/start")
                require(
                    started.get("applied", {}).get("ready") is True,
                    "相机启动未确认就绪 / Camera start is not confirmed ready",
                )
                report["deployment"]["observed_camera"] = {
                    key: value
                    for key, value in started.get("info", {}).items()
                    if key
                    in {
                        "driver",
                        "backend",
                        "resolution",
                        "fps",
                        "exposure_us",
                        "actual_exposure_us",
                        "analogue_gain",
                        "actual_analogue_gain",
                    }
                }
                frame = client.preview()
                require(
                    frame.startswith(b"\xff\xd8\xff") and frame.endswith(b"\xff\xd9"),
                    "JPEG 帧无效 / Invalid JPEG frame",
                )
                record(f"cycle_{cycle}_capture", {"jpeg_bytes": len(frame)})
                call("POST", "/camera/lease", {"lease_id": lease, "ttl_seconds": 120})
                analysis_pending = True
                started = client.json(
                    "POST", CORE + "/analysis/start", {"owner_token": owner}
                )
                if started.get("success") is False:
                    analysis_pending = False
                    if started.get("error_code") == "ANALYSIS_BUSY":
                        camera_touched = False
                        report["checks"].append(
                            {
                                "name": "camera_cleanup",
                                "status": "skipped",
                                "detail": "另一个调用方已取得分析，不停止相机 / Another caller owns analysis; leave camera running",
                            }
                        )
                require(
                    started.get("success") is True
                    and started.get("ownership_supported") is True,
                    "分析未取得所有权 / Analysis ownership was not acquired",
                )
                session = started.get("session_id")
                require(bool(session), "缺少分析会话 ID / Missing analysis session ID")
                deadline = time.monotonic() + wait
                while True:
                    call(
                        "POST", "/camera/lease", {"lease_id": lease, "ttl_seconds": 120}
                    )
                    result = call(
                        "GET", "/analysis/result?" + urlencode({"owner_token": owner})
                    )
                    require(
                        result.get("session_id") == session,
                        "分析会话被替换 / Analysis session changed",
                    )
                    require(
                        result.get("phase") != "failed"
                        and not result.get("last_error"),
                        "分析报告错误 / Analysis reported an error",
                    )
                    if result.get("fullsolve_count", 0) > 0 and result.get("result"):
                        status = result["result"].get("status")
                        require(
                            status in {"MATCH_FOUND", "NO_MATCH", "TOO_FEW", "TIMEOUT"},
                            "解算器未返回有效场景结果 / Solver returned no valid scene result",
                        )
                        record(
                            f"cycle_{cycle}_analysis",
                            {
                                "status": status,
                                "fullsolve_count": result["fullsolve_count"],
                            },
                        )
                        break
                    require(
                        time.monotonic() < deadline,
                        "分析等待超时 / Analysis wait expired",
                    )
                    time.sleep(0.5)
                stop_analysis()
                call("POST", "/camera/lease", {"lease_id": lease, "release": True})
                lease = None
                stop_attempted = True
                call("POST", "/camera/stop")
                stopped = call("GET", "/camera/status")
                require(
                    stopped.get("streaming") is False
                    and stopped.get("lifecycle", {}).get("phase") == "sleeping"
                    and all(
                        stopped.get("lifecycle", {}).get(key) == 0 for key in CONSUMERS
                    ),
                    "相机停止或资源释放未确认 / Camera stop or resource release unconfirmed",
                )
                camera_touched = False
                record(f"cycle_{cycle}_stop")
            final = call("GET", "/system/status")
            record(
                "final_health",
                {
                    "health": final.get("health"),
                    "health_reasons": final.get("health_reasons", []),
                },
            )
            report.update(
                success=True,
                code=0,
                summary="自动检查通过，等待人工验收 / Automated checks passed; manual acceptance required",
                release_decision="manual_acceptance_required",
            )
    except (Exception, KeyboardInterrupt) as exc:
        detail = str(exc) if isinstance(exc, SmokeFailure) else type(exc).__name__
        report["checks"].append({"name": "run", "status": "failed", "detail": detail})
    finally:
        cleanup = []
        if analysis_pending:
            cleanup.append(("analysis_cleanup", stop_analysis))
        if lease:
            cleanup.append(
                (
                    "lease_cleanup",
                    lambda: call(
                        "POST", "/camera/lease", {"lease_id": lease, "release": True}
                    ),
                )
            )
        if camera_touched and not stop_attempted:
            cleanup.append(("camera_cleanup", lambda: call("POST", "/camera/stop")))
        for name, action in cleanup:
            try:
                action()
                record(name)
            except Exception:
                report["checks"].append(
                    {
                        "name": name,
                        "status": "failed",
                        "detail": "清理未确认，人工检查服务 / Cleanup unconfirmed; inspect service",
                    }
                )
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def main(argv=None):
    """写操作需显式确认，报告不包含令牌 / Require explicit writes and omit tokens from reports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--expected-backend", required=True, choices=["imx327_mipi", "v4l2"]
    )
    parser.add_argument("--service-commit", required=True)
    parser.add_argument(
        "--profile", required=True, help="部署配置标签 / Deployment profile label"
    )
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--wait", type=float, default=60)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.dry_run and not args.yes:
        parser.error(
            "启停相机与分析需 --yes / Camera and analysis control require --yes"
        )
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.service_commit):
        parser.error("--service-commit 需要完整 SHA / A full commit SHA is required")
    if not (1 <= args.cycles <= 3 and 5 <= args.wait <= 90 and 1 <= args.timeout <= 60):
        parser.error("cycles=1..3, wait=5..90, timeout=1..60")
    try:
        client = CoreClient(args.base_url, args.timeout)
    except SmokeFailure as exc:
        parser.error(str(exc))
    report = run_smoke(
        client,
        dry_run=args.dry_run,
        service_commit=args.service_commit,
        profile=args.profile,
        expected_backend=args.expected_backend,
        cycles=args.cycles,
        wait=args.wait,
    )
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    sys.stdout.write(content if args.json else report["summary"] + "\n")
    return report["code"]


if __name__ == "__main__":
    sys.exit(main())
