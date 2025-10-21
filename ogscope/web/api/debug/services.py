"""
调试控制台服务层
"""
import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# 调试控制台相关
DEBUG_CAPTURES_DIR = Path.home() / "dev_captures"
DEBUG_CAPTURES_DIR.mkdir(exist_ok=True)

# 全局变量存储相机状态
camera_instance = None
is_recording = False
recording_task = None

# 预览帧缓存与抓取任务
latest_preview_jpeg: Optional[bytes] = None
last_preview_time: Optional[float] = None
preview_grabber_task = None


def get_camera_instance():
    """获取相机实例"""
    global camera_instance
    if camera_instance is None:
        from ogscope.hardware.camera import create_camera
        from ogscope.config import get_settings
        
        settings = get_settings()
        config = {
            "type": "imx327_mipi",
            "width": settings.camera_width,
            "height": settings.camera_height,
            "fps": 5,  # 调试控制台默认使用 5fps（用户未指定时）
            "exposure_us": settings.camera_exposure,
            "analogue_gain": settings.camera_gain,
            "rotation": 180,  # 默认180度旋转
            "sampling_mode": "supersample",
        }
        
        camera_instance = create_camera(config)
        if camera_instance and not camera_instance.initialize():
            camera_instance = None
    
    return camera_instance


