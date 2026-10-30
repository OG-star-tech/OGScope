"""共享相机控制实现，不依赖 Web 调试服务 / Shared camera controls independent of Web debug services."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from ogscope.domain.camera.runtime import CameraCapture, SharedFrame


def i18n_payload(
    message_key: str, message: str, message_params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """保留现有响应消息字段 / Preserve existing response message fields."""
    payload: dict[str, Any] = {
        "message_key": message_key,
        "message": message,
    }
    if message_params:
        payload["message_params"] = message_params
    return payload


class CameraControlService:
    """单个采集端口的共享控制行为 / Shared control behavior for one capture port.

    保留旧事务、超时与恢复顺序；焦点快照和录像状态随实例隔离。
    Preserve transactions, budgets and recovery order; isolate focus/recording state per instance.
    """

    def __init__(
        self, capture: CameraCapture, *, analysis_running: Callable[[], bool]
    ) -> None:
        self.capture = capture
        self._analysis_running = analysis_running
        self.recording = False
        self.recording_task: asyncio.Task | None = None
        self._recording_lock = asyncio.Lock()
        self._focus_snapshot: dict[str, Any] | None = None
        self._focus_lock: asyncio.Lock | None = None

    @property
    def recording_state_lock(self) -> asyncio.Lock:
        """录像任务和控制状态使用同一实例锁 / One instance lock protects recording task and controls."""
        return self._recording_lock

    async def finish_recording_task(self) -> None:
        """锁内结束录像，保留原有优雅退出预算 / Finish recording under the lock with existing grace budgets."""
        self.recording = False
        task = self.recording_task
        if task is None:
            return
        try:
            done, _ = await asyncio.wait({task}, timeout=2.0)
        except asyncio.CancelledError:
            # 保留旧停止语义：请求取消仍完成录像清理 / Preserve stop semantics: finish recording cleanup after request cancellation.
            done = set()
        if not done:
            task.cancel()
            done, _ = await asyncio.wait({task}, timeout=1.0)
        if not done:
            raise RuntimeError("录像任务未退出 / Recording task did not stop")
        self.recording_task = None
        if not task.cancelled():
            task.result()

    async def shutdown(self) -> None:
        """退出时释放录像任务与占用；媒体元数据仍由 Dev 管理 / Release recording on exit; Dev retains media metadata."""
        async with self.recording_state_lock:
            active = self.recording or self.recording_task is not None
            try:
                await self.finish_recording_task()
            finally:
                if active:
                    await self.capture.release_recording_consumer()

    def get_camera_instance(self) -> Any:
        """只读取共享句柄，不启动硬件 / Read the shared handle without starting hardware."""
        return self.capture.get_camera_instance()

    def _attach_camera_if_needed(self, camera: Any) -> None:
        """保留既有兼容句柄绑定 / Preserve existing compatible-handle attachment."""
        if camera is not None and self.capture.get_camera_instance() is None:
            self.capture.attach_camera_instance(camera)

    def _focus_state_lock(self) -> asyncio.Lock:
        """按实例延迟创建调焦锁 / Lazily create a per-instance focus lock."""
        if self._focus_lock is None:
            self._focus_lock = asyncio.Lock()
        return self._focus_lock

    async def get_preview_frame(
        self, since_frame_id: int | None = None
    ) -> tuple[int, SharedFrame | None]:
        """返回共享帧；HTTP 表示留在调用方 / Return a shared frame, leaving HTTP to callers."""
        return await self.capture.get_preview_frame(since_frame_id)

    async def get_camera_status(self) -> dict[str, Any]:
        """读取共享相机状态 / Read shared camera status"""
        camera = await asyncio.to_thread(self.get_camera_instance)
        self._attach_camera_if_needed(camera)
        status = await self.capture.status()
        if not status.get("connected"):
            return {
                "connected": False,
                "streaming": False,
                "recording": self.recording,
                "error": status.get("error") or "相机未初始化",
                "configured_backend": status.get("configured_backend"),
                "lifecycle": self.capture.lifecycle_status(),
            }
        return {
            "lifecycle": self.capture.lifecycle_status(),
            "connected": bool(status.get("connected")),
            "streaming": bool(status.get("streaming")),
            "recording": self.recording,
            "info": status.get("info", {}),
            "configured_backend": status.get("configured_backend"),
            "runtime_overrides": status.get("runtime_overrides", {}),
        }

    async def get_runtime_overrides(self) -> dict[str, Any]:
        """获取运行时预览覆盖参数 / Get runtime preview overrides."""
        manager = self.capture
        return {"runtime_overrides": manager.get_runtime_overrides()}

    async def clear_runtime_overrides(self) -> dict[str, Any]:
        """清空运行时预览覆盖参数 / Clear runtime preview overrides."""
        manager = self.capture
        manager.clear_runtime_overrides()
        return {
            "success": True,
            **i18n_payload(
                "server.runtimeOverridesCleared",
                "运行时预览参数已清空",
            ),
        }

    async def start_camera(self) -> dict[str, Any]:
        """启动共享相机 / Start the shared camera"""
        camera = await asyncio.to_thread(self.get_camera_instance)
        self._attach_camera_if_needed(camera)
        await self.capture.ensure_started()
        return {"success": True, **i18n_payload("server.cameraStarted", "相机启动成功")}

    async def ensure_camera_streaming(self) -> None:
        """确保相机已采集并刷新预览（分析台与 /api/camera 共用单例，避免重复打开设备）/ Ensure capture + preview; shared singleton for lab and /api/camera."""
        camera = await asyncio.to_thread(self.get_camera_instance)
        self._attach_camera_if_needed(camera)
        await self.capture.ensure_started()

    async def stop_camera(self) -> dict[str, Any]:
        """停止共享相机 / Stop the shared camera"""
        camera = await asyncio.to_thread(self.get_camera_instance)
        self._attach_camera_if_needed(camera)
        if self._focus_snapshot is not None:
            await self.stop_focus_session()
        manager = self.capture
        ownership = manager.lifecycle_status()

        if (
            self._analysis_running()
            or ownership["analysis_consumers"]
            or ownership["operation_consumers"]
            or ownership["recording_consumers"]
        ):
            return {
                "success": False,
                "message": "Camera is in use; stop its task first / 相机正在使用，请先停止分析、校准或录像任务",
            }
        try:
            await manager.stop()
        except RuntimeError as exc:
            return {"success": False, "message": str(exc)}
        return {"success": True, **i18n_payload("server.cameraStopped", "相机停止成功")}

    async def get_stream_frame_bytes(
        self,
        image_format: str = "jpeg",
        quality: int = 75,
        *,
        since_frame_id: int | None = None,
    ) -> tuple[int, bytes | None, int]:
        """读取共享流帧并编码 / Read shared frame and encode.

        返回 (code, data, snap_frame_id)。snap_frame_id 供 MJPEG 循环写入 since_frame_id，
        在共享缓存未前进时返回 304 以避免 PNG/自定义质量下的疯狂同步抓帧。
        Returns (code, data, snap_frame_id). snap_frame_id is fed back as since_frame_id for
        the MJPEG loop; returns 304 when the shared cache has not advanced to avoid sync grabs.
        """
        manager = self.capture
        await manager.ensure_started()
        snap = await manager.get_cached_frame_snapshot()
        if snap is None:
            return 503, None, 0

        fmt = image_format.lower()
        q = int(max(10, min(100, int(quality))))
        if since_frame_id is not None and since_frame_id == snap.frame_id:
            return 304, None, snap.frame_id

        if fmt == "jpeg":
            # 质量变体仍来自同一共享帧，不因客户端质量不同额外抓 RAW。
            # Quality variants use the same shared frame, never an extra camera read.
            encoded = await manager.get_stream_jpeg(snap, q)
            return (200 if encoded is not None else 500), encoded, snap.frame_id

        raw, _fid, _ts = await manager.get_raw_frame()
        encoded = await manager.encode_image(raw, image_format, q)
        if encoded is None:
            return 500, None, snap.frame_id
        snap2 = await manager.get_cached_frame_snapshot()
        sid = int(snap2.frame_id) if snap2 is not None else int(snap.frame_id)
        return 200, encoded, sid

    async def set_rotation(self, rotation: int) -> dict[str, Any]:
        """设置图像旋转角度 / Set image rotation angle"""
        camera = self.get_camera_instance()
        if not camera:
            raise Exception("相机未初始化")

        if camera.set_rotation(rotation):
            self.capture.update_runtime_overrides({"rotation": int(rotation)})
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

    async def set_mirror(
        self, flip_horizontal: bool, flip_vertical: bool
    ) -> dict[str, Any]:
        """设置水平/垂直镜像（采集管线内，与解算一致）/ Set mirror in capture pipeline."""
        camera = self.get_camera_instance()
        if not camera:
            raise Exception("相机未初始化")
        if not hasattr(camera, "set_flip"):
            raise Exception("相机不支持镜像设置")
        fh = bool(flip_horizontal)
        fv = bool(flip_vertical)
        if camera.set_flip(fh, fv):
            self.capture.update_runtime_overrides(
                {"flip_horizontal": fh, "flip_vertical": fv}
            )
            return {
                "success": True,
                "flip_horizontal": fh,
                "flip_vertical": fv,
                **i18n_payload(
                    "server.mirrorSet",
                    f"镜像: 水平={'开' if fh else '关'}, 垂直={'开' if fv else '关'}",
                    {"flip_horizontal": fh, "flip_vertical": fv},
                ),
            }
        raise Exception("设置镜像失败")

    async def set_size(self, width: int, height: int) -> dict[str, Any]:
        """仅切换分辨率（宽高），不影响当前帧率；必要时重启预览抓取 / Only switches the resolution (width and height) without affecting the current frame rate; restart preview capture if necessary"""
        camera = self.get_camera_instance()
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
            success = await self.capture.reconfigure_camera(
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

        self.capture.update_runtime_overrides(
            {"width": int(width), "height": int(height)}
        )
        return {
            "success": True,
            "info": info,
            **i18n_payload("server.resolutionUpdated", "分辨率已更新"),
        }

    async def set_sampling_mode(self, mode: str) -> dict[str, Any]:
        """切换采样模式 / Switch sampling mode (supersample | native | crop)."""
        camera = self.get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        # 验证输入参数 / Validate input parameters
        if mode not in ["supersample", "native", "crop"]:
            raise Exception(f"不支持的采样模式: {mode}")

        try:
            ok = await self.capture.reconfigure_camera(
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

        self.capture.update_runtime_overrides({"sampling_mode": mode})
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

    async def set_fps(self, fps: int) -> dict[str, Any]:
        """仅设置帧率，尽量不影响当前预览 / Only set the frame rate and try not to affect the current preview"""
        camera = self.get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        # 验证输入参数 / Validate input parameters
        if fps <= 0 or fps > 60:
            raise Exception(f"帧率参数无效: {fps} (应在1-60之间)")

        try:
            ok = False
            if hasattr(camera, "set_fps"):
                ok = await self.capture.reconfigure_camera(
                    "set_fps",
                    lambda: camera.set_fps(int(fps)),
                    timeout_sec=10.0,
                )
            else:
                info = camera.get_camera_info()
                ok = await self.capture.reconfigure_camera(
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
                        ok = await self.capture.reconfigure_camera(
                            "retry_set_fps",
                            lambda: camera.set_fps(int(fps)),
                            timeout_sec=10.0,
                        )
                    else:
                        ok = await self.capture.reconfigure_camera(
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

            self.capture.update_runtime_overrides({"fps": int(fps)})
            return {
                "success": True,
                "info": info,
                **i18n_payload(
                    "server.fpsSet", f"帧率设置为 {int(fps)}", {"fps": int(fps)}
                ),
            }
        except Exception as e:
            raise Exception(f"设置帧率失败: {str(e)}")

    async def set_auto_exposure_mode(self, enabled: bool) -> dict[str, Any]:
        """仅切换自动曝光模式 / Toggle auto-exposure mode only"""
        camera = self.get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        if not hasattr(camera, "set_auto_exposure"):
            raise Exception("当前相机不支持自动曝光切换")

        applied = await self.capture.reconfigure_camera(
            "set_auto_exposure",
            lambda: camera.set_auto_exposure(bool(enabled)),
            timeout_sec=10.0,
        )
        if not applied:
            raise Exception("设置自动曝光模式失败")

        self.capture.update_runtime_overrides({"auto_exposure": bool(enabled)})
        return {
            "success": True,
            **i18n_payload("server.autoExposureUpdated", "曝光模式已更新"),
            "auto_exposure": bool(enabled),
        }

    async def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """更新共享相机设置 / Update shared camera settings"""
        camera = self.get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        try:
            # 整组设置在同一个相机事务中执行，避免与 capture_request 并发访问 libcamera。
            # Apply the full settings batch in one camera transaction to avoid racing capture_request.
            def _apply_settings_sync() -> bool:
                auto_exposure = settings.get(
                    "autoExposure", getattr(camera, "auto_exposure", False)
                )
                if "autoExposure" in settings:
                    if not hasattr(camera, "set_auto_exposure"):
                        raise Exception("当前相机驱动不支持自动曝光")
                    if not camera.set_auto_exposure(bool(auto_exposure)):
                        raise Exception("设置自动曝光模式失败")

                if not auto_exposure and "exposure" in settings:
                    camera.set_exposure(settings["exposure"])

                if (
                    not auto_exposure
                    and "gain" in settings
                    and "digitalGain" in settings
                ):
                    camera.set_gain(settings["gain"], settings.get("digitalGain", 1.0))
                elif not auto_exposure and "gain" in settings:
                    camera.set_gain(settings["gain"])

                if any(
                    key in settings
                    for key in ["contrast", "brightness", "saturation", "sharpness"]
                ) and hasattr(camera, "set_image_enhancement"):
                    camera.set_image_enhancement(
                        settings.get("contrast", 1.0),
                        settings.get("brightness", 0.0),
                        settings.get("saturation", 1.0),
                        settings.get("sharpness", 1.0),
                    )

                if "noiseReductionMode" in settings and hasattr(
                    camera, "set_noise_reduction_mode"
                ):
                    camera.set_noise_reduction_mode(settings["noiseReductionMode"])
                elif "noiseReduction" in settings and hasattr(
                    camera, "set_noise_reduction"
                ):
                    camera.set_noise_reduction(settings["noiseReduction"])

                if "aeFlickerMode" in settings and hasattr(
                    camera, "set_ae_flicker_mode"
                ):
                    camera.set_ae_flicker_mode(settings["aeFlickerMode"])
                if (
                    "autoExposureMaxUs" in settings
                    and settings["autoExposureMaxUs"]
                    and hasattr(camera, "set_auto_exposure_max_us")
                ):
                    camera.set_auto_exposure_max_us(settings["autoExposureMaxUs"])

                if "whiteBalanceMode" in settings and hasattr(
                    camera, "set_white_balance"
                ):
                    camera.set_white_balance(
                        settings["whiteBalanceMode"],
                        settings.get("whiteBalanceGainR", 1.0),
                        settings.get("whiteBalanceGainB", 1.0),
                    )

                if "colorMode" in settings and hasattr(camera, "set_color_mode"):
                    camera.set_color_mode(settings["colorMode"])
                return True

            logging.getLogger(__name__).info(
                "camera_settings_apply fields=%s", ",".join(sorted(settings))
            )
            await self.capture.reconfigure_camera(
                "update_settings", _apply_settings_sync, timeout_sec=10.0
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
            if "noiseReductionMode" in settings:
                overrides["noise_reduction_mode"] = settings["noiseReductionMode"]
            elif "noiseReduction" in settings:
                # 兼容旧控制台数值降噪 / Compat numeric NR control from legacy console.
                level = int(settings.get("noiseReduction") or 0)
                overrides["noise_reduction_mode"] = (
                    "off" if level <= 0 else "fast" if level <= 2 else "high_quality"
                )
            if "aeFlickerMode" in settings:
                overrides["ae_flicker_mode"] = settings["aeFlickerMode"]
            if "autoExposureMaxUs" in settings:
                overrides["auto_exposure_max_us"] = settings["autoExposureMaxUs"]
            if "colorMode" in settings:
                overrides["color_mode"] = settings["colorMode"]
            if "whiteBalanceMode" in settings:
                overrides["white_balance_mode"] = settings["whiteBalanceMode"]
                overrides["white_balance_gain_r"] = settings.get(
                    "whiteBalanceGainR", 1.0
                )
                overrides["white_balance_gain_b"] = settings.get(
                    "whiteBalanceGainB", 1.0
                )
            if overrides:
                self.capture.update_runtime_overrides(overrides)

            return {
                "success": True,
                **i18n_payload("server.cameraSettingsUpdated", "相机设置已更新"),
                "settings": settings,
            }
        except Exception as e:
            raise Exception(f"更新设置失败: {str(e)}")

    async def start_focus_session(self) -> dict[str, Any]:
        """锁定曝光/增益并关闭降噪，保存可恢复快照 / Lock imaging controls with a restorable snapshot."""
        async with self._focus_state_lock():
            if self._focus_snapshot is not None:
                return {
                    "success": True,
                    "active": True,
                    "already_active": True,
                    "locked": self._focus_snapshot["locked"],
                }

            camera = self.get_camera_instance()
            if not camera or not camera.is_initialized:
                raise Exception("相机未初始化")
            info = (
                camera.get_camera_info() if hasattr(camera, "get_camera_info") else {}
            )
            snapshot_settings: dict[str, Any] = {
                "autoExposure": bool(getattr(camera, "auto_exposure", False)),
                "exposure": int(getattr(camera, "exposure_us", 10_000)),
                "gain": float(getattr(camera, "analogue_gain", 1.0)),
                "digitalGain": float(getattr(camera, "digital_gain", 1.0)),
                "noiseReductionMode": str(
                    getattr(camera, "noise_reduction_mode", "fast")
                ),
            }
            locked = {
                "autoExposure": False,
                "exposure": max(
                    1,
                    int(
                        info.get("actual_exposure_us") or snapshot_settings["exposure"]
                    ),
                ),
                "gain": max(
                    0.1,
                    float(
                        info.get("actual_analogue_gain") or snapshot_settings["gain"]
                    ),
                ),
                "digitalGain": max(
                    0.1,
                    float(
                        info.get("actual_digital_gain")
                        or snapshot_settings["digitalGain"]
                    ),
                ),
                "noiseReductionMode": "off",
            }
            runtime_overrides = self.capture.get_runtime_overrides()
            await self.update_settings(locked)
            self._focus_snapshot = {
                "settings": snapshot_settings,
                "runtime_overrides": runtime_overrides,
                "locked": locked,
            }
            return {
                "success": True,
                "active": True,
                "already_active": False,
                "locked": locked,
            }

    async def stop_focus_session(self) -> dict[str, Any]:
        """恢复焦点会话前的相机参数 / Restore camera controls from before focus mode."""
        async with self._focus_state_lock():
            snapshot = self._focus_snapshot
            if snapshot is None:
                return {"success": True, "active": False, "restored": False}

            camera = self.get_camera_instance()
            restored = bool(camera and camera.is_initialized)
            if restored:
                restore_settings = snapshot["settings"]
                if restore_settings["autoExposure"]:
                    # 先恢复手动基线，再重新开启 AE；否则批量设置会按 AE 语义跳过曝光/增益。
                    # Restore the manual baseline before re-enabling AE; AE batches skip exposure/gain.
                    await self.update_settings(
                        {**restore_settings, "autoExposure": False}
                    )
                    await self.update_settings({"autoExposure": True})
                else:
                    await self.update_settings(restore_settings)
            manager = self.capture
            manager.clear_runtime_overrides()
            manager.update_runtime_overrides(snapshot["runtime_overrides"])
            self._focus_snapshot = None
            return {
                "success": True,
                "active": False,
                "restored": restored,
                "restored_settings": snapshot["settings"],
            }

    async def set_white_balance(
        self, mode: str, gain_r: float = 1.0, gain_b: float = 1.0
    ) -> dict[str, Any]:
        """设置白平衡 / Set white balance"""
        camera = self.get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        if camera.set_white_balance(mode, gain_r, gain_b):
            self.capture.update_runtime_overrides(
                {
                    "white_balance_mode": mode,
                    "white_balance_gain_r": float(gain_r),
                    "white_balance_gain_b": float(gain_b),
                }
            )
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

    async def set_color_mode(self, color_mode: str) -> dict[str, Any]:
        """设置颜色模式 / Set color mode"""
        camera = self.get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")

        if color_mode not in ["color", "mono"]:
            raise Exception("不支持的颜色模式，只支持 'color' 或 'mono'")

        try:
            if hasattr(camera, "set_color_mode"):
                success = await self.capture.reconfigure_camera(
                    "set_color_mode",
                    lambda: camera.set_color_mode(color_mode),
                    timeout_sec=10.0,
                )
                if success:
                    self.capture.update_runtime_overrides({"color_mode": color_mode})
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
