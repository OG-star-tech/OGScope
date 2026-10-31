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


@pytest.mark.parametrize("latitude", [40.0, -40.0])
@pytest.mark.parametrize(
    "refraction", [{"mode": "off"}, {"mode": "standard", "temperature_c": 0.0}]
)
def test_real_core_handshake_publish_and_consumer_validation(
    client, monkeypatch, refraction, latitude
):
    from zenitapa.domain.alignment.current_target import require_current_target
    from zenitapa.domain.alignment.observer import ObserverConfig

    from ogscope.algorithms.plate_solve import SolveResult
    from ogscope.core.application import core_service
    from ogscope.core.realtime import service as realtime

    row, context, _ = runpy.run_path(
        str(Path(__file__).parents[1] / "unit/test_current_pole_astrometry.py")
    )["observed_field"](
        latitude=latitude,
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
            result, ObserverConfig(latitude_deg=latitude, longitude_deg=116)
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
    from dataclasses import replace
    from unittest.mock import Mock
    from zenitapa.domain.alignment.calibration import load_alignment_production_settings
    from zenitapa.domain.alignment.session import AlignmentSession
    from zenitapa.domain.alignment.polar_target import PolarTargetError

    movement = Mock()
    downstream = AlignmentSession(
        ogscope=Mock(),
        read_position=Mock(),
        read_movement=Mock(),
        goto_target=movement,
        stop_goto=Mock(),
        prod_settings=replace(
            load_alignment_production_settings(),
            target_mode="ogscope_current_pole",
            refraction_enabled=refraction["mode"] != "off",
        ),
    )
    downstream._correction_observer = ObserverConfig(
        latitude_deg=latitude, longitude_deg=116, elevation_m=2000, source="manual"
    )
    pole = "north" if latitude > 0 else "south"
    downstream._set(target_pole=pole)
    downstream._validate_analysis_target(started)
    downstream._solve_for_alignment({"result": result})
    receipt = downstream.snapshot().target_contract
    assert (
        receipt["expected_pole"]
        == receipt["acknowledged_pole"]
        == receipt["result_pole"]
        == pole
    )
    assert (
        receipt["result_session_id"] == receipt["session_id"] == started["session_id"]
    )
    assert receipt["frame_id"] == 12 and receipt["target_policy"] == "current_pole_v1"
    wrong = copy.deepcopy(result)
    wrong["target_pole"] = "south" if pole == "north" else "north"
    with pytest.raises(PolarTargetError):
        downstream._solve_for_alignment({"result": wrong})
    assert downstream.snapshot().target_pole == pole
    movement.assert_not_called()
    from zenitapa.application.system_debug_service import SystemDebugApplicationService
    from zenitapa.domain.alignment import apply_service, correction
    from zenitapa.domain.alignment.calibration import load_alignment_settings

    debug = SystemDebugApplicationService(Mock(), Mock(), Mock())
    live_context = copy.deepcopy(context)
    live_context["observer"]["source"] = "observer_manual"
    live_context["quality"] = {"location_authorized": True}
    debug._solve_context_provider = lambda: live_context
    debug._debug_analysis = Mock()
    debug._debug_analysis.read.return_value = {"result": result}
    debug.mount_position = lambda: {
        "valid": True,
        "altitude_deg": abs(latitude) + 0.5,
        "azimuth_deg": 0 if latitude > 0 else 180,
    }
    config = replace(load_alignment_settings(), auto_apply_enabled=True)
    monkeypatch.setattr(correction, "load_alignment_settings", lambda: config)
    monkeypatch.setattr(apply_service, "load_alignment_settings", lambda: config)
    dispatch = Mock(return_value={"apply_status": "applied"})
    monkeypatch.setattr(apply_service, "apply_mount_correction", dispatch)
    apply_service.reset_live_apply_state()
    plan = debug.alignment_plan()
    assert plan["ready"], plan
    applied = debug.alignment_apply(source="live")
    assert applied["ready"], applied
    dispatch.assert_called_once()
    assert applied["planned_alt_delta_deg"] == pytest.approx(
        plan["planned_alt_delta_deg"]
    )
    for rejected_result, authorized in ((wrong, True), (result, False)):
        debug._debug_analysis.read.return_value = {"result": rejected_result}
        live_context["quality"]["location_authorized"] = authorized
        assert debug.alignment_plan()["blocked"]
        assert debug.alignment_apply(source="live")["blocked"]
        dispatch.assert_called_once()
    apply_service.reset_live_apply_state()
    original = copy.deepcopy(result)
    assert (
        adapter.get_analysis_result(owner_token="contract-owner")["result"] == original
    )
    service.state.last_result["astronomy"]["target_pole"] = (
        "south" if latitude > 0 else "north"
    )
    with pytest.raises(RuntimeError, match="mismatch"):
        adapter.get_analysis_result(owner_token="contract-owner")
    assert adapter.stop_analysis(
        session_id=started["session_id"], owner_token="contract-owner"
    )["success"]
