# OGScope hardware bill of materials (BOM)

English | [中文](bom.md)

## Core hardware

| # | Item | Model / spec | Qty | Ref. price | Notes |
|---|------|--------------|-----|------------|-------|
| 1 | SBC | Raspberry Pi Zero 2W | 1 | ~¥180 | Required |
| 2 | Camera | IMX327 MIPI module | 1 | ~¥100 | Required |
| 3 | Display | 2.4" SPI LCD | 1 | ~¥30 | Required |
| 4 | microSD | 32GB Class 10 | 1 | ~¥30 | Required |
| 5 | PSU | 5V 3A USB-C | 1 | ~¥20 | Required |

## Optional hardware

| # | Item | Model / spec | Qty | Ref. price | Notes |
|---|------|--------------|-----|------------|-------|
| 6 | Heatsink | Aluminum kit | 1 | ~¥10 | Recommended |
| 7 | Tact switch | 6×6 mm | 4–6 | ~¥5 | Optional |
| 8 | Resistor | 10kΩ bussed | 1 | ~¥2 | For buttons |
| 9 | USB Ethernet | RTL8152 | 1 | ~¥15 | Wired fallback |
| 10 | Enclosure | 3D printed | 1 | ~¥30 | DIY |

## Camera selection

### IMX327 module

- **Sensor**: Sony IMX327
- **Resolution**: 1920×1080 (2MP)
- **Pixel**: 2.9 µm
- **Interface**: MIPI CSI
- **Sensitivity**: suited for polar scope use
- **Sourcing**: Taobao / AliExpress

**Notes**:
- **Option A**: IMX327 module with Pi Zero 2W–compatible MIPI CSI flex.
- **Option B**: Official or compatible Raspberry Pi camera modules.
- **Option C**: Any MIX327 variant verified for Pi Zero 2W CSI.

## Display selection

### 2.4" SPI LCD

- **Drivers**: ST7789 or ILI9341
- **Resolution**: 240×320 or 240×240
- **Bus**: SPI
- **Touch**: optional resistive
- **Sourcing**: Waveshare, Adafruit, etc.

**Examples**:
- Waveshare 2.4" LCD (ST7789)
- Adafruit 2.4" TFT (ILI9341)

## Power

- **Voltage**: 5V
- **Current**: 3A recommended (Pi + camera + display)
- **Connector**: USB Type-C
- **Tip**: use a quality adapter to avoid brownouts

## 3D printed enclosure

- **Material**: PLA or PETG
- **Infill**: ~20%
- **Supports**: per design
- **STLs**: `hardware/3d_models/` (if present in repo)

## Tools

- Phillips / flat screwdrivers
- Tweezers
- Hot glue (optional)
- Dupont jumpers

## Rough cost

- **Minimum**: ~¥330 (no enclosure)
- **Recommended**: ~¥380 (with common extras)
- **Full**: ~¥450 (all optional items)

## Where to buy

### China

- **Raspberry Pi**: official Taobao store
- **IMX327**: search “IMX327 Raspberry Pi MIPI”
- **LCD**: [Waveshare](https://www.waveshare.net/)

### International

- **Raspberry Pi**: AliExpress official / resellers
- **IMX327**: AliExpress
- **LCD**: [Adafruit](https://www.adafruit.com/)

## Caveats

1. **Camera**: confirm CSI mechanical and electrical compatibility with Pi Zero 2W.
2. **PSU**: inadequate power causes instability.
3. **Cooling**: add a heatsink for long runs.
4. **SD card**: use a fast card for responsive OS.

## Upgrade ideas

- **IMX462**: higher sensitivity (~¥150)
- **GPS**: time and location (~¥50)
- **IMU**: orientation (~¥20)

---

Last updated: 2025-01-01
