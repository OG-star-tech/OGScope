"""
AK09911 / AK09911C 磁力计 I2C 访问（Linux `/dev/i2c-*`）/ AK09911 family magnetometer over I2C.

引脚由设备树绑定到 i2c 总线；本模块只负责总线号与 7-bit 从地址 / Pins are bound by DT; this module only uses bus id and 7-bit address.
"""

from __future__ import annotations

import errno
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# AK09911 系列寄存器（AK09911C 兼容）/ AK09911-class register map
REG_WIA1 = 0x00
REG_WIA2 = 0x01
REG_HXL = 0x03
REG_ST1 = 0x10
REG_ST2 = 0x18
REG_CNTL2 = 0x31

EXPECTED_WIA1 = 0x48
EXPECTED_WIA2 = 0x09  # AK09911；若读数不同仍以原始值回报 / AK09911; raw values still reported if different
# 与调试层一致：AK09911C 等变体 WIA2 可能为 0x05 / Same as debug layer for AK09911C WIA2.
_KNOWN_WIA2_FAMILY: frozenset[int] = frozenset({0x05, 0x09})
_AK09911_ADDR7_CAD: tuple[int, int] = (0x0C, 0x0D)

# 数据手册典型灵敏度（单测模式 16bit）/ Typical sensitivity from datasheet (µT/LSB)
AK09911_UT_PER_LSB = 0.4915


@dataclass(slots=True)
class Ak09911ProbeResult:
    """一次探测结果 / Single probe outcome."""

    wia1: int | None
    wia2: int | None
    present: bool
    error: str | None = None


@dataclass(slots=True)
class Ak09911Measurement:
    """单次测量原始值 / Single measurement (raw + scaled)."""

    hx: int
    hy: int
    hz: int
    ut_x: float
    ut_y: float
    ut_z: float


@dataclass(slots=True)
class Ak09911IoError:
    """I2C 失败上下文 / Structured I2C failure context."""

    stage: str
    errno: int | None
    message: str
    addr7: int

    def to_text(self) -> str:
        return (
            f"[{self.stage}] {self.message}"
            f" (addr=0x{self.addr7:02x}, errno={self.errno})"
        )


def i2c_dev_path(bus: int) -> str:
    return f"/dev/i2c-{int(bus)}"


def ensure_i2c_dev_node(bus: int) -> str | None:
    """若节点不存在则返回 None / Missing char dev (e.g. i2c-dev not loaded)."""
    path = i2c_dev_path(bus)
    return path if os.path.exists(path) else None


