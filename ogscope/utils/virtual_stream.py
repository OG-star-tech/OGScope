"""
虚拟视频流生成器
用于开发环境模拟相机视频流
"""
import io
import math
import random
import time
from typing import Tuple, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2


class VirtualVideoStream:
    """虚拟视频流生成器"""
    
    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_time = 1.0 / fps
        self.last_frame_time = 0
        
        # 模拟参数
        self.star_field_density = 0.1
        self.polar_star_position = (0.5, 0.3)  # 极轴星位置
        self.noise_level = 0.05
        self.atmospheric_turbulence = True
        
        # 生成星点数据
        self.stars = self._generate_star_field()
        
        # 大气湍流参数
        self.turbulence_offset = 0
        self.turbulence_speed = 0.1
        
        # 时间戳
        self.start_time = time.time()
    
    def _generate_star_field(self) -> list:
        """生成星点数据"""
        stars = []
        num_stars = int(self.width * self.height * self.star_field_density / 10000)
        
        for _ in range(num_stars):
            # 随机位置
            x = random.uniform(0, 1)
            y = random.uniform(0, 1)
            
            # 随机星等 (1-6等)
            magnitude = random.uniform(1.0, 6.0)
            
            # 根据星等计算亮度
            brightness = max(0, 1.0 - (magnitude - 1) / 5.0)
            
            # 星点大小
            size = max(1, int(3 * brightness))
            
            stars.append({
                'x': x,
                'y': y,
                'magnitude': magnitude,
                'brightness': brightness,
                'size': size,
                'twinkle_phase': random.uniform(0, 2 * math.pi)
            })
        
        # 添加极轴星（北极星）
        stars.append({
            'x': self.polar_star_position[0],
            'y': self.polar_star_position[1],
            'magnitude': 2.0,
            'brightness': 0.8,
            'size': 4,
            'twinkle_phase': 0,
            'is_polar_star': True
        })
        
        return stars
    
    def _apply_atmospheric_turbulence(self, image: np.ndarray) -> np.ndarray:
        """应用大气湍流效果"""
        if not self.atmospheric_turbulence:
            return image
        
        # 简单的湍流效果：轻微的位置偏移
        self.turbulence_offset += self.turbulence_speed
        
        # 创建湍流偏移
        turbulence_x = int(2 * math.sin(self.turbulence_offset))
        turbulence_y = int(1 * math.cos(self.turbulence_offset * 1.3))
        
        # 应用偏移
        if turbulence_x != 0 or turbulence_y != 0:
            M = np.float32([[1, 0, turbulence_x], [0, 1, turbulence_y]])
            image = cv2.warpAffine(image, M, (self.width, self.height))
        
        return image
    
    def _add_noise(self, image: np.ndarray) -> np.ndarray:
        """添加噪声"""
        if self.noise_level <= 0:
            return image
        
        # 生成随机噪声
        noise = np.random.normal(0, self.noise_level * 255, image.shape).astype(np.uint8)
        
        # 添加噪声到图像
        noisy_image = cv2.add(image, noise)
        
        return noisy_image
    
    def _draw_stars(self, image: np.ndarray) -> np.ndarray:
        """绘制星点"""
        current_time = time.time()
        
        for star in self.stars:
            # 计算闪烁效果
            twinkle = 0.8 + 0.2 * math.sin(star['twinkle_phase'] + current_time * 2)
            brightness = star['brightness'] * twinkle
            
            # 计算像素位置
            x = int(star['x'] * self.width)
            y = int(star['y'] * self.height)
            
            # 绘制星点
            size = star['size']
            color = int(255 * brightness)
            
            # 绘制星点（圆形）
            cv2.circle(image, (x, y), size, (color, color, color), -1)
            
            # 为亮星添加十字光芒
            if brightness > 0.7:
                # 水平线
                cv2.line(image, (x - size*2, y), (x + size*2, y), (color, color, color), 1)
                # 垂直线
                cv2.line(image, (x, y - size*2), (x, y + size*2), (color, color, color), 1)
            
            # 为极轴星添加特殊标记
            if star.get('is_polar_star'):
                # 绘制极轴星标记
                cv2.circle(image, (x, y), size + 2, (0, 255, 255), 2)  # 黄色圆圈
                # 添加文字标记
                cv2.putText(image, "Polaris", (x + 10, y - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        
        return image
    
    def _draw_crosshair(self, image: np.ndarray) -> np.ndarray:
        """绘制十字准星"""
        center_x = self.width // 2
        center_y = self.height // 2
        
        # 绘制十字准星
        color = (255, 0, 0)  # 红色
        thickness = 2
        
        # 水平线
        cv2.line(image, (center_x - 20, center_y), (center_x + 20, center_y), color, thickness)
        # 垂直线
        cv2.line(image, (center_x, center_y - 20), (center_x, center_y + 20), color, thickness)
        
        # 中心圆
        cv2.circle(image, (center_x, center_y), 8, color, thickness)
        
        return image
    
    def _draw_coordinate_grid(self, image: np.ndarray) -> np.ndarray:
        """绘制坐标网格"""
        color = (64, 64, 64)  # 深灰色
        thickness = 1
        
        # 绘制网格线
        for i in range(0, self.width, self.width // 10):
            cv2.line(image, (i, 0), (i, self.height), color, thickness)
        
        for i in range(0, self.height, self.height // 10):
            cv2.line(image, (0, i), (self.width, i), color, thickness)
        
        return image
    
    def generate_frame(self) -> bytes:
        """生成一帧图像"""
        current_time = time.time()
        
        # 控制帧率
        if current_time - self.last_frame_time < self.frame_time:
            time.sleep(self.frame_time - (current_time - self.last_frame_time))
        
        self.last_frame_time = time.time()
        
        # 创建黑色背景
        image = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # 绘制坐标网格
        image = self._draw_coordinate_grid(image)
        
        # 绘制星点
        image = self._draw_stars(image)
        
        # 绘制十字准星
        image = self._draw_crosshair(image)
        
        # 应用大气湍流
        image = self._apply_atmospheric_turbulence(image)
        
        # 添加噪声
        image = self._add_noise(image)
        
        # 转换为JPEG
        _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        return buffer.tobytes()
    
    def get_star_positions(self) -> list:
        """获取当前星点位置（用于校准）"""
        return [
            {
                'x': star['x'] * self.width,
                'y': star['y'] * self.height,
                'magnitude': star['magnitude'],
                'name': 'Polaris' if star.get('is_polar_star') else f'Star_{i}'
            }
            for i, star in enumerate(self.stars)
        ]
    
    def update_polar_star_position(self, x: float, y: float):
        """更新极轴星位置"""
        self.polar_star_position = (x, y)
        # 更新极轴星位置
        for star in self.stars:
            if star.get('is_polar_star'):
                star['x'] = x
                star['y'] = y
                break
    
    def set_simulation_parameters(self, **kwargs):
        """设置模拟参数"""
        if 'star_field_density' in kwargs:
            self.star_field_density = kwargs['star_field_density']
            self.stars = self._generate_star_field()
        
        if 'noise_level' in kwargs:
            self.noise_level = kwargs['noise_level']
        
        if 'atmospheric_turbulence' in kwargs:
            self.atmospheric_turbulence = kwargs['atmospheric_turbulence']


# 全局虚拟视频流实例
_virtual_stream: Optional[VirtualVideoStream] = None


def get_virtual_stream() -> VirtualVideoStream:
    """获取虚拟视频流实例"""
    global _virtual_stream
    if _virtual_stream is None:
        _virtual_stream = VirtualVideoStream()
    return _virtual_stream


def create_virtual_stream(width: int = 1920, height: int = 1080, fps: int = 30) -> VirtualVideoStream:
    """创建新的虚拟视频流实例"""
    return VirtualVideoStream(width, height, fps)