def generate_filename(prefix: str = "IMG") -> str:
    """生成文件名"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}"


def save_capture_info(filename: str, camera_params: Dict[str, Any], file_size: int):
    """保存拍摄信息到txt文件"""
    info_file = DEBUG_CAPTURES_DIR / f"{filename}.txt"
    
    info_data = {
        "filename": filename,
        "timestamp": datetime.now().isoformat(),
        "exposure_us": camera_params.get("exposure_us", 0),
        "analogue_gain": camera_params.get("analogue_gain", 1.0),
        "digital_gain": camera_params.get("digital_gain", 1.0),
        "resolution": f"{camera_params.get('width', 1920)}x{camera_params.get('height', 1080)}",
        "file_size": file_size,
        "camera_type": camera_params.get("type", "imx327_mipi"),
        "fps": camera_params.get("fps", 15)
    }
    
    with open(info_file, 'w', encoding='utf-8') as f:
        json.dump(info_data, f, indent=2, ensure_ascii=False)


class DebugCameraService:
    """调试相机服务"""
    
    @staticmethod
    def get_camera_instance():
        """提供给路由的获取实例入口（兼容 routes 中的调用）"""
        return globals()["get_camera_instance"]()
    
    @staticmethod
    async def get_camera_status():
        """获取调试相机状态"""
        camera = get_camera_instance()
        if not camera:
            return {
                "connected": False,
                "streaming": False,
                "recording": is_recording,
                "error": "相机未初始化"
            }
        
        return {
            "connected": camera.is_initialized,
            "streaming": camera.is_capturing,
            "recording": is_recording,
            "info": camera.get_camera_info()
        }
    
    @staticmethod
    async def start_camera():
        """启动调试相机"""
        camera = get_camera_instance()
        if not camera:
            raise Exception("相机初始化失败")
        
        if camera.start_capture():
            # 启动后台抓取任务
            await DebugCameraService._ensure_preview_grabber()
            return {"success": True, "message": "相机启动成功"}
        else:
            raise Exception("相机启动失败")
    
    @staticmethod
    async def stop_camera():
        """停止调试相机"""
        camera = get_camera_instance()
        if not camera:
            return {"success": True, "message": "相机未运行"}
        
        if camera.stop_capture():
            await DebugCameraService._stop_preview_grabber()
            return {"success": True, "message": "相机停止成功"}
        else:
            raise Exception("相机停止失败")
    
    @staticmethod
    async def get_preview():
        """获取调试相机预览"""
        camera = get_camera_instance()
        if not camera or not camera.is_capturing:
            raise Exception("相机未运行")
        
        try:
            # 若后台抓取未运行，尝试启动一次
            await DebugCameraService._ensure_preview_grabber()
            
            # 等待最多500ms 以获取缓存帧
            import time
            deadline = time.time() + 0.5
            global latest_preview_jpeg
            while latest_preview_jpeg is None and time.time() < deadline:
                await asyncio.sleep(0.01)
            if latest_preview_jpeg is None:
                raise Exception("暂无预览帧")
            from fastapi.responses import StreamingResponse
            return StreamingResponse(
                iter([latest_preview_jpeg]),
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"}
            )
        except Exception as e:
            raise Exception(f"预览失败: {str(e)}")
    
    @staticmethod
    async def capture_image():
        """拍摄单张图片"""
        camera = get_camera_instance()
        if not camera or not camera.is_capturing:
            raise Exception("相机未运行")
        
        try:
            import cv2
            
            # 捕获图像
            image = camera.capture_image()
            if image is None:
                raise Exception("图像捕获失败")
            
            # 生成文件名
            filename = generate_filename("IMG")
            image_path = DEBUG_CAPTURES_DIR / f"{filename}.jpg"
            
            # 保存图像
            success = cv2.imwrite(str(image_path), image)
            if not success:
                raise Exception("图像保存失败")
            
            # 保存拍摄信息
            camera_info = camera.get_camera_info()
            file_size = image_path.stat().st_size
            save_capture_info(filename, camera_info, file_size)
            
            return {
                "success": True,
                "filename": f"{filename}.jpg",
                "path": str(image_path),
                "size": file_size
            }
            
        except ImportError:
            raise Exception("OpenCV未安装")
        except Exception as e:
            raise Exception(f"拍摄失败: {str(e)}")
    
    @staticmethod
    async def set_rotation(rotation: int):
        """设置图像旋转角度"""
        camera = get_camera_instance()
        if not camera:
            raise Exception("相机未初始化")
        
        if camera.set_rotation(rotation):
            return {"success": True, "message": f"旋转角度设置为: {rotation}度"}
        else:
            raise Exception("设置旋转角度失败")
    
    @staticmethod
    async def start_recording():
        """开始录制视频"""
        global is_recording, recording_task
        
        if is_recording:
            raise Exception("已在录制中")
        
        camera = get_camera_instance()
        if not camera or not camera.is_capturing:
            raise Exception("相机未运行")
        
        try:
            import cv2
            import numpy as np
            
            filename = generate_filename("VID")
            video_path = DEBUG_CAPTURES_DIR / f"{filename}.avi"
            
            # 创建视频写入器（MJPG/AVI 更鲁棒）
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            camera_info = camera.get_camera_info()
            width = camera_info.get('width', 1920)
            height = camera_info.get('height', 1080)
            fps = camera_info.get('fps', 15)
            
            video_writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))
            
            if not video_writer.isOpened():
                raise Exception("视频写入器创建失败")
            
            is_recording = True
            
            # 启动录制任务
            async def record_video():
                nonlocal video_writer
                try:
                    while is_recording:
                        image = camera.capture_image()
                        if image is not None:
                            # OpenCV 期望 BGR
                            try:
                                import cv2
                                bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                            except Exception:
                                bgr = image
                            video_writer.write(bgr)
                        await asyncio.sleep(1/max(fps,1))
                finally:
                    video_writer.release()
            
            recording_task = asyncio.create_task(record_video())
            
            return {
                "success": True,
                "filename": f"{filename}.avi",
                "path": str(video_path)
            }
            
        except ImportError:
            raise Exception("OpenCV未安装")
        except Exception as e:
            raise Exception(f"录制启动失败: {str(e)}")
    
    @staticmethod
    async def stop_recording():
        """停止录制视频"""
        global is_recording, recording_task
        
        if not is_recording:
            raise Exception("未在录制中")
        
        is_recording = False
        
        if recording_task:
            await recording_task
            recording_task = None
        
        return {"success": True, "message": "录制已停止"}

    @staticmethod
    async def set_size(width: int, height: int):
        """仅切换分辨率（宽高），不影响当前帧率；必要时重启预览抓取"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")
        
        # 验证输入参数
        if width <= 0 or height <= 0:
            raise Exception("分辨率参数无效")
        
        # 为避免在预览抓取进行中重配导致底层冲突：先停抓取，再设置，最后重启抓取
        try:
            await DebugCameraService._stop_preview_grabber()
            success = camera.set_resolution(int(width), int(height))
            if not success:
                raise Exception("相机设置分辨率失败")
        except Exception as e:
            # 出错也尽量恢复抓取器
            try:
                await DebugCameraService._ensure_preview_grabber()
            except Exception:
                pass
            raise Exception(f"设置分辨率失败: {str(e)}")

        # 校验是否已生效（以相机报告的尺寸为准）
        info = camera.get_camera_info()
        # 在supersample模式下，检查output_width和output_height
        if info.get('sampling_mode') == 'supersample':
            applied = (int(info.get('output_width', 0)) == int(width) and int(info.get('output_height', 0)) == int(height))
        else:
            applied = (int(info.get('width', 0)) == int(width) and int(info.get('height', 0)) == int(height))
        
        if not applied:
            # 如果设置未生效，尝试重新设置一次
            try:
                success = camera.set_resolution(int(width), int(height))
                if success:
                    info = camera.get_camera_info()
                    if info.get('sampling_mode') == 'supersample':
                        applied = (int(info.get('output_width', 0)) == int(width) and int(info.get('output_height', 0)) == int(height))
                    else:
                        applied = (int(info.get('width', 0)) == int(width) and int(info.get('height', 0)) == int(height))
            except Exception:
                pass
            
            if not applied:
                current_res = f"{info.get('width', 0)}x{info.get('height', 0)}"
                if info.get('sampling_mode') == 'supersample':
                    current_res = f"{info.get('output_width', 0)}x{info.get('output_height', 0)}"
                raise Exception(f"切换分辨率未生效，当前分辨率: {current_res}")

        # 分辨率调整后尝试重启抓取器（失败不影响返回）
        try:
            await DebugCameraService._restart_preview_grabber()
        except Exception:
            pass
        return {"success": True, "message": "分辨率已更新", "info": info}

    @staticmethod
    async def set_sampling_mode(mode: str):
        """切换采样模式（supersample | native | crop）"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")
        
        # 验证输入参数
        if mode not in ['supersample', 'native', 'crop']:
            raise Exception(f"不支持的采样模式: {mode}")
        
        # 避免与预览抓取竞争：先停抓取
        try:
            await DebugCameraService._stop_preview_grabber()
            ok = camera.set_sampling_mode(mode)
            if not ok:
                raise Exception("相机设置采样模式失败")
        except Exception as e:
            try:
                await DebugCameraService._ensure_preview_grabber()
            except Exception:
                pass
            raise Exception(f"设置采样模式失败: {str(e)}")
        
        # 验证设置是否生效
        info = camera.get_camera_info()
        current_mode = info.get('sampling_mode', 'unknown')
        if current_mode != mode:
            raise Exception(f"采样模式设置未生效，当前模式: {current_mode}")
        
        await DebugCameraService._restart_preview_grabber()
        return {"success": True, "message": f"采样模式已设置为 {mode}", "info": info}

    @staticmethod
    async def set_fps(fps: int):
        """仅设置帧率，尽量不影响当前预览"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")
        
        # 验证输入参数
        if fps <= 0 or fps > 60:
            raise Exception(f"帧率参数无效: {fps} (应在1-60之间)")
        
        try:
            ok = False
            # 优先热更新帧率（同步调用，避免执行器上下文问题）
            if hasattr(camera, 'set_fps'):
                ok = camera.set_fps(int(fps))
            else:
                # 兼容旧实现：通过 set_resolution 传入 fps
                info = camera.get_camera_info()
                # 为避免竞争，切换前停抓取
                await DebugCameraService._stop_preview_grabber()
                ok = camera.set_resolution(info.get('width', 640), info.get('height', 360), int(fps))

            if not ok:
                raise Exception("相机设置帧率失败")
            
            # 验证设置是否生效
            info = camera.get_camera_info()
            current_fps = info.get('fps', 0)
            if current_fps != int(fps):
                # 如果设置未生效，尝试重新设置一次
                try:
                    if hasattr(camera, 'set_fps'):
                        ok = camera.set_fps(int(fps))
                    else:
                        ok = camera.set_resolution(info.get('width', 640), info.get('height', 360), int(fps))
                    if ok:
                        info = camera.get_camera_info()
                        current_fps = info.get('fps', 0)
                except Exception:
                    pass
                
                if current_fps != int(fps):
                    raise Exception(f"帧率设置未生效，当前帧率: {current_fps}")
            
            # 帧率变化后，预览抓取节流需要同步
            await DebugCameraService._restart_preview_grabber()
            return {"success": True, "message": f"帧率设置为 {int(fps)}", "info": info}
        except Exception as e:
            raise Exception(f"设置帧率失败: {str(e)}")

    # ==================== 内部：预览抓取器 ====================
    @staticmethod
    async def _ensure_preview_grabber():
        global preview_grabber_task
        if preview_grabber_task and not preview_grabber_task.done():
            return
        preview_grabber_task = asyncio.create_task(DebugCameraService._preview_grabber_loop())

    @staticmethod
    async def _stop_preview_grabber():
        global preview_grabber_task
        if preview_grabber_task:
            preview_grabber_task.cancel()
            try:
                # 添加超时机制，避免无限等待
                await asyncio.wait_for(preview_grabber_task, timeout=2.0)
            except asyncio.TimeoutError:
                # 超时后强制取消
                preview_grabber_task.cancel()
            except asyncio.CancelledError:
                # 任务被取消是正常的，不需要处理
                pass
            except Exception:
                pass
            preview_grabber_task = None

    @staticmethod
    async def _restart_preview_grabber():
        await DebugCameraService._stop_preview_grabber()
        await DebugCameraService._ensure_preview_grabber()

    @staticmethod
    async def _preview_grabber_loop():
        """后台抓取最新帧，编码为 JPEG 缓存，降低单次请求阻塞与抖动"""
        global latest_preview_jpeg, last_preview_time
        camera = get_camera_instance()
        if not camera or not camera.is_capturing:
            return
        import cv2
        import time
        target_fps = max(1, int(camera.get_camera_info().get('fps', 5)))
        interval = 1.0 / target_fps
        try:
            while True:
                start = time.time()
                try:
                    image = camera.get_video_frame()
                    if image is not None:
                        ok, buf = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        if ok:
                            latest_preview_jpeg = buf.tobytes()
                            last_preview_time = time.time()
                except Exception:
                    # 忽略单帧失败
                    pass
                # 按 fps 节流
                spent = time.time() - start
                await asyncio.sleep(max(0.0, interval - spent))
        except asyncio.CancelledError:
            # 正确处理取消信号
            raise
        except Exception as e:
            # 记录其他异常
            import logging
            logging.getLogger(__name__).error(f"预览抓取器异常: {e}")
    
    @staticmethod
    async def update_settings(settings: Dict[str, Any]):
        """更新调试相机设置"""
        camera = get_camera_instance()
        if not camera or not camera.is_initialized:
            raise Exception("相机未初始化")
        
        try:
            # 更新相机参数
            camera.set_exposure(settings["exposure"])
            camera.set_gain(settings["gain"])
            
            return {
                "success": True,
                "message": "相机设置已更新",
                "settings": settings
            }
        except Exception as e:
            raise Exception(f"更新设置失败: {str(e)}")
    
    @staticmethod
    async def reset_camera():
        """重置相机到默认设置"""
        from ogscope.config import get_settings
        
        settings = get_settings()
        camera = get_camera_instance()
        
        if camera and camera.is_initialized:
            camera.set_exposure(settings.camera_exposure)
            camera.set_gain(settings.camera_gain)
        
        return {
            "success": True,
            "message": "相机已重置到默认设置"
        }


