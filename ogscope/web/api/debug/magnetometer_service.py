"""
磁力计调试自检（AK09911 系列 I²C）/ Magnetometer debug self-test (AK09911 family on I²C).
"""

from __future__ import annotations

import asyncio
import glob
import math
import os
import re
from typing import Any

from ogscope.platform.hardware.ak09911_i2c import (
    measure_heading_with_cad_fallback,
    scan_i2c_bus,
)
from ogscope.web.api.debug.i2c_debug_bus_lock import i2c_debug_bus_lock

# WIA：与 Linux ak09911 驱动及数据手册一致 / Matches upstream ak09911 driver & datasheets.
_AKM_WIA1 = 0x48
# AK09911 WIA2=0x09；部分变体（如 AK09911C）可能为 0x05 / AK09911 uses 0x09; some variants use 0x05.
_KNOWN_WIA2 = frozenset({0x05, 0x09})
# CAD 脚决定 I²C 地址：常见为 0x0C 或 0x0D / CAD pin selects slave address.
_AK09911_ADDR7_CANDIDATES: tuple[int, ...] = (0x0C, 0x0D)


def _list_i2c_device_nodes() -> list[str]:
    paths = sorted(glob.glob("/dev/i2c-[0-9]*"))
    return [p for p in paths if os.path.exists(p)]


def _smbus_read_wia(bus: int, addr7: int) -> dict[str, Any]:
    """读取寄存器 0x00、0x01（WIA1/WIA2）/ Read WIA1/WIA2 registers."""
    try:
        from smbus2 import SMBus
    except ImportError:
        return {"ok": False, "error": "smbus2 not installed", "wia1": None, "wia2": None}

    path = f"/dev/i2c-{bus}"
    if not os.path.exists(path):
        return {
            "ok": False,
            "error": f"missing {path} (enable dtparam=i2c_arm=on & load i2c-dev)",
            "wia1": None,
            "wia2": None,
        }

    def _read() -> tuple[int | None, int | None, str | None]:
        try:
            with SMBus(bus) as bus_obj:
                w1 = int(bus_obj.read_byte_data(addr7, 0x00))
                w2 = int(bus_obj.read_byte_data(addr7, 0x01))
                return w1, w2, None
        except OSError as exc:
            return None, None, str(exc)
        except Exception as exc:
            return None, None, str(exc)

    wia1, wia2, err = _read()
    if err:
        return {"ok": False, "error": err, "wia1": None, "wia2": None}
    match = (
        wia1 == _AKM_WIA1 and wia2 is not None and int(wia2) in _KNOWN_WIA2
    )
    return {
        "ok": True,
        "error": None,
        "wia1": wia1,
        "wia2": wia2,
        "matches_ak099xx": bool(match),
    }


def _smbus_read_wia_first_matching(
    bus: int, preferred: int = 0x0C
) -> tuple[int, dict[str, Any]]:
    """
    在 AK09911 常见地址上读 WIA，优先 preferred；另一地址为 CAD 备选。
    / Read WIA on typical AK09911/C addresses (CAD selects 0x0C vs 0x0D).
    """
    pref = int(preferred)
    if pref in _AK09911_ADDR7_CANDIDATES:
        order = [pref] + [a for a in _AK09911_ADDR7_CANDIDATES if a != pref]
    else:
        order = [pref]
    last_addr = pref
    last: dict[str, Any] = {}
    for addr7 in order:
        last = _smbus_read_wia(bus, addr7)
        last_addr = addr7
        if last.get("ok") and last.get("matches_ak099xx"):
            return addr7, last
    return last_addr, last


