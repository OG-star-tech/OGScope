"""独立观测星场与目标契约回归 / Independent observed-field and contract regressions."""

import copy
import math

import erfa
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from ogscope.domain.analysis.astrometry import AstronomyOptions, attach_polar_solution


def observed_field(latitude=40.0, roll=37.0, refraction=False, offset_deg=0.0):
    """由已知物理姿态反向生成星库坐标，不调用产品几何 / Generate catalog matches from a known physical pose."""
    sign = 1 if latitude > 0 else -1
    lat = math.radians(latitude)
    bore = sign * np.array([0.0, math.cos(lat), math.sin(lat)])
    left = np.array([1.0, 0.0, 0.0])
    up = np.cross(bore, left)
    attitude = np.column_stack((bore, left, up))
    attitude = Rotation.from_rotvec(bore * math.radians(roll)).as_matrix() @ attitude
    attitude = (
        Rotation.from_rotvec(
            np.array([1.0, 0.0, 0.0]) * math.radians(offset_deg)
        ).as_matrix()
        @ attitude
    )
    rng = np.random.default_rng(419)
    xy = rng.uniform([-500, -270], [500, 270], (36, 2))
    focal = 1280 / (2 * math.tan(math.radians(13.0) / 2))
    rays = np.column_stack((np.ones(len(xy)), -xy[:, 0] / focal, -xy[:, 1] / focal))
    rays /= np.linalg.norm(rays, axis=1)[:, None]
    sky = rays @ attitude.T
    az = np.arctan2(sky[:, 0], sky[:, 1]) % (2 * math.pi)
    zd = np.arccos(sky[:, 2])
    utc = erfa.dtf2d("UTC", 2026, 10, 31, 0, 0, 0.0)
    ra, dec = erfa.atoc13(
        "A",
        az,
        zd,
        *utc,
        0.0,
        math.radians(116),
        lat,
        0.0,
        0.0,
        0.0,
        1013.25 if refraction else 0.0,
        10.0,
        0.5,
        0.55,
    )
    catalog = np.column_stack(
        (np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec))
    )
    u, _, vt = np.linalg.svd(rays.T @ catalog)
    raw_rotation = u @ vt
    row = {
        "status": "MATCH_FOUND",
        "observation_time_utc": "2026-10-31T00:00:00Z",
        "ra_deg": math.degrees(math.atan2(raw_rotation[0, 1], raw_rotation[0, 0]))
        % 360,
        "dec_deg": math.degrees(math.asin(raw_rotation[0, 2])),
        "roll_deg": math.degrees(math.atan2(raw_rotation[1, 2], raw_rotation[2, 2]))
        % 360,
        "fov_deg": 13.0,
        "tetra": {
            "epoch_equinox": 2000.0,
            "epoch_proper_motion": 2026.0,
            "distortion": 0.0,
        },
        "solve_frame": {"session_id": "test", "frame_id": 12},
        "solve_overlay": {
            "frame_shape": [720, 1280],
            "stars_matched": [
                {
                    "x": x + 640,
                    "y": y + 360,
                    "ra_deg": math.degrees(r),
                    "dec_deg": math.degrees(d),
                }
                for (x, y), r, d in zip(xy, ra, dec)
            ],
        },
    }
    context = {
        "observer": {
            "latitude_deg": latitude,
            "longitude_deg": 116.0,
            "altitude_m": 0.0,
        }
    }
    return row, context, attitude


@pytest.mark.parametrize("latitude", [20.0, 40.0, 70.0, -20.0, -40.0, -70.0])
@pytest.mark.parametrize("roll", [0.0, 37.0, 180.0, 270.0])
def test_physical_pole_is_zero_and_j2000_pole_is_not(latitude, roll):
    row, context, attitude = observed_field(latitude, roll)
    original = copy.deepcopy(row)
    result = attach_polar_solution(
        row, solve_context=context, target_pole="north" if latitude > 0 else "south"
    )
    assert result["astronomy"]["status"] == "valid"
    guide = result["overlay_ext"]["polar_guide"]
    assert guide["angular_sep_deg"] * 3600 < 0.02
    assert guide["target"]["x"] == pytest.approx(640, abs=0.001)
    assert guide["target"]["y"] == pytest.approx(360, abs=0.001)
    assert np.asarray(result["astronomy"]["camera_to_local"]) == pytest.approx(
        attitude[:, [1, 2, 0]], abs=1e-7
    )
    assert (90 - abs(row["dec_deg"])) * 60 > 8.5
    assert row == original


