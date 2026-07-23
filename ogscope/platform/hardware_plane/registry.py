"""
能力注册中心 / Capability registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from ogscope.platform.hardware_plane.contracts import CapabilityKind, CapabilityState


@dataclass(slots=True)
class CapabilityRecord:
    """能力记录 / Capability record."""

    name: str
    kind: CapabilityKind
    state: CapabilityState
    writable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化 / Serialize."""
        return {
            "name": self.name,
            "kind": self.kind.value,
            "state": self.state.value,
            "writable": self.writable,
            "metadata": dict(self.metadata),
        }


class CapabilityRegistry:
    """线程安全能力注册中心 / Thread-safe capability registry."""

    def __init__(self) -> None:
        self._records: dict[str, CapabilityRecord] = {}
        self._lock = Lock()

    def register(self, record: CapabilityRecord) -> None:
        """注册能力 / Register capability."""
        with self._lock:
            self._records[record.name] = record

    def update_state(self, name: str, state: CapabilityState) -> None:
        """更新能力状态 / Update capability state."""
        with self._lock:
            record = self._records.get(name)
            if record is None:
                return
            record.state = state

    def list_records(self) -> list[CapabilityRecord]:
        """列出所有能力 / List all capabilities."""
        with self._lock:
            return list(self._records.values())

    def as_dict_list(self) -> list[dict[str, Any]]:
        """字典列表表示 / Dict-list representation."""
        return [record.to_dict() for record in self.list_records()]
