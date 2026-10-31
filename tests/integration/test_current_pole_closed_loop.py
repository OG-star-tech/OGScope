"""真实像素闭环验收，可选跨仓环境 / Optional cross-repository real-pixel acceptance.

Set OGSCOPE_TEST_STAR_DATABASE and add ZenitAPA and sky-simulator to PYTHONPATH.
设置星库环境变量，并将 ZenitAPA 和 sky-simulator 检出加入 PYTHONPATH。
Only capture I/O, motor I/O and elapsed time are simulated; no hardware is used.
仅模拟采集、电机接口和流逝时间；不接触硬件。
"""

import json
import math
import os
import random
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

# 可选依赖必须在导入前跳过 / Skip optional dependencies before importing them.
# ruff: noqa: E402
pytest.importorskip("zenitapa.adapters.rest_ogscope.client")
pytest.importorskip("sky_simulator.screen.render")
pytest.importorskip("astropy")

import zenitapa.domain.alignment.apply as apply_module
import zenitapa.domain.alignment.session as session_module
from astropy import units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time
from astropy.utils import iers
from devtools.alignment_sim.clock import VirtualClock, virtual_time
from devtools.alignment_sim.mount import MountConfig, SimMount
from loguru import logger
from sky_simulator.screen.astro import roll_of, vec_to_radec
from sky_simulator.screen.catalog import StarCatalog
from sky_simulator.screen.render import (
    CAMERA_PX_PER_RAD,
    Geometry,
    Look,
    Pointing,
    Renderer,
)
from zenitapa.adapters.rest_ogscope.client import OGScopeRestClient
from zenitapa.domain.alignment.calibration import (
    load_alignment_production_settings,
    load_alignment_settings,
)
from zenitapa.domain.alignment.observer import ObserverConfig

from ogscope.algorithms.plate_solve.solver import PlateSolver
from ogscope.config import get_settings
from ogscope.core.application import core_service
from ogscope.core.realtime import service as realtime


@pytest.fixture
def star_database(monkeypatch):
    """星库为显式本地测试资源 / The catalogue is an explicit local test resource."""
    path = os.environ.get("OGSCOPE_TEST_STAR_DATABASE")
    if not path:
        pytest.skip("OGSCOPE_TEST_STAR_DATABASE is not configured")
    assert Path(path).is_file()
    monkeypatch.setattr(get_settings(), "solver_tetra_database_path", Path(path))
    monkeypatch.setattr(iers.conf, "auto_download", False)
    monkeypatch.setattr(iers.conf, "auto_max_age", None)
    return path


