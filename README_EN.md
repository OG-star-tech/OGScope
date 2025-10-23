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

## Contributing

Issues and Pull Requests are welcome!