@pytest.mark.parametrize("latitude", [20.0, 40.0, -20.0, -40.0])
def test_refraction_is_fitted_across_matched_stars(latitude):
    row, context, _ = observed_field(latitude, refraction=True)
    on = attach_polar_solution(
        row,
        solve_context=context,
        target_pole="north" if latitude > 0 else "south",
        astronomy={"refraction": {"mode": "standard"}},
    )
    off = attach_polar_solution(
        row, solve_context=context, target_pole="north" if latitude > 0 else "south"
    )
    assert on["astronomy"]["status"] == "valid"
    assert on["overlay_ext"]["polar_guide"]["angular_sep_deg"] * 3600 < 0.05
    assert off["overlay_ext"]["polar_guide"]["angular_sep_deg"] * 3600 > 50
    assert on["astronomy"]["refraction"]["mode"] == "standard"


def test_roll_and_image_sign_follow_actual_camera_axes():
    row, context, attitude = observed_field(offset_deg=0.5)
    result = attach_polar_solution(row, solve_context=context)
    guide = result["overlay_ext"]["polar_guide"]
    assert guide["angular_sep_deg"] == pytest.approx(0.5, abs=1e-5)
    camera = attitude.T @ np.array(
        [0, math.cos(math.radians(40)), math.sin(math.radians(40))]
    )
    expected = -1280 / (2 * math.tan(math.radians(13) / 2)) * camera[1:] / camera[0]
    assert [guide["delta_px"]["dx"], guide["delta_px"]["dy"]] == pytest.approx(
        expected, abs=0.001
    )


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"observation_time_utc": None}, "observation_time_unavailable"),
        (
            {"observation_time_utc": "2026-10-31T00:00:00"},
            "observation_time_unavailable",
        ),
        ({"tetra": {"epoch_equinox": 1950}}, "catalog_epoch_unsupported"),
        ({"frame": "date"}, "catalog_epoch_unsupported"),
        ({"solve_overlay": {}}, "matched_geometry_unavailable"),
    ],
)
def test_invalid_target_keeps_raw_solve_and_fails_closed(change, reason):
    row, context, _ = observed_field()
    result = attach_polar_solution({**row, **change}, solve_context=context)
    assert result["status"] == "MATCH_FOUND"
    assert result["astronomy"]["reason"] == reason
    assert "polar_guide" not in result["overlay_ext"]


def test_timezone_equivalence_and_idempotence():
    row, context, _ = observed_field()
    first = attach_polar_solution(row, solve_context=context)
    second = attach_polar_solution(
        {**row, "observation_time_utc": "2026-10-31T08:00:00+08:00"},
        solve_context=context,
    )
    assert first["astronomy"] == second["astronomy"]
    assert attach_polar_solution(first, solve_context=context) == first


def test_missing_site_and_requested_refraction_are_distinct():
    row, _, _ = observed_field()
    without_site = attach_polar_solution(row)
    assert without_site["astronomy"]["pose_frame"] == "cirs"
    assert without_site["astronomy"]["observer"] is None
    requested = attach_polar_solution(
        row, astronomy={"refraction": {"mode": "standard"}}
    )
    assert requested["astronomy"]["reason"] == "refraction_requires_observer"


def test_refraction_inputs_and_incoherent_policies_are_rejected():
    with pytest.raises(ValueError):
        AstronomyOptions.model_validate({"refraction": {"mode": "measured"}})
    with pytest.raises(ValueError):
        AstronomyOptions.model_validate(
            {"policy": "catalog_visual_v1", "refraction": {"mode": "standard"}}
        )
    with pytest.raises(ValueError):
        AstronomyOptions.model_validate({"policy": "typo"})


def test_explicit_legacy_mode_is_preserved():
    row, _, _ = observed_field()
    result = attach_polar_solution(row, astronomy={"policy": "catalog_visual_v1"})
    assert result["overlay_ext"]["polar_guide"]["target"]["dec_deg"] == 90
    assert not any(result["overlay_ext"]["polar_guide"]["corrections"].values())


