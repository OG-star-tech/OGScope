"""Shared catalog visual target / 共享星库视觉目标。"""

from __future__ import annotations

import math
from typing import Any


def build_catalog_polar_guide(row: dict[str, Any]) -> dict[str, Any] | None:
    """构建极轴引导向量 / Build polar guide vector from solve center."""
    overlay = row.get("solve_overlay")
    if not isinstance(overlay, dict):
        return None
    frame_shape = overlay.get("frame_shape")
    if (
        not isinstance(frame_shape, list)
        or len(frame_shape) < 2
        or frame_shape[0] in (None, 0)
        or frame_shape[1] in (None, 0)
    ):
        return None
    try:
        h = float(frame_shape[0])
        w = float(frame_shape[1])
        ra_center = float(row.get("ra_deg"))
        dec_center = float(row.get("dec_deg"))
    except (TypeError, ValueError):
        return None
    fov_deg = row.get("fov_deg")
    roll_deg = row.get("roll_deg")
    if fov_deg is None:
        return None
    try:
        fov = float(fov_deg)
    except (TypeError, ValueError):
        return None
    roll = 0.0
    try:
        if roll_deg is not None:
            roll = float(roll_deg)
    except (TypeError, ValueError):
        roll = 0.0

    if not all(math.isfinite(v) for v in (h, w, ra_center, dec_center, fov, roll)):
        return None
    if h <= 0 or w <= 0 or not -90 <= dec_center <= 90 or not 0 < fov < 180:
        return None
    if row.get("frame") == "date":
        return None

    # 会话指定天极；旧客户端缺省仍使用北天极，不从画面推断。
    # Select the session's pole; legacy callers default north, never infer from the image.
    pole = row.get("target_pole", "north")
    if pole not in ("north", "south"):
        return None
    target_ra = ra_center
    target_dec = -90.0 if pole == "south" else 90.0
    d_ra = target_ra - ra_center
    while d_ra > 180.0:
        d_ra -= 360.0
    while d_ra < -180.0:
        d_ra += 360.0
    d_dec = target_dec - dec_center
    east_deg = d_ra * math.cos(math.radians(dec_center))
    north_deg = d_dec
    roll_rad = math.radians(roll)
    # Image x right, y down; Tetra3 Roll is CCW from image up (y→0).
    # 图像 x 向右、y 向下；Tetra3 Roll 从图像上方逆时针计量。
    x_deg = east_deg * math.cos(roll_rad) - north_deg * math.sin(roll_rad)
    y_deg = east_deg * math.sin(roll_rad) + north_deg * math.cos(roll_rad)

    # Tetra3 FOV is horizontal; scale pixels per degree by frame width.
    # Tetra3 FOV 为水平视场，按图像宽度换算每度像素数。
    px_per_deg = (w / max(fov, 1e-6)) if fov > 0 else 1.0
    dx_px = x_deg * px_per_deg
    dy_px = -y_deg * px_per_deg
    cx = w * 0.5
    cy = h * 0.5
    tx = cx + dx_px
    ty = cy + dy_px

    c_dec = math.radians(dec_center)
    t_dec = math.radians(target_dec)
    d_ra_rad = math.radians(d_ra)
    cos_ang = math.sin(c_dec) * math.sin(t_dec) + math.cos(c_dec) * math.cos(
        t_dec
    ) * math.cos(d_ra_rad)
    cos_ang = max(-1.0, min(1.0, cos_ang))
    angular_sep_deg = math.degrees(math.acos(cos_ang))

    return {
        "target_kind": f"{pole}_celestial_pole",
        "target_frame": "catalog_j2000",
        "target_policy": "catalog_visual_v1",
        "corrections": {
            "precession": False,
            "nutation": False,
            "aberration": False,
            "refraction": False,
        },
        "image_offset_deg": {"dx": x_deg, "dy": -y_deg},
        "frame_center": {
            "x": cx,
            "y": cy,
            "ra_deg": ra_center,
            "dec_deg": dec_center,
        },
        "target": {"x": tx, "y": ty, "ra_deg": target_ra, "dec_deg": target_dec},
        "delta_px": {"dx": dx_px, "dy": dy_px},
        "angular_sep_deg": angular_sep_deg,
    }


def attach_catalog_polar_guide(row: dict[str, Any]) -> dict[str, Any]:
    """Copy a successful solve with its authoritative target / 为成功解算副本附加权威目标。"""
    if row.get("status") != "MATCH_FOUND":
        return row
    guide = build_catalog_polar_guide(row)
    ext = dict(row.get("overlay_ext") or {})
    if guide is None:
        ext.pop("polar_guide", None)
    else:
        ext["polar_guide"] = guide
    return {**row, "overlay_ext": ext}
