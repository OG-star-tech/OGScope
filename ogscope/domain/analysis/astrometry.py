"""当前极轴与观测姿态的唯一计算入口 / Single current-pole astrometry authority."""

from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import erfa
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.optimize import minimize_scalar

CURRENT_POLICY = "current_pole_v1"
LEGACY_POLICY = "catalog_visual_v1"


class RefractionOptions(BaseModel):
    """显式环境来源与有界参数 / Explicit environmental source and bounded inputs."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    mode: Literal["off", "standard", "measured"] = "off"
    pressure_hpa: float | None = Field(default=None, gt=0, le=1100)
    temperature_c: float | None = Field(default=None, ge=-80, le=60)
    relative_humidity: float = Field(default=0.5, ge=0, le=1)
    wavelength_um: float = Field(default=0.55, ge=0.3, le=2.0)

    @model_validator(mode="after")
    def require_measurements(self) -> RefractionOptions:
        """实测模式不得虚构气压或温度 / Measured mode requires actual measurements."""
        if self.mode == "measured" and (
            self.pressure_hpa is None or self.temperature_c is None
        ):
            raise ValueError("Measured refraction requires pressure and temperature")
        if self.mode != "measured" and self.pressure_hpa is not None:
            raise ValueError("Pressure measurements require measured mode")
        if self.mode == "off" and self.temperature_c is not None:
            raise ValueError("Temperature requires enabled refraction")
        return self


class AstronomyOptions(BaseModel):
    """会话冻结策略，基础天文转换不可拆散 / Freeze a coherent astronomical policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    policy: Literal["current_pole_v1", "catalog_visual_v1"] = CURRENT_POLICY
    refraction: RefractionOptions = Field(default_factory=RefractionOptions)

    @model_validator(mode="after")
    def coherent_policy(self) -> AstronomyOptions:
        """历史基线不允许混入折射 / Keep the historical baseline uncorrected."""
        if self.policy == LEGACY_POLICY and self.refraction.mode != "off":
            raise ValueError("The catalogue baseline requires refraction off")
        return self


class TargetUnavailable(ValueError):
    """原始解算仍有效，但目标条件不满足 / A solve can succeed without a usable target."""


