"""固定 Core v1 的公开形状，不锁定文案 / Freeze public Core v1 shape, not prose."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


def contract_shape(schema):
    """保留类型、默认值、约束及 HTTP 行为 / Retain types, defaults, constraints and HTTP behavior."""
    prose = {
        "title",
        "description",
        "summary",
        "operationId",
        "tags",
        "examples",
        "example",
    }

    def normalize(value, *, preserve_keys=False):
        if isinstance(value, dict):
            return {
                key: normalize(item, preserve_keys=key in {"properties", "schemas"})
                for key, item in value.items()
                if preserve_keys or key not in prose
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return normalize({"paths": schema["paths"], "components": schema["components"]})


def test_core_v1_matches_reviewed_contract_baseline(client):
    """内部重构不能悄悄改变 Core v1 / Internal refactors must not silently change Core v1."""
    baseline = Path(__file__).parents[1] / "fixtures" / "core-v1-contract.json"
    assert contract_shape(client.get("/openapi-core.json").json()) == json.loads(
        baseline.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("include_optional_routes", [True, False])
def test_core_v1_is_identical_with_standalone_or_subordinate_routes(
    include_optional_routes,
):
    """角色裁剪不能影响 Core 契约 / Role-specific route pruning must preserve Core."""
    from fastapi import FastAPI

    from ogscope.web.api.main import create_api_router
    from ogscope.web.app import _prune_openapi_components

    app = FastAPI()
    app.include_router(
        create_api_router(
            include_network=include_optional_routes,
            include_dev_debug=include_optional_routes,
        ),
        prefix="/api",
    )
    schema = app.openapi()
    schema["paths"] = {
        key: value
        for key, value in schema["paths"].items()
        if key.startswith("/api/core/v1/")
    }
    _prune_openapi_components(schema, schema["paths"])
    baseline = Path(__file__).parents[1] / "fixtures" / "core-v1-contract.json"
    assert contract_shape(schema) == json.loads(baseline.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "path,method,payload",
    [
        ("analysis/start", "start_analysis", None),
        ("analysis/start", "start_analysis", {"owner_token": ""}),
        ("analysis/stop", "stop_analysis", {"session_id": ""}),
        ("camera/lease", "camera_operation_lease", {"ttl_seconds": 9}),
        ("camera/lease", "camera_operation_lease", {"unknown_option": True}),
        ("camera/tune", "tune_camera", {"rotation": 45}),
    ],
)
def test_invalid_core_requests_fail_before_dispatch(
    client, monkeypatch, path, method, payload
):
    """无效请求不得进入设备调用 / Invalid requests must not reach device operations."""
    from ogscope.web.api.core.routes import core_contract_service

    operation = AsyncMock(side_effect=AssertionError("Unexpected device dispatch"))
    monkeypatch.setattr(core_contract_service, method, operation)
    response = client.post("/api/core/v1/" + path, json=payload)
    assert response.status_code == 422
    operation.assert_not_called()


@pytest.mark.parametrize("error,status", [(LookupError, 404), (ValueError, 409)])
def test_exact_frame_errors_keep_http_status(client, monkeypatch, error, status):
    """缺帧与身份冲突必须区分 / Missing frames and identity conflicts remain distinct."""
    from ogscope.web.api.core.routes import core_contract_service

    def unavailable(**kwargs):
        raise error("Frame unavailable")

    monkeypatch.setattr(
        core_contract_service, "get_analysis_frame_snapshot", unavailable
    )
    response = client.get("/api/core/v1/analysis/frame?session_id=old&frame_id=1")
    assert response.status_code == status
