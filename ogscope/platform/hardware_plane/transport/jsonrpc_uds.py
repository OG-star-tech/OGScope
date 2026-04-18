"""
UDS JSON-RPC 传输（占位实现） / UDS JSON-RPC transport (placeholder).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

JsonCallHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class JsonRpcUdsServer:
    """基于 Unix Domain Socket 的最小 JSON-RPC 服务 / Minimal JSON-RPC over UDS."""

    def __init__(self, socket_path: str, handler: JsonCallHandler) -> None:
        self._socket_path = Path(socket_path)
        self._handler = handler
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        if self._server is not None:
            return
        if self._socket_path.exists():
            self._socket_path.unlink()
        self._server = await asyncio.start_unix_server(
            self._handle_conn,
            path=str(self._socket_path),
        )

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        if self._socket_path.exists():
            self._socket_path.unlink()

    async def _handle_conn(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        while not reader.at_eof():
            line = await reader.readline()
            if not line:
                break
            raw = line.decode("utf-8", errors="ignore").strip()
            if not raw:
                continue
            try:
                request = json.loads(raw)
                method = str(request.get("method", ""))
                params = request.get("params") or {}
                resp = await self._handler(method, params)
            except Exception as exc:  # pragma: no cover
                resp = {"success": False, "error": str(exc), "data": {}}
            writer.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            await writer.drain()
        writer.close()
        await writer.wait_closed()

