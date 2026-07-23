"""Sensor-assisted solve prediction / 传感器辅助解算预测."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

DEFAULT_SENSOR_MATCH_THRESHOLD_DEG = 25.0


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _normalize_deg(value: float) -> float:
    return value % 360.0


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def julian_date(when_utc: datetime) -> float:
    """Julian date from UTC datetime / UTC 时间转儒略日."""
    dt = when_utc.astimezone(timezone.utc)
    year = dt.year
    month = dt.month
    day = dt.day
    hour = dt.hour + dt.minute / 60.0 + (dt.second + dt.microsecond / 1e6) / 3600.0
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5
    return jd + hour / 24.0


def gmst_deg(jd: float) -> float:
    """Greenwich mean sidereal time in degrees / 格林尼治平恒星时（度）."""
    t = (jd - 2451545.0) / 36525.0
    gmst = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * t * t
        - (t * t * t) / 38710000.0
    )
    return _normalize_deg(gmst)


def local_sidereal_time_deg(longitude_deg: float, when_utc: datetime) -> float:
    """Local sidereal time in degrees / 地方恒星时（度）."""
    return _normalize_deg(gmst_deg(julian_date(when_utc)) + longitude_deg)


def horizontal_to_equatorial(
    *,
    altitude_deg: float,
    azimuth_deg: float,
    latitude_deg: float,
    longitude_deg: float,
    when_utc: datetime,
) -> tuple[float, float]:
    """Convert Alt/Az to RA/Dec; azimuth is north-based clockwise.

    地平坐标转赤道坐标；方位角从北顺时针计算。
    """
    lat_r = math.radians(latitude_deg)
    alt_r = math.radians(altitude_deg)
    az_r = math.radians(azimuth_deg)
    sin_dec = math.sin(alt_r) * math.sin(lat_r) + math.cos(alt_r) * math.cos(
        lat_r
    ) * math.cos(az_r)
    dec_r = math.asin(max(-1.0, min(1.0, sin_dec)))
    ha_r = math.atan2(
        -math.sin(az_r) * math.cos(alt_r),
        math.sin(alt_r) * math.cos(lat_r)
        - math.cos(alt_r) * math.sin(lat_r) * math.cos(az_r),
    )
    ra_deg = _normalize_deg(
        local_sidereal_time_deg(longitude_deg, when_utc) - math.degrees(ha_r)
    )
    return ra_deg, math.degrees(dec_r)


def angular_separation_deg(
    ra1_deg: float,
    dec1_deg: float,
    ra2_deg: float,
    dec2_deg: float,
) -> float:
    """Great-circle distance between two RA/Dec points / 两个赤道坐标点的大圆距离."""
    ra1 = math.radians(ra1_deg)
    dec1 = math.radians(dec1_deg)
    ra2 = math.radians(ra2_deg)
    dec2 = math.radians(dec2_deg)
    cos_sep = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(
        dec2
    ) * math.cos(ra1 - ra2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    return value if isinstance(value, dict) else {}


def predict_from_solve_context(
    solve_context: Any,
) -> dict[str, Any]:
    """Build predicted RA/Dec from optional sensor context.

    从可选传感器上下文生成预测赤经赤纬。
    """
    ctx = _as_dict(solve_context)
    observer = _as_dict(ctx.get("observer"))
    orientation = _as_dict(ctx.get("orientation"))
    quality = _as_dict(ctx.get("quality"))
    if not ctx:
        return {"sensor_status": "unavailable"}

    gps_valid = bool(quality.get("gps_valid"))
    time_valid = bool(quality.get("time_valid"))
    mount_valid = bool(quality.get("mount_valid"))
    heading_valid = bool(quality.get("heading_valid"))
    lat = _optional_float(observer.get("latitude_deg"))
    lon = _optional_float(observer.get("longitude_deg"))
    when = _parse_utc(observer.get("time_utc"))
    alt = _optional_float(orientation.get("altitude_deg"))
    az = _optional_float(orientation.get("azimuth_deg"))
    if az is None:
        az = _optional_float(orientation.get("heading_deg"))
    if (
        not gps_valid
        or not time_valid
        or lat is None
        or lon is None
        or when is None
        or alt is None
        or az is None
    ):
        return {"sensor_status": "unavailable"}
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0 and -90.0 <= alt <= 90.0):
        return {"sensor_status": "unavailable"}
    if not (mount_valid or heading_valid):
        return {"sensor_status": "unavailable"}
    predicted_ra, predicted_dec = horizontal_to_equatorial(
        altitude_deg=alt,
        azimuth_deg=az,
        latitude_deg=lat,
        longitude_deg=lon,
        when_utc=when,
    )
    return {
        "predicted_ra_deg": round(predicted_ra, 6),
        "predicted_dec_deg": round(predicted_dec, 6),
        "sensor_delta_deg": None,
        "sensor_status": "predicted",
    }


def attach_sensor_prediction(
    row: dict[str, Any],
    solve_context: Any,
    *,
    threshold_deg: float = DEFAULT_SENSOR_MATCH_THRESHOLD_DEG,
) -> None:
    """Attach sensor prediction to a solve row in-place / 就地附加传感器预测结果。"""
    if solve_context is None:
        return
    prediction = predict_from_solve_context(solve_context)
    if prediction.get("sensor_status") != "predicted":
        row["sensor_prediction"] = prediction
        return
    ra = _optional_float(row.get("ra_deg"))
    dec = _optional_float(row.get("dec_deg"))
    if str(row.get("status") or "") != "MATCH_FOUND" or ra is None or dec is None:
        row["sensor_prediction"] = prediction
        return
    delta = angular_separation_deg(
        float(prediction["predicted_ra_deg"]),
        float(prediction["predicted_dec_deg"]),
        ra,
        dec,
    )
    prediction["sensor_delta_deg"] = round(delta, 6)
    prediction["sensor_status"] = "matched" if delta <= threshold_deg else "mismatch"
    row["sensor_prediction"] = prediction
