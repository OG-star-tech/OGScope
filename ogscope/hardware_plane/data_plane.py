"""
数据面：环形缓冲区 / Data plane: ring buffer.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock


@dataclass(slots=True)
class FramePacket:
    """帧数据包 / Frame packet."""

    frame_id: int
    timestamp: float
    payload: bytes
    media_type: str


class FrameRingBuffer:
    """轻量帧环形缓冲 / Lightweight frame ring buffer."""

    def __init__(self, capacity: int = 8) -> None:
        self._capacity = max(1, int(capacity))
        self._queue: deque[FramePacket] = deque(maxlen=self._capacity)
        self._seq = 0
        self._lock = Lock()

    def publish(self, payload: bytes, media_type: str = "image/jpeg") -> FramePacket:
        """发布帧 / Publish frame."""
        with self._lock:
            self._seq += 1
            packet = FramePacket(
                frame_id=self._seq,
                timestamp=time.time(),
                payload=payload,
                media_type=media_type,
            )
            self._queue.append(packet)
            return packet

    def latest(self) -> FramePacket | None:
        """读取最新帧 / Read latest frame."""
        with self._lock:
            if not self._queue:
                return None
            return self._queue[-1]