class PixelLoop:
    """以真实图像连接两个产品与底座模型 / Connect both products through real images."""

    def __init__(
        self, client, monkeypatch, database, *, roll=0, refraction=False, fault=""
    ):
        self.clock = VirtualClock(datetime(2026, 10, 31, tzinfo=timezone.utc))
        self.mount = SimMount(
            MountConfig(start_alt_deg=43, start_az_deg=3),
            self.clock,
            random.Random(7),
        )
        self.catalog = StarCatalog.load(database)
        self.stars = SkyCoord(
            ra=self.catalog.ra * u.rad, dec=self.catalog.dec * u.rad, frame="icrs"
        )
        self.geometry = Geometry(
            width=1280,
            height=720,
            px_per_rad=CAMERA_PX_PER_RAD,
            center_x=639.5,
            center_y=359.5,
        )
        self.fov = math.degrees(2 * math.atan(640 / CAMERA_PX_PER_RAD))
        self.roll, self.refraction, self.fault = roll, refraction, fault
        self.next_frame = 0.0
        self.frames, self.events, self.requests = [], [], []
        self.solver = PlateSolver()
        self.service = realtime.RealtimeSolveService()
        monkeypatch.setattr(core_service, "realtime_solve_service", self.service)
        monkeypatch.setattr(
            realtime,
            "get_camera_manager",
            lambda: SimpleNamespace(get_camera_instance=lambda: None),
        )

        async def capture_ready(*args):
            self.service.state.phase = "analyzing"

        monkeypatch.setattr(self.service, "_loop", capture_ready)
        self.adapter = OGScopeRestClient("http://testserver")
        self.adapter.camera_leases_supported = False

        def transport(method, path, payload=None):
            self.requests.append((method, path.split("?")[0]))
            if path.startswith("/api/core/v1/analysis/result"):
                if (
                    self.service.state.running
                    and self.clock.now >= self.next_frame
                    and self.fault != "timeout"
                ):
                    self.publish()
            response = client.request(
                method, path, **({"json": payload} if payload is not None else {})
            )
            response.raise_for_status()
            if path.endswith("/analysis/start"):
                self.next_frame = self.clock.now + 1
            return response.json()

        monkeypatch.setattr(self.adapter, "_json", transport)
        monkeypatch.setattr(
            self.adapter,
            "get_camera_status",
            lambda: {
                "success": True,
                "streaming": True,
                "info": {
                    "optics": {"effective_fov_deg": {"width": self.fov, "height": 7.34}}
                },
            },
        )
        monkeypatch.setattr(
            self.adapter, "reset_camera_temporal_history", lambda: {"success": True}
        )
        prod = replace(
            load_alignment_production_settings(),
            target_mode="ogscope_current_pole",
            refraction_enabled=refraction,
            verify_enabled=True,
            pre_lift_alt_enabled=False,
            convergence_arcmin=0.5,
            max_correction_rounds=5,
            first_solve_timeout_s=8,
            pose_solve_timeout_s=8,
            search_solve_timeout_s=8,
            auto_search_solve_timeout_s=8,
            auto_search_max_total_attempts=2,
            failure_retry_count=0,
        )
        self.session = session_module.AlignmentSession(
            ogscope=self.adapter,
            read_position=self.mount.read_position,
            read_movement=self.mount.read_movement,
            goto_target=self.mount.goto_target,
            goto_target_fast=self.mount.goto_target_fast,
            stop_goto=self.mount.stop_goto,
            prod_settings=prod,
            align_settings=replace(load_alignment_settings(), auto_apply_enabled=True),
            solve_context_provider=self.context,
        )
        self.session.set_start_context(
            {
                "level_status_at_start": "good",
                "level_calibrated_at_start": True,
                "level_tilt_deg_at_start": 0.0,
                "level_pitch_deg_at_start": 0.0,
                "level_roll_deg_at_start": 0.0,
                "level_uncertainty_deg_at_start": 0.0,
            }
        )
        monkeypatch.setattr(
            self.session,
            "_log_event",
            lambda event, **fields: self.events.append({"event": event, **fields}),
        )
        monkeypatch.setattr(
            session_module,
            "get_observer_config",
            lambda: ObserverConfig(latitude_deg=40, longitude_deg=116),
        )
        monkeypatch.setattr(
            session_module,
            "_utc_now",
            lambda: self.clock.utc()
            + timedelta(
                seconds=(
                    3600
                    if fault == "board_offset"
                    else (10 if fault == "clock_step" and self.frames else 0)
                )
            ),
        )
        original_sleep = self.clock.sleep

        def bounded_sleep(seconds):
            assert self.clock.now < 600, "alignment exceeded virtual deadline"
            original_sleep(seconds)
            if self.fault == "cancel" and self.mount.moves:
                self.session.cancel()

        self.clock.sleep = bounded_sleep

    def context(self):
        """模拟可信 GPS 上下文 / Simulate a trusted GPS context."""
        return {
            "observer": {
                "latitude_deg": 40,
                "longitude_deg": 116,
                "altitude_m": 0,
                "source": "zacp_gps",
                "time_utc": self.clock.utc().isoformat(),
                "time_source": "gps",
            },
            "quality": {
                "time_valid": True,
                "time_fresh": not (self.fault == "expired_utc" and self.frames),
                "time_source": "gps",
                "gps_valid": True,
                "position_valid": True,
                "position_source": "gps",
                "location_authorized": True,
            },
        }

    def publish(self):
        """每一帧都从天体正向投影生成 / Generate every frame by forward celestial projection."""
        observed = self.stars.transform_to(
            AltAz(
                obstime=Time(self.clock.utc()),
                location=EarthLocation.from_geodetic(116 * u.deg, 40 * u.deg, 0 * u.m),
                pressure=(1013.25 if self.refraction else 0) * u.hPa,
                temperature=10 * u.deg_C,
                relative_humidity=0.5,
                obswl=0.55 * u.micron,
            )
        )
        az, alt = observed.az.radian, observed.alt.radian
        self.catalog.vec = np.column_stack(
            (np.cos(alt) * np.sin(az), np.cos(alt) * np.cos(az), np.sin(alt))
        )
        bore, up = map(np.asarray, self.mount.axis_direction())
        angle = math.radians(self.roll)
        up = up * math.cos(angle) + np.cross(bore, up) * math.sin(angle)
        ra, dec = vec_to_radec(bore)
        pixels = Renderer(self.catalog).render(
            Pointing(math.degrees(ra), math.degrees(dec), roll_of(bore, up)),
            self.geometry,
            Look(overlay=False),
        )
        if self.fault == "blank":
            pixels[:] = 0
        solved = self.solver.solve_from_bgr_frame(
            cv2.cvtColor(pixels, cv2.COLOR_GRAY2BGR),
            max_stars=100,
            fov_estimate=self.fov,
            fov_max_error=0.2,
            solve_timeout_ms=5000,
        )
        self.service._apply_solve_result(
            solved,
            frame_id=len(self.frames) + 1,
            capture_time={
                "observation_time_utc": self.clock.utc().isoformat(),
                "observation_time_reference": "source_utc",
            },
        )
        self.service.state.frame_count += 1
        self.service.state.fullsolve_count += 1
        self.frames.append(
            {
                "t": self.clock.now,
                "moves": len(self.mount.moves),
                "status": solved.status,
                "receipt": self.service.state.last_result,
            }
        )
        self.next_frame = self.clock.now + 2

    def run(self):
        """运行生产状态机并测量隐藏真值 / Run the production state machine and measure hidden truth."""
        logger.disable("zenitapa")
        try:
            with virtual_time(self.clock, [session_module, apply_module]):
                self.session.run()
        finally:
            logger.enable("zenitapa")
        bore = np.asarray(self.mount.axis_direction()[0])
        pole = np.array([0, math.cos(math.radians(40)), math.sin(math.radians(40))])
        error = (
            math.degrees(math.atan2(np.linalg.norm(np.cross(bore, pole)), bore @ pole))
            * 60
        )
        snap = self.session.snapshot()
        report = {
            "outcome": snap.outcome.value,
            "message": snap.message,
            "error_arcmin": error,
            "virtual_seconds": self.clock.now,
            "moves": len(self.mount.moves),
            "frames": len(self.frames),
        }
        assert not self.service.state.running
        assert not self.mount.moving("altitude")
        assert not self.mount.moving("azimuth")
        return report


