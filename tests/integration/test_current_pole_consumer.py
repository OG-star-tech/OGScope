"""配套工作树的真实 Core/适配层验收 / Paired Core and adapter acceptance.

Add the consumer checkout to PYTHONPATH to run; no board or motors are used.
通过 PYTHONPATH 提供消费方检出运行；不使用开发板或电机。
"""

import copy
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

consumer = pytest.importorskip("zenitapa.adapters.rest_ogscope.client")


@pytest.mark.parametrize(
    "refraction", [{"mode": "off"}, {"mode": "standard", "temperature_c": 0.0}]
)
def test_real_core_handshake_publish_and_consumer_validation(
    client, monkeypatch, refraction
):
    from zenitapa.domain.alignment.current_target import require_current_target
    from zenitapa.domain.alignment.observer import ObserverConfig

    from ogscope.algorithms.plate_solve import SolveResult
    from ogscope.core.application import core_service
    from ogscope.core.realtime import service as realtime

    row, context, _ = runpy.run_path(
        str(Path(__file__).parents[1] / "unit/test_current_pole_astrometry.py")
    )["observed_field"](
        offset_deg=0.5,
        refraction=refraction["mode"] != "off",
        elevation_m=2000.0,
        temperature_c=0.0,
    )
    service = realtime.RealtimeSolveService()
    monkeypatch.setattr(core_service, "realtime_solve_service", service)
    monkeypatch.setattr(
        realtime,
        "get_camera_manager",
        lambda: SimpleNamespace(get_camera_instance=lambda: None),
    )

    async def idle(*args):
        return None

    monkeypatch.setattr(service, "_loop", idle)
    adapter = consumer.OGScopeRestClient("http://testserver")

    def transport(method, path, payload=None):
        response = client.request(
            method, path, **({"json": payload} if payload is not None else {})
        )
        response.raise_for_status()
        return response.json()

    monkeypatch.setattr(adapter, "_json", transport)
    started = adapter.start_analysis(
        {
            "solve_context": context,
            "owner_token": "contract-owner",
            "astronomy": {"policy": "current_pole_v1", "refraction": refraction},
        }
    )
    assert started["astronomy"]["policy"] == "current_pole_v1"
    solved = SolveResult(
        ra_deg=row["ra_deg"],
        dec_deg=row["dec_deg"],
        detected_stars=36,
        solve_source="test",
        status="MATCH_FOUND",
        status_code=1,
        matches=36,
        prob=1e-20,
        rmse_arcsec=0.1,
        t_solve_ms=1,
        t_extract_ms=1,
        t_preprocess_ms=1,
        roll_deg=row["roll_deg"],
        fov_deg=row["fov_deg"],
        raw=row["tetra"],
        solve_overlay=row["solve_overlay"],
    )
    service._apply_solve_result(
        solved,
        capture_time={
            "observation_time_utc": row["observation_time_utc"],
            "observation_time_reference": "source_utc",
        },
        frame_id=12,
    )
    result = adapter.get_analysis_result(owner_token="contract-owner")["result"]
    assert (
        require_current_target(
            result, ObserverConfig(latitude_deg=40, longitude_deg=116)
        )["alignment_target_mode"]
        == "ogscope_current_pole"
    )
    assert result["overlay_ext"]["polar_guide"]["angular_sep_deg"] == pytest.approx(
        0.5, abs=1e-5
    )
    if refraction["mode"] == "standard":
        assert result["astronomy"]["refraction"]["temperature_c"] == 0
        assert result["astronomy"]["refraction"]["pressure_hpa"] == pytest.approx(
            799.3, abs=0.1
        )
        changed = client.post(
            "/api/core/v1/analysis/start",
            json={
                "solve_context": context,
                "owner_token": "contract-owner",
                "astronomy": {
                    "policy": "current_pole_v1",
                    "refraction": {"mode": "standard", "temperature_c": 20},
                },
            },
        )
        assert changed.status_code == 409
    original = copy.deepcopy(result)
    assert (
        adapter.get_analysis_result(owner_token="contract-owner")["result"] == original
    )
    service.state.last_result["astronomy"]["target_pole"] = "south"
    with pytest.raises(RuntimeError, match="mismatch"):
        adapter.get_analysis_result(owner_token="contract-owner")
    assert adapter.stop_analysis(
        session_id=started["session_id"], owner_token="contract-owner"
    )["success"]
