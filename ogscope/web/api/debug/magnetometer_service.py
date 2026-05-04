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

from ogscope.platform.hardware.ak09911_i2c import measure_single, scan_i2c_bus

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
            used, w = await asyncio.to_thread(_smbus_read_wia_first_matching, b, addr7)
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
        resolved, wia = await asyncio.to_thread(
            _smbus_read_wia_first_matching, int(bus), int(addr7)
        )
        if not (wia.get("ok") and wia.get("matches_ak099xx")):
            return {
                "success": False,
                "error": wia.get("error")
                or "WIA probe failed (not AK09911 family at 0x0C/0x0D)",
                "heading_deg": None,
                "field_ut": None,
                "field_raw": None,
            }
        meas, err = await asyncio.to_thread(measure_single, int(bus), int(resolved))
        if err or meas is None:
            return {
                "success": False,
                "error": err or "measurement failed",
                "heading_deg": None,
                "field_ut": None,
                "field_raw": None,
            }
        hx, hy = float(meas.hx), float(meas.hy)
        heading_rad = math.atan2(hx, hy)
        heading_deg = (math.degrees(heading_rad) + 360.0) % 360.0
        return {
            "success": True,
            "error": None,
            "bus": int(bus),
            "addr_7bit": int(resolved),
            "addr_7bit_hex": f"0x{int(resolved):02x}",
            "heading_deg": round(heading_deg, 2),
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
        }

