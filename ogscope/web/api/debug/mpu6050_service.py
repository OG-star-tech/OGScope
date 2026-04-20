"""
MPU-6050 调试自检（I²C WHO_AM_I）/ MPU-6050 debug self-test (I²C WHO_AM_I).
"""

from __future__ import annotations

import asyncio
import glob
import os
import subprocess
import time
from typing import Any

# InvenSense MPU-6000/6050 数据手册 / Per InvenSense datasheet.
_REG_WHO_AM_I = 0x75
_EXPECT_WHO_AM_I = 0x68
_REG_PWR_MGMT_1 = 0x6B
_REG_GYRO_XOUT_H = 0x43
# 默认 GYRO_CONFIG=0 → ±250°/s，灵敏度 131 LSB/(°/s) / Default ±250 °/s, 131 LSB per °/s.
_DEFAULT_LSB_PER_DPS = 131.0


def _list_i2c_device_nodes() -> list[str]:
    paths = sorted(glob.glob("/dev/i2c-[0-9]*"))
    return [p for p in paths if os.path.exists(p)]


def _run_i2cdetect(bus: int) -> tuple[str | None, str | None]:
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


def _signed16(hi: int, lo: int) -> int:
    v = (int(hi) << 8) | int(lo)
    return v - 0x10000 if v >= 0x8000 else v


def _read_gyro_sample(bus: int, addr7: int) -> dict[str, Any]:
    """唤醒芯片并读陀螺仪原始值，换算为 °/s / Wake and read gyro, scaled to °/s."""
    try:
        from smbus2 import SMBus
    except ImportError:
        return {"ok": False, "error": "smbus2 not installed"}

    path = f"/dev/i2c-{bus}"
    if not os.path.exists(path):
        return {
            "ok": False,
            "error": f"missing {path} (enable dtparam=i2c_arm=on & load i2c-dev)",
        }

    def _io() -> dict[str, Any]:
        with SMBus(bus) as bus_obj:
            who = int(bus_obj.read_byte_data(addr7, _REG_WHO_AM_I))
            if who != _EXPECT_WHO_AM_I:
                return {
                    "ok": False,
                    "error": f"WHO_AM_I=0x{who:02x}, expected 0x{_EXPECT_WHO_AM_I:02x}",
                }
            # 退出睡眠（默认 0x6B 常为 0x40）/ Exit sleep (register often powers up sleeping).
            bus_obj.write_byte_data(addr7, _REG_PWR_MGMT_1, 0x01)
            time.sleep(0.02)
            block = bus_obj.read_i2c_block_data(addr7, _REG_GYRO_XOUT_H, 6)
        gx = _signed16(block[0], block[1])
        gy = _signed16(block[2], block[3])
        gz = _signed16(block[4], block[5])
        scale = _DEFAULT_LSB_PER_DPS
        return {
            "ok": True,
            "error": None,
            "gyro_raw": {"x": gx, "y": gy, "z": gz},
            "gyro_dps": {
                "x": round(gx / scale, 4),
                "y": round(gy / scale, 4),
                "z": round(gz / scale, 4),
            },
            "full_scale_dps": 250,
            "lsb_per_dps": scale,
        }

    try:
        return _io()
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _read_who_am_i(bus: int, addr7: int) -> dict[str, Any]:
    try:
        from smbus2 import SMBus
    except ImportError:
        return {"ok": False, "error": "smbus2 not installed", "who_am_i": None}

    path = f"/dev/i2c-{bus}"
    if not os.path.exists(path):
        return {
            "ok": False,
            "error": f"missing {path} (enable dtparam=i2c_arm=on & load i2c-dev)",
            "who_am_i": None,
        }

    try:
        with SMBus(bus) as bus_obj:
            val = int(bus_obj.read_byte_data(addr7, _REG_WHO_AM_I))
    except OSError as exc:
        return {"ok": False, "error": str(exc), "who_am_i": None}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "who_am_i": None}

    match = val == _EXPECT_WHO_AM_I
    return {
        "ok": True,
        "error": None,
        "who_am_i": val,
        "matches_mpu6050": bool(match),
    }


class MPU6050DebugService:
    """MPU-6050 WHO_AM_I 探针 / MPU-6050 WHO_AM_I probe."""

    @staticmethod
    async def selftest(
        *,
        bus: int = 1,
        addr7: int = 0x68,
        run_i2cdetect: bool = True,
    ) -> dict[str, Any]:
        nodes = _list_i2c_device_nodes()
        i2c_text: str | None = None
        i2c_err: str | None = None
        if run_i2cdetect:
            i2c_text, i2c_err = await asyncio.to_thread(_run_i2cdetect, bus)

        smbus = await asyncio.to_thread(_read_who_am_i, bus, addr7)
        overall = bool(smbus.get("ok") and smbus.get("matches_mpu6050"))

        hint: str | None = None
        if not nodes:
            hint = (
                "未找到 /dev/i2c-*：请启用 I²C 并加载 i2c-dev。"
                " / No /dev/i2c-*: enable I²C and load i2c-dev."
            )
        elif not smbus.get("ok"):
            hint = (
                "无法读取 WHO_AM_I：检查接线、地址（AD0 低=0x68、高=0x69）、"
                "以及用户是否在 i2c 组。"
                " / Cannot read WHO_AM_I: wiring, address, or i2c group."
            )
        elif not smbus.get("matches_mpu6050"):
            hint = (
                f"WHO_AM_I=0x{int(smbus.get('who_am_i') or 0):02x}，"
                "不是 MPU-6050 典型值 0x68（可能是 MPU-9250 等，需对照手册）。"
                " / WHO_AM_I does not match MPU-6050 (0x68)."
            )

        return {
            "success": overall,
            "chip_likely_mpu6050": bool(smbus.get("matches_mpu6050")),
            "platform": os.name,
            "i2c_dev_nodes": nodes,
            "bus": int(bus),
            "addr_7bit": int(addr7),
            "addr_7bit_hex": f"0x{int(addr7):02x}",
            "reg_who_am_i": f"0x{_REG_WHO_AM_I:02x}",
            "expected_who_am_i": f"0x{_EXPECT_WHO_AM_I:02x}",
            "i2cdetect": {"stdout": i2c_text, "stderr_or_note": i2c_err},
            "smbus": smbus,
            "hint": hint,
        }

    @staticmethod
    async def gyro_sample(*, bus: int = 1, addr7: int = 0x68) -> dict[str, Any]:
        """读取陀螺仪角速度（°/s）/ Read gyroscope angular rate in °/s."""
        sample = await asyncio.to_thread(_read_gyro_sample, bus, addr7)
        ok = bool(sample.get("ok"))
        body: dict[str, Any] = {
            "success": ok,
            "bus": int(bus),
            "addr_7bit": int(addr7),
            "addr_7bit_hex": f"0x{int(addr7):02x}",
            "sample": sample,
        }
        if ok:
            body["gyro_dps"] = sample.get("gyro_dps")
            body["gyro_raw"] = sample.get("gyro_raw")
        else:
            body["error"] = sample.get("error")
        return body