def plain_context(value: Any) -> dict[str, Any]:
    """隔离调用方可变上下文 / Isolate mutable caller context."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def parse_utc(value: Any) -> datetime:
    """拒绝缺失时区和不可信历元 / Reject absent zones and unsupported epochs."""
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if when.tzinfo is None or not 2000 <= when.year <= 2099:
            raise ValueError
        return when.astimezone(timezone.utc)
    except (ValueError, TypeError) as exc:
        raise TargetUnavailable("observation_time_unavailable") from exc


def bind_exposure_time(row: dict[str, Any], offset_seconds: float) -> None:
    """仅对板端曝光时间应用一次可信偏移 / Apply trusted offset once to board exposure time."""
    if (
        not row.get("observation_time_utc")
        or row.get("observation_time_reference") == "source_utc"
    ):
        return
    original = row["observation_time_utc"]
    try:
        # 未同步板端可以从旧日期启动，校验修正后的时刻 / An unsynchronized board may boot at an old epoch; validate the corrected time.
        raw_time = datetime.fromisoformat(str(original).replace("Z", "+00:00"))
        if raw_time.tzinfo is None:
            return
        corrected = parse_utc(
            (raw_time + timedelta(seconds=offset_seconds)).isoformat()
        )
    except (ValueError, TypeError, OverflowError):
        return
    row.update(
        board_observation_time_utc=original,
        observation_time_utc=corrected.isoformat().replace("+00:00", "Z"),
        observation_time_reference="source_utc",
        clock_offset_s=offset_seconds,
    )


def _unit(rows: np.ndarray) -> np.ndarray:
    return rows / np.linalg.norm(rows, axis=-1, keepdims=True)


def _vectors(ra: Any, dec: Any) -> np.ndarray:
    ra, dec = np.asarray(ra), np.asarray(dec)
    return np.stack(
        (np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)), axis=-1
    )


def _altaz(vector: np.ndarray) -> tuple[float, float]:
    return (
        math.degrees(math.asin(float(np.clip(vector[2], -1, 1)))),
        math.degrees(math.atan2(vector[0], vector[1])) % 360,
    )


def _angle(first: np.ndarray, second: np.ndarray) -> float:
    return math.degrees(
        math.atan2(
            float(np.linalg.norm(np.cross(first, second))), float(np.dot(first, second))
        )
    )


def _camera_rays(
    yx: np.ndarray, height: float, width: float, fov: float, distortion: float
) -> np.ndarray:
    """Tetra 相机坐标为前/左/上 / Tetra camera coordinates are forward/left/up."""
    delta = np.asarray(yx, dtype=float) - [height / 2, width / 2]
    radius2 = np.sum(delta * delta, axis=1) * (2 / width) ** 2
    delta = delta * ((1 - distortion * radius2) / (1 - distortion))[:, None]
    scale = 2 * math.tan(math.radians(fov) / 2) / width
    return _unit(
        np.column_stack(
            (np.ones(len(delta)), -delta[:, 1] * scale, -delta[:, 0] * scale)
        )
    )


def _fit(
    yx: np.ndarray,
    sky: np.ndarray,
    height: float,
    width: float,
    fov: float,
    distortion: float,
) -> tuple[np.ndarray, float, float]:
    """逐星拟合刚性姿态与焦距 / Fit attitude and focal scale from corrected matched stars."""

    def evaluate(value: float) -> tuple[np.ndarray, float]:
        camera = _camera_rays(yx, height, width, value, distortion)
        u, _, vt = np.linalg.svd(camera.T @ sky)
        rotation = u @ np.diag([1, 1, np.linalg.det(u @ vt)]) @ vt
        return rotation, float(np.mean(np.sum((camera @ rotation - sky) ** 2, axis=1)))

    fitted = minimize_scalar(
        lambda value: evaluate(value)[1],
        bounds=(fov * 0.98, fov * 1.02),
        method="bounded",
        options={"xatol": 1e-9},
    )
    if not fitted.success:
        raise TargetUnavailable("attitude_fit_failed")
    rotation, loss = evaluate(float(fitted.x))
    return rotation, float(fitted.x), math.degrees(math.sqrt(loss)) * 3600


def _pixel_target(
    camera: np.ndarray, height: float, width: float, fov: float, distortion: float
) -> tuple[float, float]:
    """反解同一个镜头模型，包含中心点 / Invert the same lens model, including its centre."""
    if camera[0] <= 0:
        raise TargetUnavailable("target_behind_camera")
    focal = width / (2 * math.tan(math.radians(fov) / 2))
    delta = -focal * np.array([camera[1], camera[2]]) / camera[0]
    ru = float(np.linalg.norm(delta))
    if ru > 1e-12 and distortion:
        rd = ru
        kp = distortion * (2 / width) ** 2
        for _ in range(40):
            derivative = (1 - 3 * kp * rd * rd) / (1 - distortion)
            if derivative <= 0:
                raise TargetUnavailable("target_projection_out_of_range")
            step = (rd * (1 - kp * rd * rd) / (1 - distortion) - ru) / derivative
            rd -= step
            if abs(step) < 1e-7:
                break
        else:
            raise TargetUnavailable("target_projection_out_of_range")
        delta *= rd / ru
    return width / 2 + float(delta[0]), height / 2 + float(delta[1])


def _site(context: dict[str, Any]) -> dict[str, float | None] | None:
    observer = context.get("observer") or {}
    if observer.get("latitude_deg") is None or observer.get("longitude_deg") is None:
        return None
    lat, lon, alt = (
        float(observer["latitude_deg"]),
        float(observer["longitude_deg"]),
        (
            float(observer["altitude_m"])
            if observer.get("altitude_m") is not None
            else None
        ),
    )
    if (
        not all(math.isfinite(v) for v in (lat, lon))
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
        or (alt is not None and (not math.isfinite(alt) or not -500 <= alt <= 10000))
    ):
        raise TargetUnavailable("observer_invalid")
    return {"latitude_deg": lat, "longitude_deg": lon, "altitude_m": alt}


def build_current_pole(
    row: dict[str, Any],
    options: AstronomyOptions,
    context: dict[str, Any],
    target_pole: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """原始匹配星点到物理极轴，禁止二次修正 / Raw matches to the physical pole, once."""
    if row.get("observation_time_error"):
        raise TargetUnavailable(str(row["observation_time_error"]))
    when = parse_utc(row.get("observation_time_utc"))
    quality = context.get("quality") or {}
    if quality.get("time_valid") is False or quality.get("time_fresh") is False:
        raise TargetUnavailable("observation_time_untrusted")
    raw = row.get("tetra") or {}
    if (
        row.get("frame") not in (None, "j2000", "catalog_j2000")
        or raw.get("epoch_equinox") != 2000.0
    ):
        raise TargetUnavailable("catalog_epoch_unsupported")
    overlay = row.get("solve_overlay") or {}
    shape = overlay.get("frame_shape") or []
    matches = overlay.get("stars_matched") or []
    if len(shape) < 2 or len(matches) < 4:
        raise TargetUnavailable("matched_geometry_unavailable")
    height, width = float(shape[0]), float(shape[1])
    fov, k = float(row["fov_deg"]), float(raw.get("distortion") or 0)
    yx = np.array([[m["y"], m["x"]] for m in matches], dtype=float)
    catalog = np.radians(
        np.array([[m["ra_deg"], m["dec_deg"]] for m in matches], dtype=float)
    )
    if (
        not (height > 0 and width > 0 and 0 < fov < 90 and abs(k) < 0.5)
        or not np.isfinite(yx).all()
        or not np.isfinite(catalog).all()
        or np.any(np.abs(catalog[:, 1]) > math.pi / 2)
    ):
        raise TargetUnavailable("matched_geometry_invalid")
    if np.linalg.matrix_rank(yx - np.mean(yx, axis=0), tol=0.5) < 2:
        raise TargetUnavailable("matched_geometry_degenerate")
    site = _site(context)
    ref = options.refraction
    if ref.mode != "off" and site is None:
        raise TargetUnavailable("refraction_requires_observer")
    if ref.mode == "standard" and site["altitude_m"] is None:
        raise TargetUnavailable("refraction_requires_altitude")
    pressure = (
        0.0
        if ref.mode == "off"
        else (
            float(ref.pressure_hpa)
            if ref.mode == "measured"
            else 1013.25 * math.exp(-float(site["altitude_m"]) / 8434.5)
        )
    )
    temperature = float(ref.temperature_c) if ref.temperature_c is not None else 10.0
    utc = erfa.dtf2d(
        "UTC",
        when.year,
        when.month,
        when.day,
        when.hour,
        when.minute,
        when.second + when.microsecond / 1e6,
    )
    tt = erfa.taitt(*erfa.utctai(*utc))
    if site:
        astrom, _ = erfa.apco13(
            *utc,
            0.0,
            math.radians(site["longitude_deg"]),
            math.radians(site["latitude_deg"]),
            float(site["altitude_m"] or 0),
            0.0,
            0.0,
            pressure,
            temperature,
            ref.relative_humidity,
            ref.wavelength_um,
        )
    else:
        astrom, _ = erfa.apci13(*tt)
    ri, di = erfa.atciqz(catalog[:, 0], catalog[:, 1], astrom)
    sign = 1 if target_pole == "north" else -1
    if site:
        az, zd, _, _, _ = erfa.atioq(ri, di, astrom)
        if ref.mode != "off" and (
            np.any(zd > math.radians(85)) or sign * site["latitude_deg"] < 5
        ):
            raise TargetUnavailable("refraction_altitude_out_of_range")
        sky = np.column_stack(
            (np.sin(zd) * np.sin(az), np.sin(zd) * np.cos(az), np.cos(zd))
        )
        lat = math.radians(site["latitude_deg"])
        pole = sign * np.array([0.0, math.cos(lat), math.sin(lat)])
        frame = "observed_enu"
    else:
        sky = _vectors(ri, di)
        pole = np.array([0.0, 0.0, float(sign)])
        frame = "cirs"
    rotation, fitted_fov, residual = _fit(yx, sky, height, width, fov, k)
    camera_pole = rotation @ pole
    x, y = _pixel_target(camera_pole, height, width, fitted_fov, k)
    boresight = rotation[0]
    separation = _angle(boresight, pole)
    physical_j2000 = sign * erfa.pnm06a(*tt)[2]
    corrections = {
        "precession": True,
        "nutation": True,
        "aberration": True,
        "refraction": ref.mode != "off",
        "solar_deflection": True,
        "diurnal_aberration": site is not None,
        "polar_motion": False,
        "proper_motion": False,
    }
    astronomy = {
        "status": "valid",
        "policy": CURRENT_POLICY,
        "target_pole": target_pole,
        "model": "ERFA IAU2006/2000A",
        "model_version": erfa.__version__,
        "observation_time_utc": when.isoformat().replace("+00:00", "Z"),
        "time_source": (
            "trusted_context" if quality.get("time_valid") else "supplied_exposure_utc"
        ),
        "observer": site,
        "corrections": corrections,
        "requested": options.model_dump(),
        "refraction": {
            "mode": ref.mode,
            "pressure_hpa": pressure,
            "pressure_source": (
                "disabled"
                if ref.mode == "off"
                else "measured" if ref.mode == "measured" else "altitude_estimate"
            ),
            "temperature_source": (
                "unused"
                if ref.mode == "off"
                else (
                    "standard"
                    if ref.temperature_c is None
                    else "measured" if ref.mode == "measured" else "manual"
                )
            ),
            "temperature_c": temperature,
            "relative_humidity": ref.relative_humidity,
            "wavelength_um": ref.wavelength_um,
        },
        "earth_orientation": {
            "dut1_seconds": 0.0,
            "dut1_source": "assumed",
            "polar_motion_source": "omitted",
        },
        "catalog_epoch_equinox": raw["epoch_equinox"],
        "catalog_epoch_proper_motion": raw.get("epoch_proper_motion"),
        "attitude_method": "matched_stars",
        "matched_stars": len(matches),
        "fit_rmse_arcsec": residual,
        "fitted_fov_deg": fitted_fov,
        "distortion": k,
        "camera_basis": "left_up_forward",
        "pose_frame": frame,
        "camera_to_local": rotation.T[:, [1, 2, 0]].tolist(),
        "boresight_vector": boresight.tolist(),
        "pole_vector": pole.tolist(),
        "physical_pole_j2000_vector": physical_j2000.tolist(),
        "solve_frame": copy.deepcopy(row.get("solve_frame")),
    }
    guide = {
        "target_kind": f"{target_pole}_celestial_pole",
        "target_pole": target_pole,
        "target_frame": frame,
        "target_policy": CURRENT_POLICY,
        "corrections": corrections,
        "observation_time_utc": astronomy["observation_time_utc"],
        "frame_center": {
            "x": width / 2,
            "y": height / 2,
            "ra_deg": row["ra_deg"],
            "dec_deg": row["dec_deg"],
            "vector": boresight.tolist(),
        },
        "target": {"x": x, "y": y, "vector": pole.tolist()},
        "image_offset_deg": {
            "dx": math.degrees(math.atan2(-camera_pole[1], camera_pole[0])),
            "dy": math.degrees(math.atan2(-camera_pole[2], camera_pole[0])),
        },
        "delta_px": {"dx": x - width / 2, "dy": y - height / 2},
        "angular_sep_deg": separation,
    }
    if site:
        for obj, vector in (
            (guide["frame_center"], boresight),
            (guide["target"], pole),
        ):
            obj["alt_deg"], obj["az_deg"] = _altaz(vector)
    return astronomy, guide


def attach_polar_solution(
    row: dict[str, Any],
    *,
    astronomy: Any = None,
    solve_context: Any = None,
    target_pole: str = "north",
) -> dict[str, Any]:
    """同一入口服务 Core、文件及开发预览 / Shared authority for Core, files and previews."""
    options = (
        astronomy
        if isinstance(astronomy, AstronomyOptions)
        else AstronomyOptions.model_validate(astronomy or {})
    )
    if target_pole not in {"north", "south"}:
        raise ValueError("Unknown target pole")
    if options.policy == LEGACY_POLICY:
        from ogscope.domain.analysis.polar_guide import attach_catalog_polar_guide

        return attach_catalog_polar_guide(
            {key: value for key, value in row.items() if key != "astronomy"},
            target_pole=target_pole,
        )
    result = {**row, "overlay_ext": dict(row.get("overlay_ext") or {})}
    result["overlay_ext"].pop("polar_guide", None)
    if row.get("status") != "MATCH_FOUND":
        return result
    try:
        result["astronomy"], result["overlay_ext"]["polar_guide"] = build_current_pole(
            row, options, plain_context(solve_context), target_pole
        )
    except (ValueError, KeyError, TypeError, np.linalg.LinAlgError) as exc:
        result["astronomy"] = {
            "status": "unavailable",
            "policy": CURRENT_POLICY,
            "target_pole": target_pole,
            "reason": (
                str(exc)
                if isinstance(exc, TargetUnavailable)
                else "astrometry_input_invalid"
            ),
            "requested": options.model_dump(),
        }
    return result
