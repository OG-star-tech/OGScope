# OGScope - Electronic Polar Scope

An intelligent electronic polar scope system based on Raspberry Pi Zero 2W for precise polar alignment in astrophotography.

English | [中文](README.md)

## Hardware Platform

- **Main Controller**: Raspberry Pi Zero 2W
- **Operating System**: Raspberry Pi OS
- **Camera**: IMX327 MIPI sensor
- **Display**: 2.4" SPI LCD
- **Communication**: WiFi wireless control

## Features

### Phase 1 - Basic Features (MVP)
- ✅ Real-time video preview
- ✅ Web remote control
- ✅ Basic polar alignment
- ✅ Camera parameter adjustment

### Phase 2 - Complete Features
- ⏳ SPI screen display
- ⏳ Automatic plate solving
- ⏳ Mobile app control
- ⏳ Calibration data management

### Phase 3 - Ecosystem Integration
- ⏳ INDI driver support
- ⏳ Mount control
- ⏳ Multi-device coordination

### Key Features

- 🔭 **Precise Alignment**: High-precision polar alignment algorithms
- 📱 **Remote Control**: Web interface and mobile app
- 🖥️ **Local Display**: 2.4" SPI LCD real-time display
- 🌐 **Ecosystem Integration**: INDI protocol support

### Technical Specifications

- **Processor**: Raspberry Pi Zero 2W (ARM Cortex-A53)
- **Camera**: IMX327 sensor (1920x1080)
- **Display**: 2.4" SPI LCD (240x320)
- **Software**: Python 3.9 + FastAPI

## Quick Start

### Requirements

- Python 3.9+
- Poetry 1.2+
- Raspberry Pi Zero 2W (Raspberry Pi OS)

### Installation

```bash
# Clone the project
git clone https://github.com/OG-star-tech/OGScope.git
cd OGScope

# Install dependencies (using Poetry)
poetry install

# Activate virtual environment
poetry shell

# Run the application
python -m ogscope.main
```

### Web Interface Access

After startup, visit: http://raspberrypi.local:8000 or http://<IP>:8000

## Documentation

### User Documentation
- [Quick Start](docs/QUICK_START_EN.md)
- [User Manual](docs/user_guide/user-manual.md)
- [FAQ](docs/user_guide/faq.md)

### Hardware Documentation
- [Bill of Materials (BOM)](docs/hardware/bom.md)
- [Assembly Guide](docs/hardware/assembly-guide.md)
- [Hardware Debugging](docs/hardware/hardware-debug.md)

### Development Documentation
- [Development Guide](docs/development/README.md)
- [PyCharm Remote Development](docs/development/pycharm-remote.md)
- [FastAPI Development](docs/development/fastapi-guide.md)
- [Testing Guide](docs/development/testing-guide.md)

## Development

See [Development Documentation](docs/development/README.md) for details.

### Remote Development Configuration (PyCharm Pro)

Recommended approach using PyCharm's file synchronization:

1. Configure SSH connection to Raspberry Pi Zero 2W
2. Set up automatic file synchronization to the development board
3. Develop locally, test hardware functions remotely
4. Detailed steps in [PyCharm File Sync Development Guide](docs/development/pycharm-remote.md)

## Project Structure

```
OGScope/
├── ogscope/           # Main application package
│   ├── core/         # Core functionality modules
│   ├── hardware/     # Hardware interface layer
│   ├── web/          # FastAPI web service
│   ├── ui/           # SPI screen interface
│   ├── algorithms/   # Astronomical algorithms
│   └── utils/        # Utility functions
├── tests/            # Test code
├── docs/             # Documentation
├── scripts/          # Deployment scripts
└── web/              # Web frontend resources
```


## License

This project is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)

- **Attribution (BY)**: Must credit the original author
- **NonCommercial (NC)**: Commercial use is prohibited
- **ShareAlike (SA)**: Derivative works must use the same license

See [LICENSE](LICENSE) file for details.

## Quick Links

- [GitHub Repository](https://github.com/OG-star-tech/OGScope)
- [Issue Tracker](https://github.com/OG-star-tech/OGScope/issues)
- [Discussions](https://github.com/OG-star-tech/OGScope/discussions)

## Contributing

Issues and Pull Requests are welcome! See [Contributing Guide](CONTRIBUTING.md) for details.

