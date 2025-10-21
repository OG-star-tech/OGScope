#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPIO 配置模块
适配 Raspberry Pi Zero 2W 的引脚布局
"""

import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class PinMode(Enum):
    """引脚模式"""
    INPUT = "input"
    OUTPUT = "output"
    PWM = "pwm"
    SPI = "spi"
    I2C = "i2c"


class RaspberryPiZero2WGPIO:
    """树莓派 Zero 2W GPIO 配置"""
    
    # GPIO 引脚定义 (BCM 编号)
    GPIO_PINS = {
        # 电源引脚
        "3V3": 1,      # 3.3V 电源
        "5V": 2,       # 5V 电源
        "GND": 6,      # 地线
        
        # GPIO 引脚
        "GPIO2": 2,    # SDA (I2C)
        "GPIO3": 3,    # SCL (I2C)
        "GPIO4": 4,    # 通用 GPIO
        "GPIO5": 5,    # 通用 GPIO
        "GPIO6": 6,    # 通用 GPIO
        "GPIO7": 7,    # SPI_CE1
        "GPIO8": 8,    # SPI_CE0
        "GPIO9": 9,    # SPI_MISO
        "GPIO10": 10,  # SPI_MOSI
        "GPIO11": 11,  # SPI_CLK
        "GPIO12": 12,  # 通用 GPIO
        "GPIO13": 13,  # 通用 GPIO
        "GPIO14": 14,  # TXD (UART)
        "GPIO15": 15,  # RXD (UART)
        "GPIO16": 16,  # 通用 GPIO
        "GPIO17": 17,  # 通用 GPIO
        "GPIO18": 18,  # PWM0
        "GPIO19": 19,  # PWM1
        "GPIO20": 20,  # 通用 GPIO
        "GPIO21": 21,  # 通用 GPIO
        "GPIO22": 22,  # 通用 GPIO
        "GPIO23": 23,  # 通用 GPIO
        "GPIO24": 24,  # 通用 GPIO
        "GPIO25": 25,  # 通用 GPIO
        "GPIO26": 26,  # 通用 GPIO
        "GPIO27": 27,  # 通用 GPIO
    }
    
    # SPI 接口配置
    SPI_CONFIG = {
        "bus": 0,           # SPI 总线
        "device": 0,        # SPI 设备
        "clock_pin": 11,    # GPIO11 - SCLK
        "miso_pin": 9,      # GPIO9 - MISO
        "mosi_pin": 10,     # GPIO10 - MOSI
        "cs_pin": 8,        # GPIO8 - CS0
        "cs1_pin": 7,       # GPIO7 - CS1
        "speed": 8000000,   # SPI 时钟频率 (8MHz)
    }
    
    # I2C 接口配置
    I2C_CONFIG = {
        "bus": 1,           # I2C 总线
        "sda_pin": 2,       # GPIO2 - SDA
        "scl_pin": 3,       # GPIO3 - SCL
        "address": 0x3C,    # 默认 I2C 地址
        "speed": 100000,    # I2C 时钟频率 (100kHz)
    }
    
    # 显示屏 SPI 配置
    DISPLAY_SPI_CONFIG = {
        "bus": 0,
        "device": 0,
        "dc_pin": 25,       # 数据/命令选择引脚
        "rst_pin": 27,      # 复位引脚
        "cs_pin": 8,        # 片选引脚
        "backlight_pin": 18, # 背光控制 (PWM)
        "width": 240,
        "height": 320,
        "rotation": 0,
    }
    
    # 按键 GPIO 配置
    BUTTON_CONFIG = {
        "button1_pin": 4,   # 按键1
        "button2_pin": 5,   # 按键2
        "button3_pin": 6,   # 按键3
        "button4_pin": 12,  # 按键4
        "pull_up": True,    # 内部上拉
        "debounce_ms": 50,  # 防抖时间
    }
    
    # LED 配置
    LED_CONFIG = {
        "status_led_pin": 16,    # 状态 LED
        "activity_led_pin": 20,  # 活动 LED
        "error_led_pin": 21,     # 错误 LED
    }


class GPIOConfig:
    """GPIO 配置管理类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.gpio_config = RaspberryPiZero2WGPIO()
        self._validate_config()
    
    def _validate_config(self):
        """验证配置"""
        # 检查显示屏配置
        if self.config.get("display", {}).get("enabled", False):
            display_config = self.config["display"]
            required_pins = ["dc_pin", "rst_pin"]
            for pin in required_pins:
                if pin not in display_config:
                    logger.warning(f"显示屏配置缺少 {pin}")
        
        # 检查按键配置
        button_config = self.config.get("buttons", {})
        if button_config.get("enabled", False):
            # 验证按键引脚配置
            pass
    
    def get_display_config(self) -> Dict[str, Any]:
        """获取显示屏配置"""
        display_config = self.config.get("display", {})
        if not display_config.get("enabled", False):
            return {}
        
        # 合并默认配置和用户配置
        config = self.gpio_config.DISPLAY_SPI_CONFIG.copy()
        config.update(display_config)
        
        return config
    
    def get_button_config(self) -> Dict[str, Any]:
        """获取按键配置"""
        button_config = self.config.get("buttons", {})
        if not button_config.get("enabled", False):
            return {}
        
        config = self.gpio_config.BUTTON_CONFIG.copy()
        config.update(button_config)
        
        return config
    
    def get_led_config(self) -> Dict[str, Any]:
        """获取 LED 配置"""
        led_config = self.config.get("leds", {})
        if not led_config.get("enabled", False):
            return {}
        
        config = self.gpio_config.LED_CONFIG.copy()
        config.update(led_config)
        
        return config
    
    def get_spi_config(self) -> Dict[str, Any]:
        """获取 SPI 配置"""
        return self.gpio_config.SPI_CONFIG.copy()
    
    def get_i2c_config(self) -> Dict[str, Any]:
        """获取 I2C 配置"""
        return self.gpio_config.I2C_CONFIG.copy()
    
    def validate_pin(self, pin_name: str) -> bool:
        """验证引脚名称是否有效"""
        return pin_name in self.gpio_config.GPIO_PINS
    
    def get_pin_number(self, pin_name: str) -> Optional[int]:
        """获取引脚编号"""
        return self.gpio_config.GPIO_PINS.get(pin_name)
    
    def get_all_used_pins(self) -> list:
        """获取所有已使用的引脚"""
        used_pins = []
        
        # 显示屏引脚
        display_config = self.get_display_config()
        if display_config:
            used_pins.extend([
                display_config.get("dc_pin"),
                display_config.get("rst_pin"),
                display_config.get("cs_pin"),
                display_config.get("backlight_pin"),
            ])
        
        # 按键引脚
        button_config = self.get_button_config()
        if button_config:
            used_pins.extend([
                button_config.get("button1_pin"),
                button_config.get("button2_pin"),
                button_config.get("button3_pin"),
                button_config.get("button4_pin"),
            ])
        
        # LED 引脚
        led_config = self.get_led_config()
        if led_config:
            used_pins.extend([
                led_config.get("status_led_pin"),
                led_config.get("activity_led_pin"),
                led_config.get("error_led_pin"),
            ])
        
        # 移除 None 值
        used_pins = [pin for pin in used_pins if pin is not None]
        
        return used_pins


# 默认配置
DEFAULT_GPIO_CONFIG = {
    "display": {
        "enabled": False,
        "type": "st7789",
        "dc_pin": 25,
        "rst_pin": 27,
        "cs_pin": 8,
        "backlight_pin": 18,
        "width": 240,
        "height": 320,
        "rotation": 0,
    },
    "buttons": {
        "enabled": False,
        "button1_pin": 4,
        "button2_pin": 5,
        "button3_pin": 6,
        "button4_pin": 12,
    },
    "leds": {
        "enabled": True,
        "status_led_pin": 16,
        "activity_led_pin": 20,
        "error_led_pin": 21,
    },
}