class MagnetometerDebugService:
    """AK09911 系列探针与总线扫描 / AK09911 family probe and bus scan."""
    _xy_calib: dict[tuple[int, int], dict[str, Any]] = {}
    _heading_mode: dict[tuple[int, int], str] = {}
    _heading_locked: dict[tuple[int, int], dict[str, Any]] = {}

    @staticmethod
    def _pair_values(axes: str, x: float, y: float, z: float) -> tuple[float, float]:
        if axes == "yz":
            return y, z
        if axes == "zx":
            return z, x
        return x, y

    @staticmethod
    def _calc_axis_spans(st: dict[str, Any]) -> tuple[float, float, float]:
        hx_hist = list(st.get("hist_x", []))
        hy_hist = list(st.get("hist_y", []))
        hz_hist = list(st.get("hist_z", []))
        if not hx_hist or not hy_hist or not hz_hist:
            return 0.0, 0.0, 0.0
        return (
            float(max(hx_hist) - min(hx_hist)),
            float(max(hy_hist) - min(hy_hist)),
            float(max(hz_hist) - min(hz_hist)),
        )

    @staticmethod
    def _auto_axes_from_spans(span_x: float, span_y: float, span_z: float) -> str:
        axis_pairs = [
            ("xy", span_x + span_y),
            ("yz", span_y + span_z),
            ("zx", span_z + span_x),
        ]
        return str(max(axis_pairs, key=lambda it: float(it[1]))[0])

    @staticmethod
    def _resolve_record_key(bus: int, addr7: int) -> tuple[int, int]:
        """优先匹配在线地址，其次退回请求地址 / Prefer detected addr then requested addr."""
        b = int(bus)
        req = int(addr7)
        candidates: list[int] = [req]
        if req in _AK09911_ADDR7_CANDIDATES:
            candidates = [req] + [a for a in _AK09911_ADDR7_CANDIDATES if a != req]
        for a in candidates:
            if (b, a) in MagnetometerDebugService._xy_calib:
                return (b, a)
        return (b, req)

    @staticmethod
    async def calibration_start(*, bus: int = 1, addr7: int = 0x0C) -> dict[str, Any]:
        """开始方向校准采样窗口 / Start heading calibration recording window."""
        async with i2c_debug_bus_lock(bus):
            resolved, wia = await asyncio.to_thread(
                _smbus_read_wia_first_matching, int(bus), int(addr7)
            )
        if not (wia.get("ok") and wia.get("matches_ak099xx")):
            return {
                "success": False,
                "error": wia.get("error") or "WIA probe failed",
                "mode": "auto",
                "bus": int(bus),
                "addr_7bit_requested": int(addr7),
            }
        k = (int(bus), int(resolved))
        MagnetometerDebugService._xy_calib[k] = {
            "hist_x": [],
            "hist_y": [],
            "hist_z": [],
            "samples": 0.0,
        }
        MagnetometerDebugService._heading_mode[k] = "recording"
        return {
            "success": True,
            "mode": "recording",
            "bus": int(bus),
            "addr_7bit_requested": int(addr7),
            "addr_7bit": int(resolved),
            "addr_7bit_hex": f"0x{int(resolved):02x}",
            "hint": "请在 5-15 秒内水平缓慢旋转设备（建议超过 180°）。",
        }

    @staticmethod
    async def calibration_commit(*, bus: int = 1, addr7: int = 0x0C) -> dict[str, Any]:
        """提交方向校准并锁定 / Commit heading calibration and lock parameters."""
        k = MagnetometerDebugService._resolve_record_key(int(bus), int(addr7))
        st = MagnetometerDebugService._xy_calib.get(k)
        if not st:
            return {
                "success": False,
                "error": "no calibration buffer, call calibration/start first",
                "mode": "auto",
                "bus": int(bus),
                "addr_7bit_requested": int(addr7),
            }
        samples = int(float(st.get("samples", 0.0)))
        if samples < 10:
            return {
                "success": False,
                "error": f"insufficient samples: {samples} (<10)",
                "mode": MagnetometerDebugService._heading_mode.get(k, "auto"),
                "bus": int(k[0]),
                "addr_7bit": int(k[1]),
            }

        hx_hist = list(st.get("hist_x", []))
        hy_hist = list(st.get("hist_y", []))
        hz_hist = list(st.get("hist_z", []))
        min_x, max_x = min(hx_hist), max(hx_hist)
        min_y, max_y = min(hy_hist), max(hy_hist)
        min_z, max_z = min(hz_hist), max(hz_hist)
        cx, cy, cz = (min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5
        span_x, span_y, span_z = (max_x - min_x), (max_y - min_y), (max_z - min_z)
        axes = MagnetometerDebugService._auto_axes_from_spans(span_x, span_y, span_z)

        # 以采样轨迹趋势决定方向符号（让序列更趋于增大）/ Infer sign from recording trend.
        prev_u: float | None = None
        unwrapped = 0.0
        for i in range(samples):
            x = float(hx_hist[i]) - cx
            y = float(hy_hist[i]) - cy
            z = float(hz_hist[i]) - cz
            a, b = MagnetometerDebugService._pair_values(axes, x, y, z)
            deg = (math.degrees(math.atan2(a, b)) + 360.0) % 360.0
            if prev_u is None:
                prev_u = deg
                unwrapped = deg
            else:
                d = deg - (prev_u % 360.0)
                d = ((d + 180.0) % 360.0) - 180.0
                unwrapped += d
                prev_u = unwrapped
        trend = unwrapped - ((math.degrees(math.atan2(
            *MagnetometerDebugService._pair_values(
                axes,
                float(hx_hist[0]) - cx,
                float(hy_hist[0]) - cy,
                float(hz_hist[0]) - cz,
            )
        )) + 360.0) % 360.0)
        sign = 1 if trend >= 0 else -1

        locked = {
            "axes_pair": axes,
            "sign": int(sign),
            "offset_deg": 0.0,
            "center": {"x": cx, "y": cy, "z": cz},
            "span": {"x": span_x, "y": span_y, "z": span_z},
            "samples": samples,
        }
        MagnetometerDebugService._heading_locked[k] = locked
        MagnetometerDebugService._heading_mode[k] = "locked"
        return {
            "success": True,
            "mode": "locked",
            "bus": int(k[0]),
            "addr_7bit": int(k[1]),
            "addr_7bit_hex": f"0x{int(k[1]):02x}",
            "locked": locked,
        }

    @staticmethod
    async def calibration_reset(*, bus: int = 1, addr7: int = 0x0C) -> dict[str, Any]:
        """重置方向校准，回到 auto / Reset calibration and return to auto mode."""
        k = MagnetometerDebugService._resolve_record_key(int(bus), int(addr7))
        MagnetometerDebugService._heading_locked.pop(k, None)
        MagnetometerDebugService._heading_mode[k] = "auto"
        return {
            "success": True,
            "mode": "auto",
            "bus": int(k[0]),
            "addr_7bit": int(k[1]),
            "addr_7bit_hex": f"0x{int(k[1]):02x}",
        }

    @staticmethod
    async def calibration_status(*, bus: int = 1, addr7: int = 0x0C) -> dict[str, Any]:
        """查询方向校准状态 / Query heading calibration mode and lock."""
        k = MagnetometerDebugService._resolve_record_key(int(bus), int(addr7))
        st = MagnetometerDebugService._xy_calib.get(k) or {}
        mode = MagnetometerDebugService._heading_mode.get(k, "auto")
        locked = MagnetometerDebugService._heading_locked.get(k)
        span_x, span_y, span_z = MagnetometerDebugService._calc_axis_spans(st)
        return {
            "success": True,
            "mode": mode,
            "bus": int(k[0]),
            "addr_7bit": int(k[1]),
            "addr_7bit_hex": f"0x{int(k[1]):02x}",
            "samples": int(float(st.get("samples", 0.0))),
            "span_xyz": {"x": round(span_x, 3), "y": round(span_y, 3), "z": round(span_z, 3)},
            "locked": locked,
        }

    @staticmethod
    async def selftest(
        *,
        bus: int = 1,
        addr7: int = 0x0C,
        run_i2cdetect: bool = True,
    ) -> dict[str, Any]:
        """
        返回 JSON 可序列化自检结果 / JSON-serializable self-test result.

        Args:
            bus: Linux I²C 总线号（树莓派 GPIO 头一般为 1）/ Linux I²C bus number.
            addr7: 7-bit 从机地址（默认 0x0C；若为 0x0D 会自动尝试另一地址）/ 7-bit slave; auto-fallback.
            run_i2cdetect: 是否尝试执行 i2cdetect / Whether to run i2cdetect.
        """
        nodes = _list_i2c_device_nodes()
        async with i2c_debug_bus_lock(bus):
            i2c_text: str | None = None
            i2c_err: str | None = None
            addresses_seen: list[str] | None = None
            if run_i2cdetect:
                scan = await asyncio.to_thread(scan_i2c_bus, bus)
                i2c_text = (scan.get("raw") or "").strip() or None
                addresses_seen = list(scan.get("addresses") or [])
                if not scan.get("success"):
                    i2c_err = scan.get("error") or "i2cdetect failed"

            requested_addr = int(addr7)
            resolved_addr, wia = await asyncio.to_thread(
                _smbus_read_wia_first_matching, bus, requested_addr
            )
            addr_auto_fallback = bool(
                resolved_addr != requested_addr
                and wia.get("ok")
                and wia.get("matches_ak099xx")
            )

            overall_ok = bool(wia.get("ok") and wia.get("matches_ak099xx"))

            hint: str | None = None
            addr_hex = f"{int(resolved_addr):02x}"
            if not nodes:
                hint = (
                    "未找到 /dev/i2c-*：请确认已启用 I²C（config.txt 中 dtparam=i2c_arm=on）"
                    "并已加载 i2c-dev（例如 /etc/modules-load.d/i2c-dev.conf）。"
                    " / No /dev/i2c-*: enable I²C in firmware and load i2c-dev."
                )
            elif not wia.get("ok"):
                bus_missing = ""
                if (
                    run_i2cdetect
                    and addresses_seen is not None
                    and addr_hex not in addresses_seen
                ):
                    bus_missing = (
                        f"当前总线 {bus} 的 i2cdetect 未列出 {addr_hex}（模块可能未接好、无 3.3V、SDA/SCL 接反，"
                        "或 CAD 决定地址与预期不符）。"
                        " / i2cdetect does not list this address (wiring, power, SDA/SCL, or CAD pin)."
                    )
                hint = (
                    "无法在总线上读取芯片 ID。"
                    + bus_missing
                    + " 亦请核对：AK09911/C 常见为 0x0C 或 0x0D（CAD）、运行用户是否在 i2c 组"
                    "（本机 ogscope 进程通常已含 i2c 附加组）。"
                    " / Cannot read chip ID; check CAD (0x0C vs 0x0D), wiring, and i2c group."
                )
            elif not wia.get("matches_ak099xx"):
                hint = (
                    f"读到了 WIA1=0x{int(wia.get('wia1') or 0):02x} WIA2=0x{int(wia.get('wia2') or 0):02x}，"
                    "与 AK09911 系列常见值不完全一致；仍可作为原始数据供排查。"
                    " / WIA bytes do not match expected AK09911 family pattern."
                )
            elif addr_auto_fallback:
                hint = (
                    f"已在 0x{requested_addr:02X} 与 0x{resolved_addr:02X} 间自动选用后者"
                    "（CAD 决定 I²C 地址；与 i2cdetect 中 0x0D/0x0C 一致即可）。"
                    " / Auto-selected I²C address via CAD (0x0C vs 0x0D)."
                )

            return {
                "success": overall_ok,
                "chip_detected_as_ak099xx": bool(wia.get("matches_ak099xx")),
                "platform": os.name,
                "i2c_dev_nodes": nodes,
                "bus": int(bus),
                "addr_7bit_requested": int(requested_addr),
                "addr_7bit": int(resolved_addr),
                "addr_7bit_hex": f"0x{int(resolved_addr):02x}",
                "addr_auto_fallback": addr_auto_fallback,
                "i2cdetect": {
                    "stdout": i2c_text,
                    "stderr_or_note": i2c_err,
                    "addresses_parsed": addresses_seen,
                    "target_addr_seen": bool(
                        addresses_seen is not None and addr_hex in addresses_seen
                    ),
                },
                "wia": {
                    "wia1": wia.get("wia1"),
                    "wia2": wia.get("wia2"),
                    "expected_wia1": f"0x{_AKM_WIA1:02x}",
                    "expected_wia2_note": "0x05 or 0x09 typical for AK09911/C family",
                },
                "smbus": wia,
                "hint": hint,
            }

    @staticmethod
    async def probe_address_on_buses(
        addr7: int = 0x0C,
        buses: list[int] | None = None,
    ) -> dict[str, Any]:
        """在多个总线上尝试读取 WIA（用于自动找总线）/ Try WIA on several buses."""
        if buses is None:
            nodes = _list_i2c_device_nodes()
            buses = []
            for p in nodes:
                m = re.search(r"i2c-(\d+)$", p)
                if m:
                    buses.append(int(m.group(1)))
            buses = sorted(set(buses)) or [0, 1, 2]
        results: list[dict[str, Any]] = []
        for b in buses:
            async with i2c_debug_bus_lock(b):
                used, w = await asyncio.to_thread(
                    _smbus_read_wia_first_matching, b, addr7
                )
            results.append({"bus": b, "addr_7bit_used": int(used), **w})
        any_ok = any(
            r.get("ok") and r.get("matches_ak099xx") for r in results
        )
        return {
            "success": any_ok,
            "addr_7bit": int(addr7),
            "per_bus": results,
        }

    @staticmethod
    async def sample_heading(*, bus: int = 1, addr7: int = 0x0C) -> dict[str, Any]:
        """
        单次测量并估算水平面内「指北」方位角（用于调试）/ Single shot + horizontal heading for debug.

        航向角定义为 atan2(Hx, Hy)（度，0–360），近似表示传感器 XY 平面内磁场水平分量指向与 +Y 的夹角关系，
        便于罗盘可视化；实际安装需校准或软铁补偿 / Heading uses atan2(Hx, Hy); calibrate for your mount.
        """
        async with i2c_debug_bus_lock(bus):
            meas, resolved, err, err_stage = await asyncio.to_thread(
                measure_heading_with_cad_fallback, int(bus), int(addr7)
            )
        if err or meas is None or resolved is None:
            return {
                "success": False,
                "error": err
                or "WIA/measure failed (not AK09911 family at 0x0C/0x0D or bus error)",
                "error_stage": err_stage or "unknown",
                "heading_deg": None,
                "field_ut": None,
                "field_raw": None,
            }
        addr_req = int(addr7)
        k = (int(bus), int(resolved))
        hx, hy, hz = float(meas.hx), float(meas.hy), float(meas.hz)
        st = MagnetometerDebugService._xy_calib.get(k)
        if st is None:
            st = {
                "hist_x": [hx],
                "hist_y": [hy],
                "hist_z": [hz],
                "samples": 1.0,
            }
            MagnetometerDebugService._xy_calib[k] = st
        else:
            hx_hist = list(st.get("hist_x", []))
            hy_hist = list(st.get("hist_y", []))
            hz_hist = list(st.get("hist_z", []))
            hx_hist.append(hx)
            hy_hist.append(hy)
            hz_hist.append(hz)
            # 保留最近窗口，避免早期极值长期污染 / Keep sliding window to avoid stale extremes.
            if len(hx_hist) > 160:
                hx_hist = hx_hist[-160:]
            if len(hy_hist) > 160:
                hy_hist = hy_hist[-160:]
            if len(hz_hist) > 160:
                hz_hist = hz_hist[-160:]
            st["hist_x"] = hx_hist
            st["hist_y"] = hy_hist
            st["hist_z"] = hz_hist
            st["samples"] = float(st.get("samples", 0.0)) + 1.0

        hx_hist = list(st.get("hist_x", []))
        hy_hist = list(st.get("hist_y", []))
        hz_hist = list(st.get("hist_z", []))
        min_x = min(hx_hist) if hx_hist else hx
        max_x = max(hx_hist) if hx_hist else hx
        min_y = min(hy_hist) if hy_hist else hy
        max_y = max(hy_hist) if hy_hist else hy
        min_z = min(hz_hist) if hz_hist else hz
        max_z = max(hz_hist) if hz_hist else hz
        cx = (min_x + max_x) * 0.5
        cy = (min_y + max_y) * 0.5
        cz = (min_z + max_z) * 0.5
        hx_corr = hx - cx
        hy_corr = hy - cy
        hz_corr = hz - cz
        span_x = max_x - min_x
        span_y = max_y - min_y
        span_z = max_z - min_z

        # 原始角 + 校准角都算，便于前端/日志诊断 / Compute both raw and calibrated heading for diagnosis.
        heading_raw_deg = (math.degrees(math.atan2(hx, hy)) + 360.0) % 360.0
        heading_cal_deg = (math.degrees(math.atan2(hx_corr, hy_corr)) + 360.0) % 360.0

        # 自动选择变化最大的两轴，适配不同安装姿态 / Pick two most-varying axes for mounting differences.
        axis_pairs = [
            ("xy", span_x + span_y, hx_corr, hy_corr),
            ("yz", span_y + span_z, hy_corr, hz_corr),
            ("zx", span_z + span_x, hz_corr, hx_corr),
        ]
        auto_axes, _, auto_a, auto_b = max(axis_pairs, key=lambda it: float(it[1]))
        heading_auto_deg = (math.degrees(math.atan2(auto_a, auto_b)) + 360.0) % 360.0

        # 采样很少时仍用 raw，避免中心未形成时抖动；其余优先用自动轴校准角。
        enough_samples = float(st.get("samples", 0.0)) >= 10.0
        enough_span = max(span_x, span_y, span_z) >= 30.0
        use_corr = bool(enough_samples and enough_span)
        heading_deg = heading_auto_deg if use_corr else heading_raw_deg
        heading_source = f"calibrated_{auto_axes}" if use_corr else "raw_xy"

        mode = MagnetometerDebugService._heading_mode.get(k, "auto")
        locked = MagnetometerDebugService._heading_locked.get(k)
        heading_deg_locked: float | None = None
        if mode == "locked" and locked:
            axes_locked = str(locked.get("axes_pair") or auto_axes)
            sign_locked = int(locked.get("sign") or 1)
            offset_locked = float(locked.get("offset_deg") or 0.0)
            c = locked.get("center") or {}
            lx = hx - float(c.get("x", cx))
            ly = hy - float(c.get("y", cy))
            lz = hz - float(c.get("z", cz))
            la, lb = MagnetometerDebugService._pair_values(axes_locked, lx, ly, lz)
            heading_deg_locked = (
                (math.degrees(math.atan2(sign_locked * la, lb)) + offset_locked + 360.0)
                % 360.0
            )
            heading_deg = heading_deg_locked
            heading_source = f"locked_{axes_locked}"
        return {
            "success": True,
            "error": None,
            "error_stage": None,
            "bus": int(bus),
            "addr_7bit_requested": addr_req,
            "addr_7bit": int(resolved),
            "addr_7bit_hex": f"0x{int(resolved):02x}",
            "addr_auto_fallback": bool(int(resolved) != addr_req),
            "heading_deg": round(heading_deg, 2),
            "heading_raw_deg": round(heading_raw_deg, 2),
            "heading_calibrated_deg": round(heading_cal_deg, 2),
            "heading_auto_deg": round(heading_auto_deg, 2),
            "heading_locked_deg": None if heading_deg_locked is None else round(heading_deg_locked, 2),
            "heading_source": heading_source,
            "heading_axes_auto": auto_axes,
            "heading_mode": mode,
            "heading_note_zh": (
                "水平磁场在 XY 平面内的方向角（0°–360°），用于指北调试；安装姿态不同需换算或校准。"
            ),
            "heading_note_en": (
                "Horizontal-plane field direction (0°–360°) for north-pointing debug; "
                "mounting affects interpretation."
            ),
            "field_ut": {
                "x": meas.ut_x,
                "y": meas.ut_y,
                "z": meas.ut_z,
            },
            "field_raw": {"x": meas.hx, "y": meas.hy, "z": meas.hz},
            "field_raw_center_xy": {"x": round(cx, 3), "y": round(cy, 3)},
            "field_raw_span_xy": {"x": round(span_x, 3), "y": round(span_y, 3)},
            "field_raw_center_xyz": {
                "x": round(cx, 3),
                "y": round(cy, 3),
                "z": round(cz, 3),
            },
            "field_raw_span_xyz": {
                "x": round(span_x, 3),
                "y": round(span_y, 3),
                "z": round(span_z, 3),
            },
            "calibration_samples": int(float(st.get("samples", 0.0))),
            "calibration_locked": locked,
        }