@pytest.mark.parametrize("latitude,refraction", [(40.0, False), (-40.0, True)])
def test_rendered_field_through_real_tetra_and_current_pole(
    tmp_path, monkeypatch, latitude, refraction
):
    """真实提星、匹配、序列化到当前目标 / Real extraction, matching and serialization to the current target."""
    from ogscope.algorithms.plate_solve.solver import _tetra_dict_to_result
    from ogscope.vendor.tetra3 import Tetra3

    row, context, _ = observed_field(
        latitude=latitude, refraction=refraction, offset_deg=0.5
    )
    matches = row["solve_overlay"]["stars_matched"]
    table = np.zeros((len(matches), 6), dtype=np.float32)
    table[:, :2] = np.radians([[s["ra_deg"], s["dec_deg"]] for s in matches])
    table[:, 5] = np.linspace(1, 6, len(matches))
    monkeypatch.setattr(
        Tetra3,
        "_build_catalog_path",
        staticmethod(lambda _: ("hip_main", tmp_path / "synthetic")),
    )
    monkeypatch.setattr(
        Tetra3,
        "_load_catalog",
        staticmethod(lambda *args: (table, np.arange(len(matches)), 2000.0)),
    )
    solver = Tetra3(load_database=None)
    database = tmp_path / "synthetic_database"
    solver.generate_database(
        max_fov=13,
        save_as=database,
        lattice_field_oversampling=10,
        patterns_per_lattice_field=20,
        verification_stars_per_fov=100,
        star_max_magnitude=7,
        epoch_proper_motion=2026,
    )
    solver.load_database(database)
    yy, xx = np.mgrid[:720, :1280]
    image = np.full((720, 1280), 10.0)
    for i, star in enumerate(matches):
        image += (220 - i * 3) * np.exp(
            -((xx + 0.5 - star["x"]) ** 2 + (yy + 0.5 - star["y"]) ** 2) / (2 * 1.5**2)
        )
    from PIL import Image

    raw = solver.solve_from_image(
        Image.fromarray(image.astype(np.float32)),
        fov_estimate=13,
        fov_max_error=0.2,
        return_matches=True,
    )
    assert raw["RA"] is not None
    centroids = np.asarray(raw["matched_centroids"])
    solved = _tetra_dict_to_result(
        raw,
        len(centroids),
        "rendered_test",
        centroids_yx=centroids,
        frame_shape_original=(720, 1280),
        solve_shape=(720, 1280),
    )
    result_row = {
        **row,
        "ra_deg": solved.ra_deg,
        "dec_deg": solved.dec_deg,
        "roll_deg": solved.roll_deg,
        "fov_deg": solved.fov_deg,
        "tetra": solved.raw,
        "solve_overlay": solved.solve_overlay,
    }
    result = attach_polar_solution(
        result_row,
        solve_context=context,
        target_pole="north" if latitude > 0 else "south",
        astronomy={"refraction": {"mode": "standard" if refraction else "off"}},
    )
    assert result["astronomy"]["status"] == "valid"
    assert result["astronomy"]["fit_rmse_arcsec"] < 1.0
    assert result["overlay_ext"]["polar_guide"]["angular_sep_deg"] == pytest.approx(
        0.5, abs=1 / 3600
    )


def test_exposure_clock_binding_is_once_and_bad_time_keeps_raw():
    """可信时间只绑定一次，坏时间保留原始解算 / Bind trusted time once; retain raw solves on bad time."""
    from ogscope.domain.analysis.astrometry import bind_exposure_time

    row = {"observation_time_utc": "2026-10-31T00:00:00Z"}
    bind_exposure_time(row, 3600)
    original = copy.deepcopy(row)
    bind_exposure_time(row, 7200)
    assert row == original and row["observation_time_utc"] == "2026-10-31T01:00:00Z"
    bad = {"observation_time_utc": "bad"}
    bind_exposure_time(bad, 3600)
    assert bad == {"observation_time_utc": "bad"}


def test_pole_vector_matches_sofa_iau2006_reference():
    """SOFA 2006-01-01 TT 的固定参考，覆盖时标与矩阵方向 / Fixed SOFA epoch checks time scales and matrix direction."""
    row, _, _ = observed_field()
    row["observation_time_utc"] = "2005-12-31T23:58:55.816Z"
    result = attach_polar_solution(row)
    pole = result["astronomy"]["physical_pole_j2000_vector"]
    # SOFA/ERFA t_xys06a at MJD(TT) 53736 / SOFA/ERFA 标准历元参考值。
    assert pole[0] == pytest.approx(0.5791308482835292617e-3, abs=1e-14)
    assert pole[1] == pytest.approx(0.4020580099454020310e-4, abs=1e-15)
