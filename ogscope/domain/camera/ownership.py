"""单相机消费者与有界操作租约 / Single-camera consumers and bounded operation leases."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, Literal

Consumer = Literal["preview", "analysis", "recording"]


class CameraOwnership:
    """占用规则独立于设备及曝光状态 / Ownership rules are independent of device and exposure state."""

    def __init__(
        self,
        *,
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task],
        check_accepting_work: Callable[[], None],
        on_active: Callable[[], None],
        on_inactive: Callable[[], None],
    ) -> None:
        self.counts: dict[str, int] = {"preview": 0, "analysis": 0, "recording": 0}
        self._operation_leases: dict[str, float] = {}
        self._lease_expiry_task: asyncio.Task | None = None
        self._spawn = spawn
        self._check_accepting_work = check_accepting_work
        self._on_active = on_active
        self._on_inactive = on_inactive

    def acquire(self, consumer: Consumer) -> None:
        """获取占用不直接打开设备 / Acquiring ownership does not open hardware."""
        self._check_accepting_work()
        self.counts[consumer] += 1

    def release(self, consumer: Consumer) -> None:
        """释放幂等且不产生负计数 / Release is bounded at zero."""
        self.counts[consumer] = max(0, self.counts[consumer] - 1)

    @property
    def active(self) -> bool:
        """任意占用保持设备唤醒 / Any owner keeps the device awake."""
        return bool(sum(self.counts.values()) + len(self._operation_leases))

    @property
    def blocks_stop(self) -> bool:
        """普通停止尊重分析、录像和操作租约 / Ordinary stop respects analysis, recording and operation leases."""
        return bool(
            self.counts["analysis"]
            or self.counts["recording"]
            or self._operation_leases
        )

    def snapshot(self) -> dict[str, int]:
        """复制公开计数，调用方不能更改内部占用 / Copy public counts without exposing mutable ownership."""
        return {
            **{name + "_consumers": value for name, value in self.counts.items()},
            "operation_consumers": len(self._operation_leases),
        }

    def begin_shutdown(self) -> None:
        """撤销租约并取消到期任务，终止禁止获取由协调器负责 / Revoke leases and cancel expiry; the coordinator fences acquisition."""
        self._operation_leases.clear()
        if self._lease_expiry_task is not None:
            self._lease_expiry_task.cancel()

    def clear_after_shutdown(self) -> None:
        """仅在释放完成后清空计数 / Clear counts only after confirmed release."""
        for name in self.counts:
            self.counts[name] = 0

    def update_lease(
        self,
        *,
        lease_id: str | None = None,
        release: bool = False,
        ttl_seconds: float = 60.0,
    ) -> dict[str, Any]:
        """Bound task ownership without opening a fake preview / 用有界任务占用替代假预览保活。"""
        now = time.monotonic()
        if release:
            self._operation_leases.pop(lease_id or "", None)
            if not self._operation_leases and self._lease_expiry_task is not None:
                self._lease_expiry_task.cancel()
                self._lease_expiry_task = None
            self._on_inactive()
            return {"success": True, "released": True}
        self._check_accepting_work()
        if lease_id:
            if self._operation_leases.get(lease_id, 0) <= now:
                self._operation_leases.pop(lease_id, None)
                self._on_inactive()
                return {"success": False, "error": "camera_lease_expired"}
        else:
            if len(self._operation_leases) >= 8:
                return {"success": False, "error": "camera_lease_limit"}
            lease_id = uuid.uuid4().hex
        ttl = max(10.0, min(120.0, float(ttl_seconds)))
        self._operation_leases[lease_id] = now + ttl
        self._on_active()
        if self._lease_expiry_task is None or self._lease_expiry_task.done():
            self._lease_expiry_task = self._spawn(self._expire_operation_leases())
        return {"success": True, "lease_id": lease_id, "ttl_seconds": ttl}

    async def _expire_operation_leases(self) -> None:
        """A disconnected owner cannot keep hardware awake forever / 失联持有者不能永久阻止休眠。"""
        current = asyncio.current_task()
        try:
            while self._operation_leases:
                await asyncio.sleep(
                    max(0.01, min(self._operation_leases.values()) - time.monotonic())
                )
                now = time.monotonic()
                self._operation_leases = {
                    key: expiry
                    for key, expiry in self._operation_leases.items()
                    if expiry > now
                }
                self._on_inactive()
        finally:
            if self._lease_expiry_task is current:
                self._lease_expiry_task = None
