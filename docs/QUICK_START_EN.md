# OGScope Quick Start Guide

This guide will help you quickly set up the OGScope development environment.

English | [中文](QUICK_START.md)

## 🎯 Goals

- ✅ Run OGScope on Raspberry Pi Zero 2W
- ✅ Configure PyCharm Professional remote development
- ✅ Access the system through web interface

## 📋 Prerequisites

### Hardware Requirements

- Raspberry Pi Zero 2W development board
- IMX327 camera module
- 2.4" SPI LCD display
- MicroSD card (32GB+)
- Power supply (5V/2A)

### Software Requirements

- macOS/Windows/Linux development machine
- PyCharm Professional 2025
- Python 3.9+
- Poetry package manager

## 🚀 Installation Steps

### Step 1: Prepare Raspberry Pi Zero 2W

1. **Flash the OS**
   ```bash
   # Download Raspberry Pi OS image for Raspberry Pi Zero 2W
   # Flash to microSD card using balenaEtcher
   ```

2. **Initial Setup**
   ```bash
   # Boot the board and connect via SSH
   ssh pi@orangepi.local
   
   # Update system
   sudo apt update && sudo apt upgrade -y
   
   # Install essential packages
   sudo apt install -y python3.9 python3-pip python3-venv git
   ```

3. **Install Poetry**
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

### Step 2: Clone and Setup Project

```bash
# Clone the repository
git clone https://github.com/OG-star-tech/OGScope.git
cd OGScope

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

### Step 3: Configure PyCharm

1. **Open Project**
   - Launch PyCharm Professional
   - Open the OGScope project directory

2. **Configure File Sync**
   - Go to `Tools` → `Deployment` → `Configuration`
   - Add SFTP server for Raspberry Pi Zero 2W
   - Configure automatic file synchronization

3. **Setup Run Configurations**
   - Create local run configuration for development
   - Create remote run configuration for hardware testing

### Step 4: Run the Application

```bash
# Local development
python -m ogscope.main

# Remote testing (on Raspberry Pi)
ssh orangepi
cd /home/pi/OGScope
poetry run python -m ogscope.main
```

## 🌐 Access Web Interface

After starting the application, access:
- Local: http://localhost:8000
- Remote: http://orangepi.local:8000

## 🔧 Development Workflow

1. **Local Development**
   - Write code in PyCharm
   - Test basic functionality locally
   - Use local run configuration

2. **File Synchronization**
   - Files automatically sync to Raspberry Pi
   - Manual sync when needed

3. **Hardware Testing**
   - Switch to remote run configuration
   - Test camera and hardware features
   - Debug on actual hardware

## 📚 Next Steps

- Read [Development Guide](development/README.md)
- Check [PyCharm Remote Development](development/pycharm-remote.md)
- Explore [API Documentation](API_ARCHITECTURE.md)

## 🆘 Troubleshooting

### Common Issues

1. **Connection Problems**
   ```bash
   # Check network connectivity
   ping orangepi.local
   
   # Verify SSH connection
   ssh orangepi
   ```

2. **Permission Issues**
   ```bash
   # Fix camera permissions
   sudo usermod -a -G video pi
   sudo reboot
   ```

3. **Dependency Issues**
   ```bash
   # Reinstall dependencies
   poetry install --sync
   ```

## 📞 Support

- [GitHub Issues](https://github.com/OG-star-tech/OGScope/issues)
- [Discussions](https://github.com/OG-star-tech/OGScope/discussions)
- [Documentation](README.md)
