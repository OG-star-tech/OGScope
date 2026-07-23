#!/usr/bin/env python3
"""
ST7796 SPI 屏冒烟测试（spidev + RPi.GPIO DC）/ ST7796 SPI display smoke test.

默认：320×320，DC=GPIO24；接线（BCM）/ Default wiring:
  SCK→GPIO11, MOSI→GPIO10, CS/CE0→GPIO8（物理脚 24）, DC→GPIO24（物理脚 18）, GND, 3V3, BL→3V3 或 PWM

环境变量 / Env: OGSCOPE_SPI_DC, OGSCOPE_SPI_W, OGSCOPE_SPI_H, OGSCOPE_SPI_BUS_SPEED

需启用 SPI：`/boot/firmware/config.txt` 中 `dtparam=spi=on` / Enable SPI on Pi.
"""
from __future__ import annotations

import os
import sys
import time


def _print_spi_hints() -> None:
    """在 Pi 上自助检查 SPI 节点 / Self-check SPI device nodes on Pi."""
    import glob

    nodes = sorted(glob.glob("/dev/spidev*"))
    print("当前 /dev/spidev*:", nodes if nodes else "（无 / none）")
    print(
        "若无 spidev：sudo raspi-config → Interface Options → SPI → Yes；"
        "或编辑 /boot/firmware/config.txt 加入 dtparam=spi=on 后 sudo reboot"
    )
    print(
        "若有设备仍失败：groups 是否含 spi；若无则 sudo usermod -aG spi $USER 后重新登录"
    )


def main() -> int:
    if sys.platform != "linux":
        print("仅适用于 Linux（树莓派）/ Linux (Raspberry Pi) only")
        return 1

    dc = int(os.environ.get("OGSCOPE_SPI_DC", "24"))
    width = int(os.environ.get("OGSCOPE_SPI_W", "320"))
    height = int(os.environ.get("OGSCOPE_SPI_H", "320"))
    bus_hz = int(os.environ.get("OGSCOPE_SPI_BUS_SPEED", "16000000"))

    try:
        from ogscope.platform.hardware.st7796_spi import ST7796SPI
    except ImportError as e:
        print(
            "缺少依赖：在树莓派上 poetry install（需 spidev、RPi.GPIO）/ Missing deps:",
            e,
        )
        return 1

    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.load_default()
    except OSError:
        font = None

    im = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(200, 200, 200))
    msg = "OGScope\nSPI OK"
    if font:
        draw.multiline_text(
            (8, height // 2 - 20),
            msg,
            fill=(255, 255, 255),
            font=font,
            spacing=4,
        )
    else:
        draw.text((8, height // 2), "OGScope SPI OK", fill=(255, 255, 255))

    disp: ST7796SPI | None = None
    try:
        disp = ST7796SPI(dc_pin=dc, width=width, height=height, max_speed_hz=bus_hz)
        disp.show_pil_rgb(im)
    except OSError as e:
        print("显示失败 / Display error:", e)
        if getattr(e, "errno", None) == 2:
            _print_spi_hints()
        if os.environ.get("OGSCOPE_SPI_DEBUG"):
            import traceback

            traceback.print_exc()
        return 1
    except Exception as e:
        print("显示失败 / Display error:", e)
        if os.environ.get("OGSCOPE_SPI_DEBUG"):
            import traceback

            traceback.print_exc()
        return 1
    finally:
        if disp is not None:
            disp.close()

    print(
        f"已绘制测试画面（{width}x{height} DC=GPIO{dc}）/ Drawn test pattern. Check backlight (BL)."
    )
    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