def scan_i2c_bus(bus: int, *, timeout_sec: float = 3.0) -> dict[str, Any]:
    """
    调用系统 `i2cdetect` 扫描总线 / Run i2cdetect -y <bus>.

    返回地址列表（十六进制字符串）与原始文本 / Returns hex strings and raw text.
    """
    exe = "/usr/sbin/i2cdetect"
    if not os.path.isfile(exe):
        exe = "i2cdetect"
    try:
        proc = subprocess.run(
            [exe, "-y", str(int(bus))],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        return {"success": False, "addresses": [], "raw": "", "error": str(e)}
    raw = (proc.stdout or "") + (proc.stderr or "")
    addrs: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not re.match(r"^[0-9a-f]{2}:", line):
            continue
        for token in line.split()[1:]:
            t = token.lower()
            if len(t) == 2 and re.match(r"^[0-9a-f]{2}$", t) and t not in ("--", "uu"):
                addrs.append(t)
    return {
        "success": proc.returncode == 0,
        "addresses": sorted(set(addrs), key=lambda x: int(x, 16)),
        "raw": raw.strip(),
        "error": None if proc.returncode == 0 else f"i2cdetect exit {proc.returncode}",
    }


def wia_matches_ak099xx_family(wia1: int, wia2: int) -> bool:
    """是否为 AK09911 系 WIA 组合 / Whether WIA matches AK09911-class pattern."""
    return wia1 == EXPECTED_WIA1 and int(wia2) in _KNOWN_WIA2_FAMILY


def _read_wia_smbus(bus: int, addr7: int) -> Ak09911ProbeResult:
    from smbus2 import SMBus

    try:
        with SMBus(bus) as smbus:
            wia1 = smbus.read_byte_data(addr7, REG_WIA1)
            wia2 = smbus.read_byte_data(addr7, REG_WIA2)
    except OSError as e:
        return Ak09911ProbeResult(None, None, False, str(e))
    present = wia_matches_ak099xx_family(wia1, wia2)
    return Ak09911ProbeResult(wia1, wia2, present, None)


def probe_ak09911(bus: int, addr7: int) -> Ak09911ProbeResult:
    """读 WIA1/WIA2 / Read WHO_AM_I bytes."""
    path = ensure_i2c_dev_node(bus)
    if path is None:
        return Ak09911ProbeResult(
            None, None, False, f"missing {i2c_dev_path(bus)} (load i2c-dev?)"
        )
    return _read_wia_smbus(bus, addr7)


def _combine_hxl_6(b: list[int]) -> tuple[int, int, int]:
    def s16(lo: int, hi: int) -> int:
        v = lo | (hi << 8)
        return v - 0x10000 if v & 0x8000 else v

    if len(b) < 6:
        raise ValueError("need 6 bytes")
    return s16(b[0], b[1]), s16(b[2], b[3]), s16(b[4], b[5])


def _err_ctx(stage: str, exc: OSError, addr7: int) -> Ak09911IoError:
    """包装 OSError 为可序列化诊断结构 / Convert OSError to serializable error context."""
    return Ak09911IoError(
        stage=stage,
        errno=getattr(exc, "errno", None),
        message=str(exc),
        addr7=int(addr7),
    )


def _measure_body_smbus(smbus: Any, addr7: int) -> Ak09911Measurement:
    """单次测量（已打开 SMBus）/ Single-shot read with an open SMBus handle."""
    try:
        smbus.write_byte_data(addr7, REG_CNTL2, 0x01)
    except OSError as exc:
        raise RuntimeError(_err_ctx("cntl2_write", exc, addr7).to_text()) from exc
    deadline = time.monotonic() + 0.35
    st1 = 0
    while time.monotonic() < deadline:
        try:
            st1 = smbus.read_byte_data(addr7, REG_ST1)
        except OSError as exc:
            raise RuntimeError(_err_ctx("st1_read", exc, addr7).to_text()) from exc
        if st1 & 0x01:
            break
        time.sleep(0.002)
    if not (st1 & 0x01):
        logger.warning("AK09911 DRDY timeout addr=0x%02x st1=0x%02x", addr7, st1)
    data: list[int] | None = None
    last_io: OSError | None = None
    for read_try in range(4):
        try:
            data = list(smbus.read_i2c_block_data(addr7, REG_HXL, 6))
            break
        except OSError as exc:
            last_io = exc
            en = getattr(exc, "errno", None)
            if read_try >= 3 or en not in (
                errno.EREMOTEIO,
                errno.EIO,
                errno.ENXIO,
            ):
                raise RuntimeError(_err_ctx("hxl_read", exc, addr7).to_text()) from exc
            time.sleep(0.006 * (read_try + 1))
    if data is None:
        if last_io is not None:
            raise RuntimeError(
                _err_ctx("hxl_read", last_io, addr7).to_text()
            ) from last_io
        raise RuntimeError("hxl_read unknown error")
    try:
        _ = smbus.read_byte_data(addr7, REG_ST2)
    except OSError as exc:
        en = getattr(exc, "errno", None)
        if en in (errno.EREMOTEIO, errno.EIO, errno.ENXIO):
            time.sleep(0.004)
            try:
                _ = smbus.read_byte_data(addr7, REG_ST2)
            except OSError as exc2:
                raise RuntimeError(
                    _err_ctx("st2_read", exc2, addr7).to_text()
                ) from exc2
        else:
            raise RuntimeError(_err_ctx("st2_read", exc, addr7).to_text()) from exc
    hx, hy, hz = _combine_hxl_6(data)
    s = AK09911_UT_PER_LSB
    return Ak09911Measurement(
        hx,
        hy,
        hz,
        round(hx * s, 3),
        round(hy * s, 3),
        round(hz * s, 3),
    )


def measure_single_smbus(bus: int, addr7: int) -> Ak09911Measurement | None:
    """单次测量模式读磁场（原始 + µT）/ Single-shot measurement."""
    from smbus2 import SMBus

    with SMBus(bus) as smbus:
        return _measure_body_smbus(smbus, addr7)


def measure_heading_with_cad_fallback(
    bus: int,
    preferred: int = 0x0C,
    *,
    bus_retries: int = 8,
) -> tuple[Ak09911Measurement | None, int | None, str | None, str | None]:
    """
    同一 SMBus 会话内先校验 WIA 再测量，并在 0x0C/0x0D 与总线重试间切换。
    / One SMBus session per try: WIA then measure; alternate CAD addrs and retries for EREMOTEIO.
    """
    from smbus2 import SMBus

    path = ensure_i2c_dev_node(bus)
    if path is None:
        return None, None, f"missing {i2c_dev_path(bus)}", "dev_missing"

    pref = int(preferred)
    if pref in _AK09911_ADDR7_CAD:
        order: list[int] = [pref] + [a for a in _AK09911_ADDR7_CAD if a != pref]
    else:
        order = [pref]

    last_err: str | None = None
    last_stage: str | None = None
    for attempt in range(max(1, int(bus_retries))):
        for addr7 in order:
            try:
                with SMBus(bus) as smbus:
                    try:
                        w1 = smbus.read_byte_data(addr7, REG_WIA1)
                        w2 = smbus.read_byte_data(addr7, REG_WIA2)
                    except OSError as exc:
                        ectx = _err_ctx("wia_read", exc, addr7)
                        last_err = ectx.to_text()
                        last_stage = ectx.stage
                        continue
                    if not wia_matches_ak099xx_family(w1, w2):
                        last_err = (
                            f"[wia_mismatch] WIA1=0x{w1:02x} WIA2=0x{w2:02x}"
                            f" (addr=0x{addr7:02x})"
                        )
                        last_stage = "wia_mismatch"
                        continue
                    time.sleep(0.004)
                    meas = _measure_body_smbus(smbus, addr7)
                    return meas, addr7, None, None
            except OSError as e:
                last_err = str(e)
                last_stage = "bus_open"
                continue
            except RuntimeError as e:
                # _measure_body_smbus 已包装阶段信息 / stage text is already embedded
                last_err = str(e)
                if str(e).startswith("[") and "]" in str(e):
                    last_stage = str(e)[1 : str(e).index("]")]
                continue
        time.sleep(min(0.06, 0.018 * (attempt + 1)))
    return (
        None,
        None,
        last_err or "AK09911 WIA/measure failed on bus",
        last_stage or "unknown",
    )


def measure_single(
    bus: int, addr7: int
) -> tuple[Ak09911Measurement | None, str | None]:
    path = ensure_i2c_dev_node(bus)
    if path is None:
        return None, f"missing {i2c_dev_path(bus)}"
    try:
        return measure_single_smbus(bus, addr7), None
    except OSError as e:
        return None, str(e)
    except Exception as e:
        logger.exception("AK09911 measure failed")
        return None, str(e)


def run_ak09911c_self_test(bus: int, addr7: int) -> dict[str, Any]:
    """
    汇总探测：扫描、WIA、可选单次测量 / Combined probe for debug API.

    `addr7` 为 7-bit 地址（如 0x0C）/ 7-bit slave address (e.g. 0x0C).
    """
    bus = int(bus)
    addr7 = int(addr7)
    out: dict[str, Any] = {
        "bus": bus,
        "address": addr7,
        "address_hex": f"0x{addr7:02x}",
        "dev_path": i2c_dev_path(bus),
        "dev_exists": ensure_i2c_dev_node(bus) is not None,
        "scan": None,
        "probe": None,
        "measurement": None,
        "success": False,
        "error": None,
    }
    if not out["dev_exists"]:
        out["error"] = (
            f"设备节点不存在: {out['dev_path']}。"
            "请确认已启用 dtparam=i2c_arm=on 且已加载 i2c-dev（例如 /etc/modules-load.d/）。"
        )
        return out

    out["scan"] = scan_i2c_bus(bus)
    probe = probe_ak09911(bus, addr7)
    out["probe"] = {
        "wia1": probe.wia1,
        "wia2": probe.wia2,
        "wia1_hex": None if probe.wia1 is None else f"0x{probe.wia1:02x}",
        "wia2_hex": None if probe.wia2 is None else f"0x{probe.wia2:02x}",
        "expected_wia": f"0x{EXPECTED_WIA1:02x} / 0x{EXPECTED_WIA2:02x}",
        "match": probe.present,
        "error": probe.error,
    }
    if probe.error:
        out["error"] = probe.error
        out["success"] = False
        return out

    meas, merr = measure_single(bus, addr7)
    if meas:
        out["measurement"] = {
            "raw": {"x": meas.hx, "y": meas.hy, "z": meas.hz},
            "ut": {"x": meas.ut_x, "y": meas.ut_y, "z": meas.ut_z},
            "scale_note": f"µT ≈ raw × {AK09911_UT_PER_LSB} (AK09911 典型值)",
        }
    else:
        out["measurement"] = None
        if merr:
            out["error"] = merr

    out["success"] = bool(probe.wia1 is not None and probe.wia2 is not None and meas)
    if out["success"]:
        out["error"] = None
    elif out["error"] is None and not meas:
        out["error"] = "已读到 WIA 但单次测量失败 / WIA ok but measurement failed"
    return out
