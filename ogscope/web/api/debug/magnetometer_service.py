"""
磁力计调试自检（AK09911 系列 I²C）/ Magnetometer debug self-test (AK09911 family on I²C).
"""

from __future__ import annotations

import asyncio
import glob
import os
import re
import subprocess
from typing import Any

# WIA：与 Linux ak09911 驱动及数据手册一致 / Matches upstream ak09911 driver & datasheets.
_AKM_WIA1 = 0x48
# AK09911 WIA2=0x09；部分变体（如 AK09911C）可能为 0x05 / AK09911 uses 0x09; some variants use 0x05.
_KNOWN_WIA2 = frozenset({0x05, 0x09})


def _list_i2c_device_nodes() -> list[str]:
    paths = sorted(glob.glob("/dev/i2c-[0-9]*"))
    return [p for p in paths if os.path.exists(p)]


def _run_i2cdetect(bus: int) -> tuple[str | None, str | None]:
    """调用系统 i2cdetect（若存在）/ Run system i2cdetect when available."""
    for bin_name in ("/usr/sbin/i2cdetect", "/sbin/i2cdetect"):
        if os.path.isfile(bin_name):
            try:
                proc = subprocess.run(
                    [bin_name, "-y", str(bus)],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                out = (proc.stdout or "") + (proc.stderr or "")
                if proc.returncode == 0:
                    return out.strip(), None
                return None, out.strip() or f"exit {proc.returncode}"
            except (OSError, subprocess.SubprocessError) as exc:
                return None, str(exc)
    return None, "i2cdetect not found"


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
            addr7: 7-bit 从机地址（CAD 接 GND 时为 0x0C）/ 7-bit slave address.
            run_i2cdetect: 是否尝试执行 i2cdetect / Whether to run i2cdetect.
        """
        nodes = _list_i2c_device_nodes()
        i2c_text: str | None = None
        i2c_err: str | None = None
        if run_i2cdetect:
            i2c_text, i2c_err = await asyncio.to_thread(_run_i2cdetect, bus)

        wia = await asyncio.to_thread(_smbus_read_wia, bus, addr7)

        overall_ok = bool(wia.get("ok") and wia.get("matches_ak099xx"))

        hint: str | None = None
        if not nodes:
            hint = (
                "未找到 /dev/i2c-*：请确认已启用 I²C（config.txt 中 dtparam=i2c_arm=on）"
                "并已加载 i2c-dev（例如 /etc/modules-load.d/i2c-dev.conf）。"
                " / No /dev/i2c-*: enable I²C in firmware and load i2c-dev."
            )
        elif not wia.get("ok"):
            hint = (
                "无法在总线上读取芯片 ID：检查接线、地址（CAD→GND=0x0C）、"
                "以及运行服务的用户是否在 i2c 组。"
                " / Cannot read chip ID: wiring, address, or i2c group membership."
            )
        elif not wia.get("matches_ak099xx"):
            hint = (
                f"读到了 WIA1=0x{int(wia.get('wia1') or 0):02x} WIA2=0x{int(wia.get('wia2') or 0):02x}，"
                "与 AK09911 系列常见值不完全一致；仍可作为原始数据供排查。"
                " / WIA bytes do not match expected AK09911 family pattern."
            )

        return {
            "success": overall_ok,
            "chip_detected_as_ak099xx": bool(wia.get("matches_ak099xx")),
            "platform": os.name,
            "i2c_dev_nodes": nodes,
            "bus": int(bus),
            "addr_7bit": int(addr7),
            "addr_7bit_hex": f"0x{int(addr7):02x}",
            "i2cdetect": {"stdout": i2c_text, "stderr_or_note": i2c_err},
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
            w = await asyncio.to_thread(_smbus_read_wia, b, addr7)
            results.append({"bus": b, **w})
        any_ok = any(
            r.get("ok") and r.get("matches_ak099xx") for r in results
        )
        return {
            "success": any_ok,
            "addr_7bit": int(addr7),
            "per_bus": results,
        }

