"""
MJPEG 长连接会话限制 / Concurrent MJPEG stream session limiter.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from ogscope.config import get_settings

EVICTED_FOR_NEW_CONNECTION = "evicted_for_new_connection"


@dataclass
class _MjpegSessionState:
    """保存单个流会话的活跃时间与淘汰回调 / Track timing and the eviction
    callback for one stream session."""

    acquired_mono: float
    last_progress_mono: float
    on_evict: Callable[[], None] | None = None


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

    async def set_evict_callback(self, callback: Callable[[], None]) -> None:
        """注册被强制淘汰时触发的回调（同步、非阻塞）/ Register a callback
        fired if this lease is forcibly evicted to make room for a new
        connection (sync, non-blocking - schedule any real cleanup work as
        its own task)."""
        await self._limiter._set_evict_callback(self._session_id, callback)

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

    async def try_acquire(self) -> MjpegStreamLease:
        """返回会话租约；已满时淘汰最久未发送进展的一路，为新连接让位 /
        Return a session lease; when full, evict whichever session has gone
        longest without send progress to make room for the new one.

        名额上限存在是为了控制并发缓冲区占用的内存，不是为了拒绝新的预览
        请求；到了上限时，与其向新连接返回 503，不如淘汰看起来最"旧"（最
        久未成功推进）的那一路，直接把名额让给新连接——这也顺带比原来的
        停滞看门狗更快地清掉一个实际已经死掉、只是还没到停滞超时的连接。
        The slot cap exists to bound concurrent buffer memory, not to
        reject new preview requests; when full, evicting whichever session
        looks "oldest" (longest since it last actually made progress) and
        handing the slot straight to the new connection is more useful than
        a 503 - and it also clears out a connection that's effectively
        already dead faster than waiting for the separate stall watchdog to
        time it out.
        """
        evict_callback: Callable[[], None] | None = None
        async with self._lock:
            if self._max > 0 and len(self._sessions) >= self._max:
                stalest_id = min(
                    self._sessions,
                    key=lambda sid: self._sessions[sid].last_progress_mono,
                )
                evict_callback = self._sessions.pop(stalest_id).on_evict
                self._release_reasons[EVICTED_FOR_NEW_CONNECTION] += 1
            session_id = self._next_session_id
            self._next_session_id += 1
            now = time.monotonic()
            self._sessions[session_id] = _MjpegSessionState(now, now)
            lease = MjpegStreamLease(self, session_id)
        # Fire the evicted session's own cleanup outside the lock - it may
        # eventually call back into this limiter (e.g. release()), which
        # would deadlock on a non-reentrant lock still held here.
        if evict_callback is not None:
            evict_callback()
        return lease

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
                "evicted_clients_total": self._release_reasons.get(
                    EVICTED_FOR_NEW_CONNECTION, 0
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

    async def _set_evict_callback(
        self, session_id: int, callback: Callable[[], None]
    ) -> None:
        async with self._lock:
            state = self._sessions.get(session_id)
            if state is not None:
                state.on_evict = callback

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
