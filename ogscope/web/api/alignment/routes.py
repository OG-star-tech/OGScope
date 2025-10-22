"""
极轴校准相关API路由
支持真实校准和模拟模式
"""
from fastapi import APIRouter, HTTPException
from ogscope.web.api.models.schemas import PolarAlignStatus, AlignmentStatus
from ogscope.utils.environment import should_use_simulation_mode
from ogscope.utils.virtual_stream import get_virtual_stream
import logging
import time
import random

logger = logging.getLogger(__name__)
router = APIRouter()

# 全局校准状态
_alignment_in_progress = False
_alignment_start_time = None
_simulation_mode = should_use_simulation_mode()

if _simulation_mode:
    logger.info("极轴校准API：启用模拟模式")


@router.post("/polar-align/start")
async def start_polar_alignment():
    """开始极轴校准"""
    global _alignment_in_progress, _alignment_start_time
    
    if _simulation_mode:
        _alignment_in_progress = True
        _alignment_start_time = time.time()
        logger.info("模拟模式：开始极轴校准")
        return {
            "success": True,
            "message": "模拟极轴校准已启动",
            "mode": "simulation"
        }
    else:
        # TODO: 实现真实极轴校准启动
        _alignment_in_progress = True
        _alignment_start_time = time.time()
        return {
            "success": True,
            "message": "极轴校准已启动",
            "mode": "real"
        }


@router.post("/alignment/start")
async def start_alignment():
    """开始极轴校准"""
    global _alignment_in_progress, _alignment_start_time
    
    if _simulation_mode:
        _alignment_in_progress = True
        _alignment_start_time = time.time()
        logger.info("模拟模式：开始极轴校准")
        return {"status": "success", "message": "模拟极轴校准已开始", "mode": "simulation"}
    else:
        # TODO: 实现真实极轴校准启动逻辑
        _alignment_in_progress = True
        _alignment_start_time = time.time()
        return {"status": "success", "message": "极轴校准已开始", "mode": "real"}


@router.post("/alignment/stop")
async def stop_alignment():
    """停止极轴校准"""
    global _alignment_in_progress
    
    if _simulation_mode:
        _alignment_in_progress = False
        logger.info("模拟模式：停止极轴校准")
        return {"status": "success", "message": "模拟极轴校准已停止", "mode": "simulation"}
    else:
        # TODO: 实现真实极轴校准停止逻辑
        _alignment_in_progress = False
        return {"status": "success", "message": "极轴校准已停止", "mode": "real"}


@router.get("/alignment/status")
async def get_alignment_status():
    """获取极轴校准状态"""
    if _simulation_mode:
        if not _alignment_in_progress:
            return {
                "status": "idle",
                "azimuth_error": 0.0,
                "altitude_error": 0.0,
                "precision": "excellent",
                "progress": 0,
                "mode": "simulation"
            }
        
        # 模拟校准进度
        elapsed_time = time.time() - _alignment_start_time if _alignment_start_time else 0
        
        # 模拟校准过程
        if elapsed_time < 2:
            status = "starting"
            progress = int(elapsed_time * 10)
            azimuth_error = 5.0 - elapsed_time * 2.5
            altitude_error = 4.0 - elapsed_time * 2.0
        elif elapsed_time < 5:
            status = "identifying"
            progress = 20 + int((elapsed_time - 2) * 20)
            azimuth_error = 2.5 - (elapsed_time - 2) * 0.8
            altitude_error = 2.0 - (elapsed_time - 2) * 0.6
        elif elapsed_time < 7:
            status = "calibrating"
            progress = 60 + int((elapsed_time - 5) * 15)
            azimuth_error = 1.0 - (elapsed_time - 5) * 0.4
            altitude_error = 0.8 - (elapsed_time - 5) * 0.3
        elif elapsed_time < 10:
            status = "targeting"
            progress = 90 + int((elapsed_time - 7) * 3)
            azimuth_error = max(0.1, 0.2 - (elapsed_time - 7) * 0.05)
            altitude_error = max(0.1, 0.2 - (elapsed_time - 7) * 0.05)
        else:
            status = "completed"
            progress = 100
            azimuth_error = 0.05
            altitude_error = 0.05
        
        # 添加一些随机波动
        azimuth_error += random.uniform(-0.1, 0.1)
        altitude_error += random.uniform(-0.1, 0.1)
        
        # 确定精度等级
        max_error = max(abs(azimuth_error), abs(altitude_error))
        if max_error < 0.5:
            precision = "excellent"
        elif max_error < 1.0:
            precision = "good"
        elif max_error < 2.0:
            precision = "fair"
        else:
            precision = "poor"
        
        return {
            "status": status,
            "azimuth_error": round(azimuth_error, 2),
            "altitude_error": round(altitude_error, 2),
            "precision": precision,
            "progress": min(100, max(0, progress)),
            "mode": "simulation"
        }
    else:
        # TODO: 实现真实极轴校准状态获取逻辑
        return {
            "status": "running",
            "azimuth_error": 2.5,
            "altitude_error": 1.8,
            "precision": "good",
            "progress": 75,
            "mode": "real"
        }


@router.get("/polar-align/status")
async def get_polar_align_status() -> PolarAlignStatus:
    """获取极轴校准状态"""
    if _simulation_mode:
        if not _alignment_in_progress:
            return PolarAlignStatus(
                status="idle",
                azimuth_error=0.0,
                altitude_error=0.0,
            )
        
        # 获取当前校准状态
        status_data = await get_alignment_status()
        
        return PolarAlignStatus(
            status=status_data["status"],
            azimuth_error=status_data["azimuth_error"],
            altitude_error=status_data["altitude_error"],
        )
    else:
        # TODO: 实现真实极轴校准状态获取
        return PolarAlignStatus(
            status="idle",
            azimuth_error=0.0,
            altitude_error=0.0,
        )


@router.post("/polar-align/stop")
async def stop_polar_alignment():
    """停止极轴校准"""
    global _alignment_in_progress
    
    if _simulation_mode:
        _alignment_in_progress = False
        logger.info("模拟模式：停止极轴校准")
        return {
            "success": True,
            "message": "模拟极轴校准已停止",
            "mode": "simulation"
        }
    else:
        # TODO: 实现真实极轴校准停止
        _alignment_in_progress = False
        return {
            "success": True,
            "message": "极轴校准已停止",
            "mode": "real"
        }


@router.get("/alignment/stars")
async def get_alignment_stars():
    """获取校准过程中的星点信息"""
    if _simulation_mode:
        try:
            virtual_stream = get_virtual_stream()
            stars = virtual_stream.get_star_positions()
            
            # 添加一些模拟的星点识别信息
            enhanced_stars = []
            for i, star in enumerate(stars):
                enhanced_star = star.copy()
                enhanced_star.update({
                    "confidence": random.uniform(0.7, 0.95),
                    "detected_at": time.time(),
                    "constellation": "Ursa Minor" if star.get('name') == 'Polaris' else "Unknown"
                })
                enhanced_stars.append(enhanced_star)
            
            return {
                "stars": enhanced_stars,
                "count": len(enhanced_stars),
                "detection_quality": "good",
                "mode": "simulation"
            }
        except Exception as e:
            logger.error(f"获取模拟星点信息失败: {e}")
            raise HTTPException(status_code=500, detail="获取星点信息失败")
    else:
        # TODO: 实现真实星点检测
        return {
            "stars": [],
            "count": 0,
            "detection_quality": "unknown",
            "mode": "real"
        }