"""
调试控制台服务层
"""

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ogscope.web.camera_shared import get_camera_manager

# 调试控制台相关 / Debug console related
DEBUG_CAPTURES_DIR = Path.home() / "dev_captures"
DEBUG_CAPTURES_DIR.mkdir(exist_ok=True)

# 全局变量存储相机状态 / Global variables store camera status
camera_instance = None
is_recording = False
recording_task = None
recording_state_lock: Optional[asyncio.Lock] = None
# 录制会话元数据（用于停止时写入侧车） / Recording session metadata (for sidecar on stop)
recording_stem: Optional[str] = None
recording_t0_mono: Optional[float] = None
recording_fps_value: float = 15.0
recording_media_filename: Optional[str] = None
recording_codec_fourcc: str = "MJPG"
recording_container: str = "AVI"

# 预览帧缓存与抓取任务 / Preview frame buffering and grabbing tasks
latest_preview_jpeg: Optional[bytes] = None
last_preview_time: Optional[float] = None
latest_preview_id: int = 0
preview_grabber_task = None
PREVIEW_JPEG_QUALITY = int(os.getenv("OGSCOPE_PREVIEW_JPEG_QUALITY", "75"))
PREVIEW_PIPELINE_WORKERS = 2

_CAMERA_ENV_KEY_MAP = {
    "width": "OGSCOPE_CAMERA_WIDTH",
    "height": "OGSCOPE_CAMERA_HEIGHT",
    "fps": "OGSCOPE_CAMERA_FPS",
    "sampling_mode": "OGSCOPE_CAMERA_SAMPLING_MODE",
    "exposure_us": "OGSCOPE_CAMERA_EXPOSURE",
    "analogue_gain": "OGSCOPE_CAMERA_GAIN",
}

# 串行化 ensure/start，避免并发 to_thread 竞争；与阻塞相机调用分离出事件循环
# Serialize ensure/start; offload blocking camera calls from asyncio event loop.
_camera_ensure_lock = asyncio.Lock()


def _get_recording_state_lock() -> asyncio.Lock:
    """懒加载录制状态锁 / Lazy-init lock for recording state."""
    global recording_state_lock
    if recording_state_lock is None:
        recording_state_lock = asyncio.Lock()
    return recording_state_lock


def is_recording_active() -> bool:
    """是否正在录制 / Whether recording is active."""
    return bool(is_recording)


def i18n_payload(
    message_key: str, message: str, message_params: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message_key": message_key,
        "message": message,
    }
    if message_params:
        payload["message_params"] = message_params
    return payload


def _persist_env_updates(updates: dict[str, Any]) -> Path:
    """将键值写入项目 .env（存在则覆盖，不存在则追加）/ Persist key-values into project .env."""
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    pending = {str(k): str(v) for k, v in updates.items()}
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _, _ = line.partition("=")
        key = key.strip()
        if key in pending:
            new_lines.append(f"{key}={pending.pop(key)}")
        else:
            new_lines.append(line)
    for key, value in pending.items():
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return env_path


def get_camera_instance():
    """获取相机实例 / Get camera instance"""
    manager = get_camera_manager()
    return manager.get_camera_instance()


def _attach_manager_camera_if_needed(camera: Any) -> None:
    """将兼容层返回的相机实例挂到共享管理器（测试与旧代码兼容）/ Attach compat camera to shared manager."""
    manager = get_camera_manager()
    if camera is not None and manager.get_camera_instance() is None:
        manager.attach_camera_instance(camera)


def _capture_timestamp_for_stem() -> str:
    """生成带毫秒的时间戳，降低同秒碰撞 / Timestamp with milliseconds to reduce same-second collisions"""
    dt = datetime.now()
    return dt.strftime("%Y%m%d_%H%M%S") + f"_{dt.microsecond // 1000:03d}"


def _to_json_safe(value: Any) -> Any:
    """将嵌套结构转为可 JSON 序列化的类型 / Convert nested structures to JSON-serializable types"""
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_param_slug(camera_info: dict[str, Any]) -> str:
    """从相机信息生成简短、文件名安全的参数片段 / Short filesystem-safe param slug from camera info"""
    if not camera_info:
        return ""
    parts: list[str] = []
    exp = camera_info.get("exposure_us")
    if exp is not None:
        try:
            parts.append(f"e{int(exp)}us")
        except (TypeError, ValueError):
            pass
    ag = camera_info.get("analogue_gain")
    if ag is not None:
        try:
            parts.append(f"ag{float(ag):.1f}".replace(".", "p"))
        except (TypeError, ValueError):
            pass
    dg = camera_info.get("digital_gain")
    if dg is not None:
        try:
            if abs(float(dg) - 1.0) > 0.01:
                parts.append(f"dg{float(dg):.1f}".replace(".", "p"))
        except (TypeError, ValueError):
            pass
    fps = camera_info.get("fps")
    if fps is not None:
        try:
            parts.append(f"{float(fps):g}fps")
        except (TypeError, ValueError):
            pass
    sm = camera_info.get("sampling_mode")
    if sm and str(sm) != "native":
        parts.append(str(sm)[:24])
    ow = camera_info.get("output_width") or camera_info.get("width")
    oh = camera_info.get("output_height") or camera_info.get("height")
    if ow and oh:
        try:
            parts.append(f"{int(ow)}x{int(oh)}")
        except (TypeError, ValueError):
            pass
    slug = "_".join(parts)
    for bad in '<>:"/\\|?*':
        slug = slug.replace(bad, "-")
    return slug[:120]


def generate_capture_stem(prefix: str, camera_info: dict[str, Any]) -> str:
    """生成带参数摘要的文件名主干（无扩展名）/ File stem (no extension) with param summary"""
    ts = _capture_timestamp_for_stem()
    slug = build_param_slug(camera_info)
    if slug:
        return f"{prefix}_{ts}_{slug}"
    return f"{prefix}_{ts}"


