"""
调试 API 对同一 Linux I²C 总线的串行访问，减轻并发 SMBus 导致的 EREMOTEIO(121)。
/ Serialize SMBus on one bus across debug endpoints to reduce concurrent NACK (errno 121).
"""

from __future__ import annotations

import asyncio

# 覆盖树莓派常见 i2c-* 编号 / Covers typical Pi i2c-N ids
_I2C_DEBUG_LOCKS: dict[int, asyncio.Lock] = {i: asyncio.Lock() for i in range(33)}


def i2c_debug_bus_lock(bus: int) -> asyncio.Lock:
    """返回总线 `bus` 对应的锁；未知编号时钳位到 0–32。/ Lock for bus id (clamped)."""
    b = max(0, min(32, int(bus)))
    return _I2C_DEBUG_LOCKS[b]
