"""
MJPEG 长连接会话限制 / Concurrent MJPEG stream session limiter.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import dataclass

from ogscope.config import get_settings


@dataclass
class _MjpegSessionState:
    """保存单个流会话的活跃时间 / Track timing for one stream session."""

    acquired_mono: float
    last_progress_mono: float


class MjpegStreamLease:
    """可幂等释放的 MJPEG 名额租约 / Idempotently releasable MJPEG slot lease."""

    def __init__(self, limiter: MjpegStreamLimiter, session_id: int) -> None:
        self._limiter = limiter
        self._session_id = session_id

    async def touch(self) -> bool:
        """记录一次已完成的下游发送 / Record one completed downstream send."""
        return await self._limiter._touch(self._session_id)

    async def idle_seconds(self) -> float | None:
        """返回距最近发送进展的秒数 / Return seconds since the latest send progress."""
        return await self._limiter._idle_seconds(self._session_id)

    async def release(self, reason: str = "released") -> bool:
        """幂等释放租约并记录原因 / Idempotently release the lease and record its reason."""
        return await self._limiter._release(self._session_id, reason)


class MjpegStreamLimiter:
    """限制并跟踪 MJPEG 响应，防止失联客户端永久占位 / Limit and track MJPEG responses."""

    def __init__(self, max_clients: int) -> None:
        self._max = max(0, int(max_clients))
        self._next_session_id = 1
        self._sessions: dict[int, _MjpegSessionState] = {}
        self._release_reasons: Counter[str] = Counter()
        self._lock = asyncio.Lock()

    @property
    def max_clients(self) -> int:
        return self._max

    @property
    def active_clients(self) -> int:
        return len(self._sessions)

    async def try_acquire(self) -> MjpegStreamLease | None:
        """若未超限则返回会话租约 / Return a session lease when under the limit."""
        async with self._lock:
            if self._max > 0 and len(self._sessions) >= self._max:
                return None
            session_id = self._next_session_id
            self._next_session_id += 1
            now = time.monotonic()
            self._sessions[session_id] = _MjpegSessionState(now, now)
            return MjpegStreamLease(self, session_id)

    async def snapshot(self) -> dict[str, object]:
        """生成无敏感标识的会话指标 / Build session metrics without client identifiers."""
        async with self._lock:
            now = time.monotonic()
            states = list(self._sessions.values())
            return {
                "active_clients": len(states),
                "oldest_client_age_ms": int(
                    max((now - state.acquired_mono for state in states), default=0.0)
                    * 1000
                ),
                "oldest_client_idle_ms": int(
                    max(
                        (now - state.last_progress_mono for state in states),
                        default=0.0,
                    )
                    * 1000
                ),
                "released_clients_total": sum(self._release_reasons.values()),
                "stalled_clients_total": self._release_reasons.get(
                    "client_stall_timeout", 0
                ),
                "release_reasons": dict(self._release_reasons),
            }

    async def _touch(self, session_id: int) -> bool:
        async with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return False
            state.last_progress_mono = time.monotonic()
            return True

    async def _idle_seconds(self, session_id: int) -> float | None:
        async with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return None
            return max(0.0, time.monotonic() - state.last_progress_mono)

    async def _release(self, session_id: int, reason: str) -> bool:
        async with self._lock:
            if self._sessions.pop(session_id, None) is None:
                return False
            self._release_reasons[reason or "released"] += 1
            return True


_limiter: MjpegStreamLimiter | None = None


def get_mjpeg_stream_limiter() -> MjpegStreamLimiter:
    """单例，配置来自 Settings / Singleton from app settings."""
    global _limiter
    if _limiter is None:
        _limiter = MjpegStreamLimiter(get_settings().stream_max_mjpeg_clients)
    return _limiter