def save_capture_sidecar(
    stem: str,
    camera_params: dict[str, Any],
    *,
    kind: str,
    media_filename: str,
    file_size: int,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """将完整拍摄/录制参数写入同名 .txt 侧车 / Write full capture params to sidecar .txt file"""
    info_file = DEBUG_CAPTURES_DIR / f"{stem}.txt"
    payload: dict[str, Any] = {
        "kind": kind,
        "media_file": media_filename,
        "sidecar_version": 2,
        "created_at": datetime.now().isoformat(),
        "file_size_bytes": file_size,
        "camera": _to_json_safe(camera_params),
    }
    if extra:
        payload["extra"] = _to_json_safe(extra)
    with open(info_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


class DebugCameraService:
    """调试相机服务 / Debug camera service"""

    @staticmethod
    def get_camera_instance():
        """提供给路由的获取实例入口（兼容 routes 中的调用） / Obtain instance entry provided for routing (compatible with calls in routes)"""
        return globals()["get_camera_instance"]()

    @staticmethod
    async def get_camera_status():
        """获取调试相机状态 / Get debug camera status"""
        camera = await asyncio.to_thread(get_camera_instance)
        _attach_manager_camera_if_needed(camera)
        status = await get_camera_manager().status()
        if not status.get("connected"):
            return {
                "connected": False,
                "streaming": False,
                "recording": is_recording,
                "error": "相机未初始化",
            }
        return {
            "connected": bool(status.get("connected")),
            "streaming": bool(status.get("streaming")),
            "recording": is_recording,
            "info": status.get("info", {}),
            "runtime_overrides": status.get("runtime_overrides", {}),
        }

    @staticmethod
    async def get_runtime_overrides():
        """获取运行时预览覆盖参数 / Get runtime preview overrides."""
        manager = get_camera_manager()
        return {"runtime_overrides": manager.get_runtime_overrides()}

    @staticmethod
    async def clear_runtime_overrides():
        """清空运行时预览覆盖参数 / Clear runtime preview overrides."""
        manager = get_camera_manager()
        manager.clear_runtime_overrides()
        return {
            "success": True,
            **i18n_payload(
                "server.runtimeOverridesCleared",
                "运行时预览参数已清空",
            ),
        }

    @staticmethod
    async def apply_runtime_overrides_as_defaults():
        """将运行时覆盖参数确认写入系统默认 .env / Persist runtime overrides to .env defaults."""
        manager = get_camera_manager()
        overrides = manager.get_runtime_overrides()
        if not overrides:
            return {
                "success": True,
                "applied": {},
                "skipped": {},
                **i18n_payload(
                    "server.runtimeOverridesEmpty",
                    "当前没有待确认的运行时参数",
                ),
            }
        applied: dict[str, Any] = {}
        skipped: dict[str, Any] = {}
        for key, value in overrides.items():
            env_key = _CAMERA_ENV_KEY_MAP.get(key)
            if env_key:
                applied[env_key] = value
            else:
                skipped[key] = value
        env_path = None
        if applied:
            env_path = _persist_env_updates(applied)
        return {
            "success": True,
            "applied": applied,
            "skipped": skipped,
            "env_path": str(env_path) if env_path else None,
            **i18n_payload(
                "server.runtimeOverridesAppliedAsDefaults",
                "运行时参数已写入系统默认配置",
            ),
        }

    @staticmethod
    async def start_camera():
        """启动调试相机 / Start the debug camera"""
        camera = await asyncio.to_thread(get_camera_instance)
        _attach_manager_camera_if_needed(camera)
        await get_camera_manager().ensure_started()
        return {"success": True, **i18n_payload("server.cameraStarted", "相机启动成功")}

    @staticmethod
    async def ensure_camera_streaming():
        """确保相机已采集并刷新预览（分析台与 /api/camera 共用单例，避免重复打开设备）/ Ensure capture + preview; shared singleton for lab and /api/camera."""
        camera = await asyncio.to_thread(get_camera_instance)
        _attach_manager_camera_if_needed(camera)
        await get_camera_manager().ensure_started()

    @staticmethod
    async def stop_camera():
        """停止调试相机 / Stop debugging camera"""
        camera = await asyncio.to_thread(get_camera_instance)
        _attach_manager_camera_if_needed(camera)
        await get_camera_manager().stop()
        return {"success": True, **i18n_payload("server.cameraStopped", "相机停止成功")}

    @staticmethod
    async def get_preview(since_frame_id: int | None = None):
        """获取调试相机预览 / Get debug camera preview"""
        from fastapi.responses import Response

        manager = get_camera_manager()
        code, frame = await manager.get_preview_frame(since_frame_id)
        if code == 304:
            return Response(status_code=304)
        if code != 200 or frame is None or frame.jpeg_frame is None:
            # 首帧兜底：直接抓一帧并编码，避免前端启动后长时间黑屏
            # First-frame fallback: grab one frame immediately to avoid prolonged black screen.
            raw, frame_id, frame_ts = await manager.get_raw_frame()
            jpeg = await asyncio.to_thread(manager.encode_frame, raw, "jpeg", 75)
            if jpeg is None:
                raise Exception("暂无预览帧")
            return Response(
                content=jpeg,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "X-Frame-Id": str(frame_id),
                    "X-Frame-Ts": str(frame_ts),
                },
            )
        return Response(
            content=frame.jpeg_frame,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "X-Frame-Id": str(frame.frame_id),
                "X-Frame-Ts": str(frame.timestamp),
                "X-Frame-Width": str(frame.width),
                "X-Frame-Height": str(frame.height),
            },
        )

    @staticmethod
    async def get_stream_frame_bytes(
        image_format: str = "jpeg", quality: int = 75
    ) -> tuple[int, bytes | None, int]:
        """读取共享流帧并编码 / Read shared frame and encode."""
        manager = get_camera_manager()
        await manager.ensure_started()
        snap = await manager.get_cached_frame_snapshot()
        if snap is None or snap.raw_frame is None:
            return 503, None, 0
        if image_format.lower() == "jpeg" and snap.jpeg_frame is not None:
            return 200, snap.jpeg_frame, snap.frame_id
        encoded = await asyncio.to_thread(
            manager.encode_frame, snap.raw_frame, image_format, int(quality)
        )
        if encoded is None:
            return 500, None, snap.frame_id
        return 200, encoded, snap.frame_id

    @staticmethod
    async def capture_image():
        """拍摄单张图片 / Take a single picture"""
        camera = get_camera_instance()
        if not camera or not camera.is_capturing:
            raise Exception("相机未运行")

        try:
            import cv2

            # 捕获图像 / capture image
            image = camera.capture_image()
            if image is None:
                raise Exception("图像捕获失败")

            camera_info = camera.get_camera_info()
            expected_w = int(
                camera_info.get("output_width", camera_info.get("width", 0)) or 0
            )
            expected_h = int(
                camera_info.get("output_height", camera_info.get("height", 0)) or 0
            )
            actual_h, actual_w = image.shape[:2]
            rotation = int(camera_info.get("rotation", 0) or 0)
            if rotation in (90, 270):
                expected_w, expected_h = expected_h, expected_w
            if (
                expected_w > 0
                and expected_h > 0
                and (int(actual_w) != expected_w or int(actual_h) != expected_h)
            ):
                raise Exception(
                    f"拍照分辨率与当前设置不一致: expected={expected_w}x{expected_h}, actual={actual_w}x{actual_h}"
                )

            # 生成文件名（含参数摘要）/ File name with param summary in stem
            stem = generate_capture_stem("IMG", camera_info)
            image_path = DEBUG_CAPTURES_DIR / f"{stem}.jpg"

            # 保存图像 / save image
            success = cv2.imwrite(str(image_path), image)
            if not success:
                raise Exception("图像保存失败")

            # 保存拍摄信息侧车 / Save capture sidecar (.txt)
            file_size = image_path.stat().st_size
            save_capture_sidecar(
                stem,
                camera_info,
                kind="photo",
                media_filename=f"{stem}.jpg",
                file_size=file_size,
                extra={
                    "actual_saved_width": int(actual_w),
                    "actual_saved_height": int(actual_h),
                    "expected_output_width": int(expected_w),
                    "expected_output_height": int(expected_h),
                },
            )

            return {
                "success": True,
                "filename": f"{stem}.jpg",
                "path": str(image_path),
                "size": file_size,
                "actual_saved_width": int(actual_w),
                "actual_saved_height": int(actual_h),
                "expected_output_width": int(expected_w),
                "expected_output_height": int(expected_h),
            }

        except ImportError:
            raise Exception("OpenCV未安装")
        except Exception as e:
            raise Exception(f"拍摄失败: {str(e)}")

    @staticmethod
    async def set_rotation(rotation: int):
        """设置图像旋转角度 / Set image rotation angle"""
        camera = get_camera_instance()
        if not camera:
            raise Exception("相机未初始化")

        if camera.set_rotation(rotation):
            get_camera_manager().update_runtime_overrides({"rotation": int(rotation)})
            return {
                "success": True,
                **i18n_payload(
                    "server.rotationSet",
                    f"旋转角度设置为: {rotation}度",
                    {"rotation": rotation},
                ),
            }
        else:
            raise Exception("设置旋转角度失败")

    @staticmethod
    async def start_recording():
        """开始录制视频 / Start recording video"""
        global is_recording, recording_task, recording_stem, recording_t0_mono, recording_fps_value
        global recording_media_filename, recording_codec_fourcc, recording_container

        async with _get_recording_state_lock():
            if is_recording:
                raise Exception("已在录制中")
            try:
                from ogscope.web.api.analysis.services import analysis_service

                if analysis_service.is_realtime_source_busy("camera"):
                    raise Exception("画面解析进行中，无法开始录制")
            except ImportError:
                pass

            camera = get_camera_instance()
            if not camera or not camera.is_capturing:
                raise Exception("相机未运行")

            try:
                import cv2

                camera_info = camera.get_camera_info()
                stem = generate_capture_stem("VID", camera_info)
                video_path = DEBUG_CAPTURES_DIR / f"{stem}.avi"

                # 优先使用 AVI 友好编码，按候选顺序探测可用编码器 / Prefer AVI-friendly codecs.
                codec_candidates = [
                    ("MJPG", "AVI"),
                    ("XVID", "AVI"),
                    ("DIVX", "AVI"),
                ]
                width = int(
                    camera_info.get("output_width", camera_info.get("width", 1920))
                )
                height = int(
                    camera_info.get("output_height", camera_info.get("height", 1080))
                )
                # 将录制写盘帧率限制在 1-3 FPS，进一步降低开发板负载 / Clamp record-write FPS to 1-3.
                source_fps = float(camera_info.get("fps", 15))
                fps = max(1.0, min(3.0, source_fps))
                recording_fps_value = fps

                video_writer = None
                chosen_codec = None
                chosen_container = None
                for codec_tag, container in codec_candidates:
                    fourcc = cv2.VideoWriter_fourcc(*codec_tag)
                    candidate_writer = cv2.VideoWriter(
                        str(video_path), fourcc, fps, (width, height)
                    )
                    if candidate_writer.isOpened():
                        video_writer = candidate_writer
                        chosen_codec = codec_tag
                        chosen_container = container
                        break
                    candidate_writer.release()

                if video_writer is None or not video_writer.isOpened():
                    raise Exception("视频写入器创建失败（AVI编码器不可用）")

                recording_stem = stem
                recording_t0_mono = time.monotonic()
                recording_media_filename = f"{stem}.avi"
                recording_codec_fourcc = str(chosen_codec or "MJPG")
                recording_container = str(chosen_container or "AVI")
                is_recording = True

                async def record_video():
                    nonlocal video_writer
                    try:
                        while is_recording:
                            image = await asyncio.to_thread(camera.capture_image)
                            if image is not None:
                                try:
                                    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                                except Exception:
                                    bgr = image
                                video_writer.write(bgr)
                            await asyncio.sleep(1 / max(fps, 1))
                    finally:
                        video_writer.release()

                recording_task = asyncio.create_task(record_video())
                return {
                    "success": True,
                    "filename": f"{stem}.avi",
                    "path": str(video_path),
                }
            except ImportError:
                raise Exception("OpenCV未安装")
            except Exception as e:
                raise Exception(f"录制启动失败: {str(e)}")

    @staticmethod
    async def stop_recording():
        """停止录制视频 / Stop recording video"""
        global is_recording, recording_task, recording_stem, recording_t0_mono, recording_fps_value
        global recording_media_filename, recording_codec_fourcc, recording_container

        async with _get_recording_state_lock():
            if not is_recording:
                raise Exception("未在录制中")

            stem = recording_stem
            t0 = recording_t0_mono
            nominal_fps = recording_fps_value
            media_filename = recording_media_filename
            codec_fourcc = recording_codec_fourcc
            container = recording_container

            is_recording = False

            if recording_task:
                try:
                    # 最多等待短时间优雅结束，避免停止录制长时间卡住 / Wait briefly for graceful stop.
                    await asyncio.wait_for(recording_task, timeout=2.0)
                except asyncio.TimeoutError:
                    recording_task.cancel()
                    try:
                        await asyncio.wait_for(recording_task, timeout=1.0)
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logging.getLogger(__name__).warning(
                            "停止录制时等待录制任务取消异常: %s", e
                        )
                except asyncio.CancelledError:
                    pass
                recording_task = None

            if stem:
                media_filename = media_filename or f"{stem}.avi"
                video_path = DEBUG_CAPTURES_DIR / media_filename
                duration_s = 0.0
                if t0 is not None:
                    duration_s = max(0.0, time.monotonic() - t0)
                file_size = int(video_path.stat().st_size) if video_path.exists() else 0
                camera = get_camera_instance()
                camera_info = camera.get_camera_info() if camera else {}
                save_capture_sidecar(
                    stem,
                    camera_info,
                    kind="video",
                    media_filename=media_filename,
                    file_size=file_size,
                    extra={
                        "duration_s": round(duration_s, 3),
                        "nominal_fps": nominal_fps,
                        "codec_fourcc": codec_fourcc,
                        "container": container,
                    },
                )
            recording_stem = None
            recording_t0_mono = None
            recording_media_filename = None
            recording_codec_fourcc = "MJPG"
            recording_container = "AVI"

        return {
            "success": True,
            **i18n_payload("server.recordingStopped", "录制已停止"),
        }

    @staticmethod
    async def set_size(width: int, height: int):
        """仅切换分辨率（宽高），不影响当前帧率；必要时重启预览抓取 / Only switches the resolution (width and height) without affecting the current frame rate; restart preview capture if necessary"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        # 验证输入参数 / Validate input parameters
        if width <= 0 or height <= 0:
            raise Exception("分辨率参数无效")

        # 检查当前分辨率是否相同 / Check if the current resolutions are the same
        info = camera.get_camera_info()
        current_width = info.get("output_width", info.get("width", 0))
        current_height = info.get("output_height", info.get("height", 0))

        if current_width == width and current_height == height:
            return {
                "success": True,
                "info": info,
                **i18n_payload("server.resolutionUnchanged", "分辨率未变化"),
            }

        try:
            success = await get_camera_manager().reconfigure_camera(
                "set_resolution",
                lambda: camera.set_resolution(int(width), int(height)),
                timeout_sec=10.0,
            )
            if not success:
                raise Exception("相机设置分辨率失败")
        except asyncio.TimeoutError:
            raise Exception("设置分辨率超时，请重试")
        except Exception as e:
            raise Exception(f"设置分辨率失败: {str(e)}")

        # 校验是否已生效（以相机报告的尺寸为准） / Verify whether the verification has taken effect (subject to the size reported by the camera)
        info = camera.get_camera_info()
        # 在supersample模式下，检查output_width和output_height / In supersample mode, check output_width and output_height
        if info.get("sampling_mode") == "supersample":
            applied = int(info.get("output_width", 0)) == int(width) and int(
                info.get("output_height", 0)
            ) == int(height)
        else:
            applied = int(info.get("width", 0)) == int(width) and int(
                info.get("height", 0)
            ) == int(height)

        if not applied:
            # 如果设置未生效，记录警告但不抛出异常 / If the setting does not take effect, log a warning but do not throw an exception
            current_res = f"{info.get('width', 0)}x{info.get('height', 0)}"
            if info.get("sampling_mode") == "supersample":
                current_res = (
                    f"{info.get('output_width', 0)}x{info.get('output_height', 0)}"
                )
            logging.getLogger(__name__).warning(
                f"分辨率设置可能未完全生效，当前分辨率: {current_res}"
            )

        get_camera_manager().update_runtime_overrides(
            {"width": int(width), "height": int(height)}
        )
        return {
            "success": True,
            "info": info,
            **i18n_payload("server.resolutionUpdated", "分辨率已更新"),
        }

    @staticmethod
    async def set_sampling_mode(mode: str):
        """切换采样模式（supersample | native | crop）"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        # 验证输入参数 / Validate input parameters
        if mode not in ["supersample", "native", "crop"]:
            raise Exception(f"不支持的采样模式: {mode}")

        try:
            ok = await get_camera_manager().reconfigure_camera(
                "set_sampling_mode",
                lambda: camera.set_sampling_mode(mode),
                timeout_sec=10.0,
            )
            if not ok:
                raise Exception("相机设置采样模式失败")
        except Exception as e:
            raise Exception(f"设置采样模式失败: {str(e)}")

        # 验证设置是否生效 / Verify whether the settings take effect
        info = camera.get_camera_info()
        current_mode = info.get("sampling_mode", "unknown")
        requested_mode = mode
        if requested_mode == "supersample" and current_mode == "native":
            # 在高分辨率场景下会自动降级为 native，这是预期行为 / In high-resolution scenarios, it is expected to automatically downgrade to native.
            pass
        elif current_mode != requested_mode:
            raise Exception(f"采样模式设置未生效，当前模式: {current_mode}")

        get_camera_manager().update_runtime_overrides({"sampling_mode": mode})
        return {
            "success": True,
            "info": info,
            "requested_mode": requested_mode,
            "effective_mode": current_mode,
            **i18n_payload(
                "server.samplingModeSet",
                f"采样模式请求为 {requested_mode}，实际生效为 {current_mode}",
                {"requested_mode": requested_mode, "effective_mode": current_mode},
            ),
        }

    @staticmethod
    async def set_fps(fps: int):
        """仅设置帧率，尽量不影响当前预览 / Only set the frame rate and try not to affect the current preview"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        # 验证输入参数 / Validate input parameters
        if fps <= 0 or fps > 60:
            raise Exception(f"帧率参数无效: {fps} (应在1-60之间)")

        try:
            ok = False
            if hasattr(camera, "set_fps"):
                ok = await get_camera_manager().reconfigure_camera(
                    "set_fps",
                    lambda: camera.set_fps(int(fps)),
                    timeout_sec=10.0,
                )
            else:
                info = camera.get_camera_info()
                ok = await get_camera_manager().reconfigure_camera(
                    "set_fps_by_set_resolution",
                    lambda: camera.set_resolution(
                        info.get("width", 640), info.get("height", 360), int(fps)
                    ),
                    timeout_sec=10.0,
                )

            if not ok:
                raise Exception("相机设置帧率失败")

            # 验证设置是否生效 / Verify whether the settings take effect
            info = camera.get_camera_info()
            current_fps = info.get("fps", 0)
            if current_fps != int(fps):
                # 如果设置未生效，尝试重新设置一次 / If the setting does not take effect, try setting it again
                try:
                    if hasattr(camera, "set_fps"):
                        ok = await get_camera_manager().reconfigure_camera(
                            "retry_set_fps",
                            lambda: camera.set_fps(int(fps)),
                            timeout_sec=10.0,
                        )
                    else:
                        ok = await get_camera_manager().reconfigure_camera(
                            "retry_set_fps_by_set_resolution",
                            lambda: camera.set_resolution(
                                info.get("width", 640),
                                info.get("height", 360),
                                int(fps),
                            ),
                            timeout_sec=10.0,
                        )
                    if ok:
                        info = camera.get_camera_info()
                        current_fps = info.get("fps", 0)
                except Exception:
                    pass

                if current_fps != int(fps):
                    raise Exception(f"帧率设置未生效，当前帧率: {current_fps}")

            get_camera_manager().update_runtime_overrides({"fps": int(fps)})
            return {
                "success": True,
                "info": info,
                **i18n_payload(
                    "server.fpsSet", f"帧率设置为 {int(fps)}", {"fps": int(fps)}
                ),
            }
        except Exception as e:
            raise Exception(f"设置帧率失败: {str(e)}")

    # ==================== 内部：预览抓取器 ==================== / ==================== Internal: Preview Grabber ====================
    @staticmethod
    async def _ensure_preview_grabber():
        await get_camera_manager().resume_grabber()

    @staticmethod
    async def _stop_preview_grabber():
        await get_camera_manager().pause_grabber()

    @staticmethod
    async def _restart_preview_grabber():
        await get_camera_manager().pause_grabber()
        await get_camera_manager().resume_grabber()

    @staticmethod
    def _capture_preview_frame(camera):
        """抓取预览帧（线程池执行） / Capture preview frame (run in thread pool)"""
        try:
            return camera.get_video_frame()
        except Exception:
            return None

    @staticmethod
    def _encode_preview_jpeg(image, quality: int) -> Optional[bytes]:
        """编码 JPEG（线程池执行） / Encode JPEG (run in thread pool)"""
        try:
            import cv2

            ok, buf = cv2.imencode(
                ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
            )
            if not ok:
                return None
            return buf.tobytes()
        except Exception:
            return None

    @staticmethod
    async def _preview_grabber_loop():
        """后台抓取最新帧，编码为 JPEG 缓存，降低单次请求阻塞与抖动 / The latest frames are captured in the background and encoded into JPEG cache to reduce single request blocking and jitter."""
        global latest_preview_jpeg, last_preview_time, latest_preview_id
        camera = get_camera_instance()
        if not camera or not camera.is_capturing:
            return
        target_fps = max(1, int(camera.get_camera_info().get("fps", 5)))
        interval = 1.0 / target_fps
        loop = asyncio.get_running_loop()
        # 使用双工人流水线：一个抓帧，一个编码，提升 Zero2W 下实时预览稳定性 / Use a two-worker pipeline: one captures frames and one encodes, improving preview stability on Zero2W.
        executor = ThreadPoolExecutor(
            max_workers=PREVIEW_PIPELINE_WORKERS, thread_name_prefix="preview-pipe"
        )
        try:
            capture_future = loop.run_in_executor(
                executor, DebugCameraService._capture_preview_frame, camera
            )
            while True:
                start = time.time()
                image = await asyncio.wrap_future(capture_future)
                # 先提交下一帧抓取，让抓取与编码并行 / Submit next frame capture first to overlap capture and encoding
                capture_future = loop.run_in_executor(
                    executor, DebugCameraService._capture_preview_frame, camera
                )
                if image is not None:
                    jpeg_bytes = await loop.run_in_executor(
                        executor,
                        DebugCameraService._encode_preview_jpeg,
                        image,
                        PREVIEW_JPEG_QUALITY,
                    )
                    if jpeg_bytes is not None:
                        latest_preview_jpeg = jpeg_bytes
                        last_preview_time = time.time()
                        latest_preview_id += 1
                # 按 fps 节流 / Throttle by fps
                spent = time.time() - start
                await asyncio.sleep(max(0.0, interval - spent))
        except asyncio.CancelledError:
            # 正确处理取消信号 / Correctly handle cancellation signals
            raise
        except Exception as e:
            # 记录其他异常 / Log other exceptions
            logging.getLogger(__name__).error(f"预览抓取器异常: {e}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    async def set_auto_exposure_mode(enabled: bool):
        """仅切换自动曝光模式 / Toggle auto-exposure mode only"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        if not hasattr(camera, "set_auto_exposure"):
            raise Exception("当前相机不支持自动曝光切换")

        if not camera.set_auto_exposure(bool(enabled)):
            raise Exception("设置自动曝光模式失败")

        get_camera_manager().update_runtime_overrides({"auto_exposure": bool(enabled)})
        return {
            "success": True,
            **i18n_payload("server.autoExposureUpdated", "曝光模式已更新"),
            "auto_exposure": bool(enabled),
        }

    @staticmethod
    async def update_settings(settings: dict[str, Any]):
        """更新调试相机设置 / Update debug camera settings"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        try:
            # 优先处理自动曝光开关，避免自动 / Prioritize the automatic exposure switch to avoid automatic
            auto_exposure = settings.get(
                "autoExposure", getattr(camera, "auto_exposure", False)
            )
            if hasattr(camera, "set_auto_exposure"):
                camera.set_auto_exposure(bool(auto_exposure))

            # 更新基础相机参数 / Update basic camera parameters
            if not auto_exposure and "exposure" in settings:
                camera.set_exposure(settings["exposure"])

            if not auto_exposure and "gain" in settings and "digitalGain" in settings:
                camera.set_gain(settings["gain"], settings.get("digitalGain", 1.0))
            elif not auto_exposure and "gain" in settings:
                camera.set_gain(settings["gain"])

            # 更新图像增强参数 / Update image enhancement parameters
            if any(
                key in settings
                for key in ["contrast", "brightness", "saturation", "sharpness"]
            ):
                contrast = settings.get("contrast", 1.0)
                brightness = settings.get("brightness", 0.0)
                saturation = settings.get("saturation", 1.0)
                sharpness = settings.get("sharpness", 1.0)

                if hasattr(camera, "set_image_enhancement"):
                    camera.set_image_enhancement(
                        contrast, brightness, saturation, sharpness
                    )

            # 更新降噪设置 / Update noise reduction settings
            if "noiseReduction" in settings:
                if hasattr(camera, "set_noise_reduction"):
                    camera.set_noise_reduction(settings["noiseReduction"])

            # 更新白平衡设置 / Update white balance settings
            if "whiteBalanceMode" in settings:
                mode = settings["whiteBalanceMode"]
                gain_r = settings.get("whiteBalanceGainR", 1.0)
                gain_b = settings.get("whiteBalanceGainB", 1.0)

                if hasattr(camera, "set_white_balance"):
                    camera.set_white_balance(mode, gain_r, gain_b)

            # 更新颜色模式设置 / Update color mode settings
            if "colorMode" in settings:
                if hasattr(camera, "set_color_mode"):
                    await get_camera_manager().reconfigure_camera(
                        "update_color_mode",
                        lambda: camera.set_color_mode(settings["colorMode"]),
                        timeout_sec=10.0,
                    )

            overrides: dict[str, Any] = {}
            if "exposure" in settings:
                overrides["exposure_us"] = settings["exposure"]
            if "gain" in settings:
                overrides["analogue_gain"] = settings["gain"]
            if "digitalGain" in settings:
                overrides["digital_gain"] = settings["digitalGain"]
            if "autoExposure" in settings:
                overrides["auto_exposure"] = bool(settings["autoExposure"])
            if "colorMode" in settings:
                overrides["color_mode"] = settings["colorMode"]
            if overrides:
                get_camera_manager().update_runtime_overrides(overrides)

            return {
                "success": True,
                **i18n_payload("server.cameraSettingsUpdated", "相机设置已更新"),
                "settings": settings,
            }
        except Exception as e:
            raise Exception(f"更新设置失败: {str(e)}")

    @staticmethod
    async def reset_camera():
        """重置相机到默认设置 / Reset camera to default settings"""
        from ogscope.config import get_settings

        settings = get_settings()
        camera = get_camera_instance()

        if camera and camera.is_initialized:
            camera.set_exposure(settings.camera_exposure)
            camera.set_gain(settings.camera_gain)

        return {
            "success": True,
            **i18n_payload("server.cameraReset", "相机已重置到默认设置"),
        }

    @staticmethod
    async def get_image_quality():
        """获取图像质量指标 / Get image quality metrics"""
        # 仅使用当前已存在实例，不触发懒初始化，避免后台轮询造成反复 acquire 冲突
        # Use existing instance only; avoid lazy init from background polling.
        camera = get_camera_manager().get_camera_instance()
        if camera is None:
            # 测试环境兼容：允许使用 monkeypatch 注入的相机实例
            # Test compatibility: allow monkeypatched injected camera instance.
            try:
                camera = get_camera_instance()
                _attach_manager_camera_if_needed(camera)
            except Exception:
                camera = None
        if not camera or not getattr(camera, "is_initialized", False):
            return {
                "success": False,
                "available": False,
                "quality": {
                    "noise_level": 0.0,
                    "exposure_adequacy": 0.0,
                    "gain_level": 0.0,
                },
                **i18n_payload("server.cameraNotRunning", "相机未运行"),
            }
        quality_metrics = camera.get_image_quality_metrics()
        return {"success": True, "available": True, "quality": quality_metrics}

    @staticmethod
    async def set_noise_reduction(level: int):
        """设置降噪级别 / Set noise reduction level"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        if camera.set_noise_reduction(level):
            return {
                "success": True,
                **i18n_payload(
                    "server.noiseReductionSet",
                    f"降噪级别设置为: {level}",
                    {"level": level},
                ),
            }
        else:
            raise Exception("设置降噪级别失败")

    @staticmethod
    async def set_white_balance(mode: str, gain_r: float = 1.0, gain_b: float = 1.0):
        """设置白平衡 / Set white balance"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        if camera.set_white_balance(mode, gain_r, gain_b):
            return {
                "success": True,
                **i18n_payload(
                    "server.whiteBalanceSet",
                    f"白平衡模式设置为: {mode}",
                    {"mode": mode},
                ),
            }
        else:
            raise Exception("设置白平衡失败")

    @staticmethod
    async def set_image_enhancement(
        contrast: float = 1.0,
        brightness: float = 0.0,
        saturation: float = 1.0,
        sharpness: float = 1.0,
    ):
        """设置图像增强参数 / Set image enhancement parameters"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        if camera.set_image_enhancement(contrast, brightness, saturation, sharpness):
            return {
                "success": True,
                **i18n_payload("server.imageEnhancementSet", "图像增强参数已设置"),
            }
        else:
            raise Exception("设置图像增强参数失败")

    @staticmethod
    async def set_night_mode(enabled: bool):
        """设置夜间模式 / Set night mode"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        if camera.set_night_mode(enabled):
            mode_text = "启用" if enabled else "关闭"
            return {
                "success": True,
                **i18n_payload(
                    "server.nightModeSet",
                    f"夜间模式已{mode_text}",
                    {"state": mode_text},
                ),
            }
        else:
            raise Exception("设置夜间模式失败")

    @staticmethod
    async def apply_night_mode_preset():
        """应用夜间模式预设 / Apply night mode preset"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        try:
            # 夜间模式预设参数 / Night mode preset parameters
            night_preset = {
                "exposure_us": 50000,
                "analogue_gain": 8.0,
                "digital_gain": 2.0,
                "noise_reduction": 2,
                "white_balance_mode": "night",
                "contrast": 1.2,
                "brightness": 0.1,
                "saturation": 0.8,
                "sharpness": 1.1,
                "night_mode": True,
            }

            # 应用预设 / Apply preset
            camera.set_exposure(night_preset["exposure_us"])
            camera.set_gain(night_preset["analogue_gain"], night_preset["digital_gain"])
            camera.set_noise_reduction(night_preset["noise_reduction"])
            camera.set_white_balance(night_preset["white_balance_mode"])
            camera.set_image_enhancement(
                night_preset["contrast"],
                night_preset["brightness"],
                night_preset["saturation"],
                night_preset["sharpness"],
            )
            camera.set_night_mode(night_preset["night_mode"])

            return {
                "success": True,
                "preset": night_preset,
                **i18n_payload("server.nightPresetApplied", "夜间模式预设已应用"),
            }
        except Exception as e:
            raise Exception(f"应用夜间模式预设失败: {str(e)}")

    @staticmethod
    async def save_current_settings_backup():
        """保存当前设置作为备份 / Save current settings as backup"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        try:
            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "settings": camera.get_camera_info(),
            }

            backup_file = DEBUG_CAPTURES_DIR / "settings_backup.json"
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "backup_file": str(backup_file),
                **i18n_payload("server.settingsBackedUp", "当前设置已备份"),
            }
        except Exception as e:
            raise Exception(f"保存设置备份失败: {str(e)}")

    @staticmethod
    async def restore_settings_backup():
        """从备份恢复设置 / Restore settings from backup"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        try:
            backup_file = DEBUG_CAPTURES_DIR / "settings_backup.json"
            if not backup_file.exists():
                raise Exception("未找到设置备份文件")

            with open(backup_file, encoding="utf-8") as f:
                backup_data = json.load(f)

            settings = backup_data.get("settings", {})

            # 恢复设置 / Restore settings
            if "exposure_us" in settings:
                camera.set_exposure(settings["exposure_us"])
            if "analogue_gain" in settings and "digital_gain" in settings:
                camera.set_gain(settings["analogue_gain"], settings["digital_gain"])
            if "noise_reduction" in settings:
                camera.set_noise_reduction(settings["noise_reduction"])
            if "white_balance_mode" in settings:
                camera.set_white_balance(settings["white_balance_mode"])
            if "contrast" in settings and "brightness" in settings:
                camera.set_image_enhancement(
                    settings.get("contrast", 1.0),
                    settings.get("brightness", 0.0),
                    settings.get("saturation", 1.0),
                    settings.get("sharpness", 1.0),
                )
            if "night_mode" in settings:
                camera.set_night_mode(settings["night_mode"])

            return {
                "success": True,
                **i18n_payload("server.settingsRestored", "设置已从备份恢复"),
            }
        except Exception as e:
            raise Exception(f"恢复设置备份失败: {str(e)}")

    @staticmethod
    async def set_color_mode(color_mode: str):
        """设置颜色模式 / Set color mode"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        if color_mode not in ["color", "mono"]:
            raise Exception("不支持的颜色模式，只支持 'color' 或 'mono'")

        try:
            if hasattr(camera, "set_color_mode"):
                success = await get_camera_manager().reconfigure_camera(
                    "set_color_mode",
                    lambda: camera.set_color_mode(color_mode),
                    timeout_sec=10.0,
                )
                if success:
                    get_camera_manager().update_runtime_overrides(
                        {"color_mode": color_mode}
                    )
                    mode_name = "彩色" if color_mode == "color" else "黑白"
                    return {
                        "success": True,
                        **i18n_payload(
                            "server.colorModeSwitched",
                            f"颜色模式已切换为{mode_name}模式",
                            {"mode": mode_name},
                        ),
                        "color_mode": color_mode,
                    }
                else:
                    raise Exception("相机不支持颜色模式切换")
            else:
                raise Exception("相机驱动不支持颜色模式切换")
        except Exception as e:
            raise Exception(f"设置颜色模式失败: {str(e)}")


class DebugPresetService:
    """调试预设服务 / Debug default service"""

    @staticmethod
    async def get_presets():
        """获取相机预设列表 / Get a list of camera presets"""
        presets_file = DEBUG_CAPTURES_DIR / "presets.json"

        if not presets_file.exists():
            return {"presets": []}

        try:
            with open(presets_file, encoding="utf-8") as f:
                data = json.load(f)
            return {"presets": data.get("presets", [])}
        except Exception as e:
            raise Exception(f"读取预设失败: {str(e)}")

    @staticmethod
    async def save_preset(preset_data: dict[str, Any]):
        """保存相机预设 / Save camera presets"""
        presets_file = DEBUG_CAPTURES_DIR / "presets.json"

        # 读取现有预设 / Read existing preset
        presets = []
        if presets_file.exists():
            try:
                with open(presets_file, encoding="utf-8") as f:
                    data = json.load(f)
                    presets = data.get("presets", [])
            except Exception:
                presets = []

        # 检查是否已存在同名预设 / Check if a preset with the same name already exists
        for i, existing_preset in enumerate(presets):
            if existing_preset["name"] == preset_data["name"]:
                presets[i] = preset_data
                break
        else:
            # 检查预设数量限制 / Check preset quantity limits
            if len(presets) >= 10:
                raise Exception("预设数量已达上限(10个)")
            presets.append(preset_data)

        # 保存预设 / save preset
        try:
            with open(presets_file, "w", encoding="utf-8") as f:
                json.dump({"presets": presets}, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                **i18n_payload("server.presetSaved", "预设保存成功"),
            }
        except Exception as e:
            raise Exception(f"保存预设失败: {str(e)}")

    @staticmethod
    async def apply_preset(preset_name: str):
        """应用相机预设 / Apply camera presets"""
        presets_file = DEBUG_CAPTURES_DIR / "presets.json"

        if not presets_file.exists():
            raise Exception("预设文件不存在")

        try:
            with open(presets_file, encoding="utf-8") as f:
                data = json.load(f)
                presets = data.get("presets", [])

            # 查找预设 / Find a preset
            preset = None
            for p in presets:
                if p["name"] == preset_name:
                    preset = p
                    break

            if not preset:
                raise Exception("预设不存在")

            # 应用预设到相机 / Apply preset to camera
            camera = get_camera_instance()
            if camera and camera.is_initialized:
                # 自动曝光优先，避免手动参数与AE冲突 / Automatic exposure priority to avoid conflicts between manual parameters and AE
                auto_exposure = preset.get("auto_exposure", False)
                if hasattr(camera, "set_auto_exposure"):
                    camera.set_auto_exposure(auto_exposure)

                # 基础参数 / Basic parameters
                if not auto_exposure:
                    camera.set_exposure(preset["exposure_us"])
                    camera.set_gain(
                        preset["analogue_gain"], preset.get("digital_gain", 1.0)
                    )

                # 图像增强参数 / Image enhancement parameters
                if any(
                    key in preset
                    for key in ["contrast", "brightness", "saturation", "sharpness"]
                ):
                    contrast = preset.get("contrast", 1.0)
                    brightness = preset.get("brightness", 0.0)
                    saturation = preset.get("saturation", 1.0)
                    sharpness = preset.get("sharpness", 1.0)

                    if hasattr(camera, "set_image_enhancement"):
                        camera.set_image_enhancement(
                            contrast, brightness, saturation, sharpness
                        )

                # 高级参数 / Advanced parameters
                if "noise_reduction" in preset:
                    if hasattr(camera, "set_noise_reduction"):
                        camera.set_noise_reduction(preset["noise_reduction"])

                # 白平衡设置 / White balance settings
                if "white_balance_mode" in preset:
                    mode = preset["white_balance_mode"]
                    gain_r = preset.get("white_balance_gain_r", 1.0)
                    gain_b = preset.get("white_balance_gain_b", 1.0)

                    if hasattr(camera, "set_white_balance"):
                        camera.set_white_balance(mode, gain_r, gain_b)

                # 旋转角度 / rotation angle
                if "rotation" in preset:
                    if hasattr(camera, "set_rotation"):
                        camera.set_rotation(preset["rotation"])

                # 颜色模式 / color mode
                if "color_mode" in preset:
                    if hasattr(camera, "set_color_mode"):
                        camera.set_color_mode(preset["color_mode"])

            return {
                "success": True,
                "preset": preset,
                **i18n_payload(
                    "server.presetApplied",
                    f"预设 '{preset_name}' 已应用",
                    {"name": preset_name},
                ),
            }

        except Exception as e:
            raise Exception(f"应用预设失败: {str(e)}")

    @staticmethod
    async def delete_preset(preset_name: str):
        """删除相机预设 / Delete camera preset"""
        presets_file = DEBUG_CAPTURES_DIR / "presets.json"

        if not presets_file.exists():
            raise Exception("预设文件不存在")

        try:
            with open(presets_file, encoding="utf-8") as f:
                data = json.load(f)
                presets = data.get("presets", [])

            # 删除预设 / Delete preset
            original_count = len(presets)
            presets = [p for p in presets if p["name"] != preset_name]

            if len(presets) == original_count:
                raise Exception("预设不存在")

            # 保存更新后的预设 / Save updated preset
            with open(presets_file, "w", encoding="utf-8") as f:
                json.dump({"presets": presets}, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                **i18n_payload(
                    "server.presetDeleted",
                    f"预设 '{preset_name}' 已删除",
                    {"name": preset_name},
                ),
            }

        except Exception as e:
            raise Exception(f"删除预设失败: {str(e)}")


class DebugFileService:
    """调试文件服务 / Debug file service"""

    @staticmethod
    async def get_files():
        """获取拍摄文件列表 / Get shooting file list"""
        try:
            # 支持的图片格式 / Supported image formats
            image_extensions = {
                ".jpg",
                ".jpeg",
                ".png",
                ".bmp",
                ".tiff",
                ".tif",
                ".webp",
            }
            # 支持的视频格式 / Supported video formats
            video_extensions = {
                ".mp4",
                ".avi",
                ".mov",
                ".mkv",
                ".wmv",
                ".flv",
                ".webm",
                ".m4v",
            }

            files = []
            for file_path in DEBUG_CAPTURES_DIR.iterdir():
                if file_path.is_file():
                    suffix = file_path.suffix.lower()
                    if suffix in image_extensions or suffix in video_extensions:
                        files.append(
                            {
                                "name": file_path.name,
                                "size": file_path.stat().st_size,
                                "modified": datetime.fromtimestamp(
                                    file_path.stat().st_mtime
                                ).isoformat(),
                                "type": (
                                    "image" if suffix in image_extensions else "video"
                                ),
                            }
                        )

            # 按修改时间排序（最新的在前） / Sort by modification time (newest first)
            files.sort(key=lambda x: x["modified"], reverse=True)

            return {"files": files}

        except Exception as e:
            raise Exception(f"获取文件列表失败: {str(e)}")

    @staticmethod
    async def get_file_info(filename: str):
        """获取文件信息 / Get file information"""
        file_path = DEBUG_CAPTURES_DIR / filename
        info_path = DEBUG_CAPTURES_DIR / f"{file_path.stem}.txt"

        if not file_path.exists():
            raise Exception("文件不存在")

        try:
            # 支持的图片格式 / Supported image formats
            image_extensions = {
                ".jpg",
                ".jpeg",
                ".png",
                ".bmp",
                ".tiff",
                ".tif",
                ".webp",
            }
            # 支持的视频格式 / Supported video formats

            suffix = file_path.suffix.lower()
            file_type = "image" if suffix in image_extensions else "video"

            info = {
                "filename": filename,
                "size": file_path.stat().st_size,
                "modified": datetime.fromtimestamp(
                    file_path.stat().st_mtime
                ).isoformat(),
                "type": file_type,
            }

            # 读取拍摄信息；将 camera 内字段展开到顶层以兼容前端详情 / Read sidecar; flatten camera for UI
            if info_path.exists():
                with open(info_path, encoding="utf-8") as f:
                    capture_info = json.load(f)
                    if isinstance(capture_info, dict):
                        cam = capture_info.get("camera")
                        if isinstance(cam, dict):
                            for k in (
                                "exposure_us",
                                "analogue_gain",
                                "digital_gain",
                                "fps",
                                "auto_exposure",
                                "rotation",
                                "sampling_mode",
                                "color_mode",
                                "sensor",
                                "resolution",
                            ):
                                if k not in capture_info and k in cam:
                                    capture_info[k] = cam[k]
                            if capture_info.get("resolution") is None:
                                ow = cam.get("output_width") or cam.get("width")
                                oh = cam.get("output_height") or cam.get("height")
                                if ow and oh:
                                    capture_info["resolution"] = f"{ow}x{oh}"
                        extra = capture_info.get("extra")
                        if isinstance(extra, dict):
                            for k, v in extra.items():
                                if k not in capture_info:
                                    capture_info[k] = v
                    info.update(capture_info)

            return info

        except Exception as e:
            raise Exception(f"获取文件信息失败: {str(e)}")

    @staticmethod
    async def delete_file(filename: str):
        """删除文件 / Delete files"""
        try:
            file_path = DEBUG_CAPTURES_DIR / filename
            info_path = DEBUG_CAPTURES_DIR / f"{file_path.stem}.txt"

            if not file_path.exists():
                raise Exception("文件不存在")

            # 删除主文件 / Delete master file
            file_path.unlink()

            # 删除对应的参数文件（如果存在） / Delete the corresponding parameter file (if it exists)
            if info_path.exists():
                info_path.unlink()

            return i18n_payload(
                "server.fileDeleted",
                f"文件 {filename} 删除成功",
                {"filename": filename},
            )

        except Exception as e:
            raise Exception(f"删除文件失败: {str(e)}")