@pytest.mark.parametrize(
    "roll,refraction,fault",
    [(0, False, ""), (180, False, "board_offset"), (37, True, "")],
)
def test_current_pole_image_loop_converges(
    client, monkeypatch, star_database, tmp_path, roll, refraction, fault
):
    loop = PixelLoop(
        client,
        monkeypatch,
        star_database,
        roll=roll,
        refraction=refraction,
        fault=fault,
    )
    report = loop.run()
    (tmp_path / "closed-loop.json").write_text(
        json.dumps({"report": report, "events": loop.events}, default=str, indent=2)
    )
    print(json.dumps(report))
    assert report["outcome"] == "success", report
    assert report["error_arcmin"] < 0.5, report
    assert report["moves"] >= 2
    assert any(frame["moves"] >= 2 for frame in loop.frames)
    assert all(
        frame["receipt"]["astronomy"]["status"] == "valid"
        for frame in loop.frames
        if frame["status"] == "MATCH_FOUND"
    )


@pytest.mark.parametrize(
    "fault", ["cancel", "blank", "timeout", "clock_step", "expired_utc"]
)
def test_current_pole_image_loop_stops_safely(
    client, monkeypatch, star_database, fault
):
    loop = PixelLoop(client, monkeypatch, star_database, fault=fault)
    report = loop.run()
    print(json.dumps(report))
    assert report["outcome"] != "success", report
    assert report["virtual_seconds"] < 600
    if fault == "cancel":
        assert report["outcome"] == "cancelled"
        assert report["moves"] == 1
    if fault in {"clock_step", "expired_utc"}:
        assert report["moves"] == 0
    if fault == "timeout":
        assert report["frames"] == 0


def test_current_pole_guard_measures_real_pixels(client, monkeypatch, star_database):
    """守护实测偏移并二次确认，不使用预制误差 / Guard measures and confirms pixel-derived drift."""
    import zenitapa.application.pole_guard as guard_module

    loop = PixelLoop(client, monkeypatch, star_database)
    assert loop.run()["outcome"] == "success"
    started = []
    original_take = guard_module.take_one_solve
    monkeypatch.setattr(
        guard_module,
        "take_one_solve",
        lambda *args, **kwargs: original_take(
            *args, **kwargs, monotonic=loop.clock.monotonic, sleep=loop.clock.sleep
        ),
    )
    guard = guard_module.PoleGuard(
        threshold_provider=lambda: 2.0,
        runtime=SimpleNamespace(
            is_running=lambda: False, snapshot=loop.session.snapshot
        ),
        ogscope=loop.adapter,
        solve_context_provider=loop.context,
        observer_provider=lambda: None,
        clock_offset_from_context=lambda _: 0.0,
        start_alignment=lambda payload: started.append(payload) or {"success": True},
        busy_reason=lambda: None,
        monotonic=loop.clock.monotonic,
        alignment_settings_provider=lambda: loop.session._prod,
    )
    assert guard.enable()["enabled"]
    good = guard.check_once()
    assert good["state"] == "watching"
    assert good["last_error_arcmin"] < 0.5
    assert not started
    # 物理模型施加 6 角分扰动，保留参考回执 / Perturb the physical model by six arcminutes, retaining its reference.
    loop.mount.goto_target("altitude", 40.1)
    loop.clock.sleep(1)
    before = len(loop.frames)
    drift = guard.check_once()
    assert drift["state"] == "realigning", drift
    assert drift["last_error_arcmin"] == pytest.approx(6, abs=0.05)
    assert len(loop.frames) == before + 2
    assert started == [{"level_continue_reason": "pole_guard"}]
    assert not loop.service.state.running
    loop.fault = "expired_utc"
    before = len(loop.frames)
    assert not guard.check_once()["enabled"]
    assert len(loop.frames) == before
    print(
        json.dumps(
            {
                "guard_error_arcmin": drift["last_error_arcmin"],
                "confirmed_frames": 2,
                "realignment_requests": len(started),
            }
        )
    )
