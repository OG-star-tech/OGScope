"""
ST7796 SPI 彩屏（如 1.54 寸 320×320 IPS）/ ST7796 SPI TFT (e.g. 1.54 inch 320×320).

初始化序列参考 Bodmer TFT_eSPI `ST7796_Init.h`；B6 第三参数按 320 行面板调整为 0x27。
Init sequence derived from Bodmer TFT_eSPI ST7796_Init.h; B6 third byte set for 320-line panel.
"""

from __future__ import annotations

import errno
import os
import time


def _rgb888_to_rgb565_be(r: int, g: int, b: int) -> tuple[int, int]:
    """RGB565 高字节在前（SPI 常见）/ RGB565 big-endian bytes."""
    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return (v >> 8) & 0xFF, v & 0xFF


class ST7796SPI:
    """ST7796，硬件 SPI0 CE0 + 独立 DC 引脚 / ST7796 on SPI0 CE0 + GPIO DC."""

    def __init__(
        self,
        *,
        dc_pin: int = 24,
        width: int = 320,
        height: int = 320,
        spi_bus: int = 0,
        spi_dev: int = 0,
        max_speed_hz: int = 16_000_000,
    ) -> None:
        import RPi.GPIO as GPIO  # noqa: N814
        import spidev

        self._GPIO = GPIO
        self._dc_pin = int(dc_pin)
        self.width = int(width)
        self.height = int(height)

        spi_path = f"/dev/spidev{spi_bus}.{spi_dev}"
        if not os.path.exists(spi_path):
            raise OSError(
                errno.ENOENT,
                f"SPI 设备不存在 {spi_path}。在 /boot/firmware/config.txt 加入 dtparam=spi=on "
                f"（或 raspi-config Interface Options → SPI）后重启。/ Missing SPI node; enable SPI and reboot.",
            )

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._dc_pin, GPIO.OUT, initial=GPIO.LOW)

        self._spi = spidev.SpiDev()
        try:
            self._spi.open(spi_bus, spi_dev)
        except OSError as e:
            if e.errno == errno.ENOENT:
                raise OSError(
                    errno.ENOENT,
                    f"无法打开 {spi_path}（Errno 2）。确认已启用 SPI 且当前用户可访问该设备（必要时将用户加入 spi 组并重新登录）。/"
                    f" Cannot open SPI device; enable SPI and check spi group.",
                ) from e
            raise
        self._spi.max_speed_hz = max_speed_hz
        self._spi.mode = 0

        self._init_sequence()

    def close(self) -> None:
        try:
            self._spi.close()
        except OSError:
            pass
        try:
            self._GPIO.cleanup()
        except Exception:
            pass

    def _wr_cmd(self, cmd: int, data: list[int] | None = None) -> None:
        self._GPIO.output(self._dc_pin, self._GPIO.LOW)
        self._spi.xfer2([cmd & 0xFF])
        if data:
            self._GPIO.output(self._dc_pin, self._GPIO.HIGH)
            self._spi.xfer2([d & 0xFF for d in data])

    def _init_sequence(self) -> None:
        # 与 TFT_eSPI ST7796_Init.h 一致；B6[2]=0x27 对应 320 行 (40*8) / Match TFT_eSPI; B6 line count for 320 px
        d = self._wr_cmd
        time.sleep(0.12)
        d(0x01)
        time.sleep(0.12)
        d(0x11)
        time.sleep(0.12)
        d(0xF0, [0xC3])
        d(0xF0, [0x96])
        d(0x36, [0x48])
        d(0x3A, [0x55])
        d(0xB4, [0x01])
        d(0xB6, [0x80, 0x02, 0x27])
        d(0xE8, [0x40, 0x8A, 0x00, 0x00, 0x29, 0x19, 0xA5, 0x33])
        d(0xC1, [0x06])
        d(0xC2, [0xA7])
        d(0xC5, [0x18])
        time.sleep(0.12)
        d(
            0xE0,
            [
                0xF0,
                0x09,
                0x0B,
                0x06,
                0x04,
                0x15,
                0x2F,
                0x54,
                0x42,
                0x3C,
                0x17,
                0x14,
                0x18,
                0x1B,
            ],
        )
        d(
            0xE1,
            [
                0xE0,
                0x09,
                0x0B,
                0x06,
                0x04,
                0x03,
                0x2B,
                0x43,
                0x42,
                0x3B,
                0x16,
                0x14,
                0x17,
                0x1B,
            ],
        )
        time.sleep(0.12)
        d(0xF0, [0x3C])
        d(0xF0, [0x69])
        time.sleep(0.12)
        d(0x29)
        time.sleep(0.02)

    def set_window(self, x0: int, y0: int, x1: int, y1: int) -> None:
        """列/行地址窗口（含边界，0-based）/ Column and row address window (inclusive)."""
        d = self._wr_cmd
        d(0x2A, [(x0 >> 8) & 0xFF, x0 & 0xFF, (x1 >> 8) & 0xFF, x1 & 0xFF])
        d(0x2B, [(y0 >> 8) & 0xFF, y0 & 0xFF, (y1 >> 8) & 0xFF, y1 & 0xFF])
        d(0x2C)

    def show_pil_rgb(self, image) -> None:
        """显示 PIL RGB 图（自动缩放到屏尺寸）/ Show PIL image, resized to panel size."""
        from PIL import Image as PILImage

        try:
            resample = PILImage.Resampling.BILINEAR
        except AttributeError:
            resample = PILImage.BILINEAR
        im = image.convert("RGB").resize((self.width, self.height), resample)
        raw = im.tobytes("raw", "RGB")
        ba = bytearray(self.width * self.height * 2)
        j = 0
        for i in range(0, len(raw), 3):
            r, g, b = raw[i], raw[i + 1], raw[i + 2]
            hi, lo = _rgb888_to_rgb565_be(r, g, b)
            ba[j] = hi
            ba[j + 1] = lo
            j += 2
        self.set_window(0, 0, self.width - 1, self.height - 1)
        self._GPIO.output(self._dc_pin, self._GPIO.HIGH)
        # 树莓派 spidev 单次 ioctl 缓冲常见上限约 4KiB；8192 会报 Argument list size exceeds 4096 bytes
        chunk = 2048
        for off in range(0, len(ba), chunk):
            self._spi.xfer2(list(ba[off : off + chunk]))
