"""统一绑定相机运行实例 / Compose one shared camera runtime."""

import asyncio
from threading import Lock

from ogscope.domain.camera.runtime import CameraCapture, CameraControl, CameraRuntime

_runtime: CameraRuntime | None = None
_binding_lock = Lock()


def get_camera_runtime() -> CameraRuntime:
    """延迟绑定一次，不打开硬件；局部服务通过构造参数注入 / Bind once without opening hardware."""
    global _runtime
    if _runtime is None:
        with _binding_lock:
            if _runtime is None:
                from ogscope.platform.adapters.camera_runtime import (
                    build_camera_runtime,
                )

                _runtime = build_camera_runtime()
    return _runtime


def get_camera_capture() -> CameraCapture:
    """控制、分析、预览及生命周期共用同一采集端口 / Share capture across all runtime consumers."""
    return get_camera_runtime().capture


def get_camera_control() -> CameraControl:
    """兼容入口与领域共用同一控制实现 / Share controls across compatibility and domain callers."""
    return get_camera_runtime().control


_shutdown_task: asyncio.Task | None = None
_shutdown_children: set[asyncio.Task] = set()


async def shutdown_camera_runtime() -> None:
    """统一终止已绑定实例，不为退出创建硬件 / Close the bound runtime without constructing hardware on exit."""
    global _shutdown_task
    if _runtime is None:
        return
    if _shutdown_task is None:
        runtime = _runtime
        runtime.capture.begin_shutdown()

        async def close() -> None:
            from ogscope.core.realtime import realtime_solve_service

            errors: list[BaseException] = []
            # 每个阶段独立收尾，前一阶段失败也必须关闭相机 / Always attempt camera cleanup after consumer failures.
            for operation, budget in (
                (lambda: realtime_solve_service.stop(force=True), 4.0),
                (runtime.control.shutdown, 3.5),
                (runtime.capture.shutdown, 8.5),
            ):
                task = asyncio.create_task(operation())
                _shutdown_children.add(task)

                def finished(done: asyncio.Task) -> None:
                    _shutdown_children.discard(done)
                    if not done.cancelled():
                        done.exception()

                task.add_done_callback(finished)
                done, _ = await asyncio.wait({task}, timeout=budget)
                if not done:
                    task.cancel()
                    errors.append(
                        TimeoutError("关闭阶段超时 / Shutdown stage timed out")
                    )
                elif task.cancelled():
                    errors.append(
                        RuntimeError("关闭阶段被取消 / Shutdown stage cancelled")
                    )
                else:
                    error = task.exception()
                    if error is not None:
                        errors.append(error)
            if errors:
                raise RuntimeError(
                    "相机运行服务未完全关闭 / Camera runtime shutdown incomplete: "
                    + "; ".join(str(exc) or type(exc).__name__ for exc in errors)
                )

        _shutdown_task = asyncio.create_task(close())
        _shutdown_task.add_done_callback(
            lambda task: None if task.cancelled() else task.exception()
        )
    await asyncio.shield(_shutdown_task)