class DebugPresetService:
    """调试预设服务"""
    
    @staticmethod
    async def get_presets():
        """获取相机预设列表"""
        presets_file = DEBUG_CAPTURES_DIR / "presets.json"
        
        if not presets_file.exists():
            return {"presets": []}
        
        try:
            with open(presets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {"presets": data.get("presets", [])}
        except Exception as e:
            raise Exception(f"读取预设失败: {str(e)}")
    
    @staticmethod
    async def save_preset(preset_data: Dict[str, Any]):
        """保存相机预设"""
        presets_file = DEBUG_CAPTURES_DIR / "presets.json"
        
        # 读取现有预设
        presets = []
        if presets_file.exists():
            try:
                with open(presets_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    presets = data.get("presets", [])
            except:
                presets = []
        
        # 检查是否已存在同名预设
        for i, existing_preset in enumerate(presets):
            if existing_preset["name"] == preset_data["name"]:
                presets[i] = preset_data
                break
        else:
            # 检查预设数量限制
            if len(presets) >= 10:
                raise Exception("预设数量已达上限(10个)")
            presets.append(preset_data)
        
        # 保存预设
        try:
            with open(presets_file, 'w', encoding='utf-8') as f:
                json.dump({"presets": presets}, f, indent=2, ensure_ascii=False)
            
            return {"success": True, "message": "预设保存成功"}
        except Exception as e:
            raise Exception(f"保存预设失败: {str(e)}")
    
    @staticmethod
    async def apply_preset(preset_name: str):
        """应用相机预设"""
        presets_file = DEBUG_CAPTURES_DIR / "presets.json"
        
        if not presets_file.exists():
            raise Exception("预设文件不存在")
        
        try:
            with open(presets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                presets = data.get("presets", [])
            
            # 查找预设
            preset = None
            for p in presets:
                if p["name"] == preset_name:
                    preset = p
                    break
            
            if not preset:
                raise Exception("预设不存在")
            
            # 应用预设到相机
            camera = get_camera_instance()
            if camera and camera.is_initialized:
                camera.set_exposure(preset["exposure_us"])
                camera.set_gain(preset["analogue_gain"], preset["digital_gain"])
            
            return {"success": True, "message": f"预设 '{preset_name}' 已应用"}
            
        except Exception as e:
            raise Exception(f"应用预设失败: {str(e)}")
    
    @staticmethod
    async def delete_preset(preset_name: str):
        """删除相机预设"""
        presets_file = DEBUG_CAPTURES_DIR / "presets.json"
        
        if not presets_file.exists():
            raise Exception("预设文件不存在")
        
        try:
            with open(presets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                presets = data.get("presets", [])
            
            # 删除预设
            original_count = len(presets)
            presets = [p for p in presets if p["name"] != preset_name]
            
            if len(presets) == original_count:
                raise Exception("预设不存在")
            
            # 保存更新后的预设
            with open(presets_file, 'w', encoding='utf-8') as f:
                json.dump({"presets": presets}, f, indent=2, ensure_ascii=False)
            
            return {"success": True, "message": f"预设 '{preset_name}' 已删除"}
            
        except Exception as e:
            raise Exception(f"删除预设失败: {str(e)}")


class DebugFileService:
    """调试文件服务"""
    
    @staticmethod
    async def get_files():
        """获取拍摄文件列表"""
        try:
            files = []
            for file_path in DEBUG_CAPTURES_DIR.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in ['.jpg', '.mp4']:
                    files.append({
                        "name": file_path.name,
                        "size": file_path.stat().st_size,
                        "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                        "type": "image" if file_path.suffix.lower() == '.jpg' else "video"
                    })
            
            # 按修改时间排序（最新的在前）
            files.sort(key=lambda x: x["modified"], reverse=True)
            
            return {"files": files}
            
        except Exception as e:
            raise Exception(f"获取文件列表失败: {str(e)}")
    
    @staticmethod
    async def get_file_info(filename: str):
        """获取文件信息"""
        file_path = DEBUG_CAPTURES_DIR / filename
        info_path = DEBUG_CAPTURES_DIR / f"{file_path.stem}.txt"
        
        if not file_path.exists():
            raise Exception("文件不存在")
        
        try:
            info = {
                "filename": filename,
                "size": file_path.stat().st_size,
                "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                "type": "image" if file_path.suffix.lower() == '.jpg' else "video"
            }
            
            # 读取拍摄信息
            if info_path.exists():
                with open(info_path, 'r', encoding='utf-8') as f:
                    capture_info = json.load(f)
                    info.update(capture_info)
            
            return info
            
        except Exception as e:
            raise Exception(f"获取文件信息失败: {str(e)}")
