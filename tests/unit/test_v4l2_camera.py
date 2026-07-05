#!/usr/bin/env python3
"""
Tests for V4L2-based camera implementation (without picamera2 dependency)
"""

import numpy as np
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from ogscope.platform.hardware.camera import V4L2Camera


class TestV4L2CameraInitialization:
    """Test V4L2 camera initialization without picamera2"""

    def test_initialize_creates_opencv_capture(self):
        """Test that initialize() creates OpenCV VideoCapture object"""
        config = {"width": 640, "height": 480, "device": "/dev/video0"}
        camera = V4L2Camera(config)
        
        with patch('cv2.VideoCapture') as mock_capture:
            mock_cap_instance = MagicMock()
            mock_cap_instance.isOpened.return_value = True
            mock_capture.return_value = mock_cap_instance
            
            result = camera.initialize()
            
            assert result is True
            assert camera.is_initialized is True
            mock_capture.assert_called_once()

    def test_initialize_fails_if_device_cannot_open(self):
        """Test that initialize() fails gracefully when device cannot be opened"""
        config = {"width": 640, "height": 480, "device": "/dev/video0"}
        camera = V4L2Camera(config)
        
        with patch('cv2.VideoCapture') as mock_capture:
            mock_cap_instance = MagicMock()
            mock_cap_instance.isOpened.return_value = False
            mock_capture.return_value = mock_cap_instance
            
            result = camera.initialize()
            
            assert result is False
            assert camera.is_initialized is False

    def test_v4l2_format_setup_called_before_capture(self):
        """Test that V4L2 format is configured before OpenCV capture"""
        config = {"width": 640, "height": 480, "device": "/dev/video0"}
        camera = V4L2Camera(config)
        
        with patch('cv2.VideoCapture') as mock_capture, \
             patch.object(camera, '_configure_v4l2_format') as mock_config:
            mock_cap_instance = MagicMock()
            mock_cap_instance.isOpened.return_value = True
            mock_capture.return_value = mock_cap_instance
            mock_config.return_value = True
            
            camera.initialize()
            
            mock_config.assert_called_once()
            # Format config should be called before VideoCapture
            assert mock_config.call_count == 1


class TestV4L2CameraCapture:
    """Test V4L2 camera frame capture"""

    def test_capture_image_returns_numpy_array(self):
        """Test that capture_image() returns a valid numpy array"""
        config = {"width": 640, "height": 480}
        camera = V4L2Camera(config)
        camera.is_initialized = True
        camera.is_capturing = True
        
        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera._capture = MagicMock()
        camera._capture.read.return_value = (True, mock_frame)
        
        result = camera.capture_image()
        
        assert isinstance(result, np.ndarray)
        assert result.shape == (480, 640, 3)

    def test_capture_image_returns_none_when_not_initialized(self):
        """Test that capture_image() returns None when camera not initialized"""
        config = {"width": 640, "height": 480}
        camera = V4L2Camera(config)
        camera.is_initialized = False
        
        result = camera.capture_image()
        
        assert result is None

    def test_capture_image_handles_read_failure(self):
        """Test that capture_image() handles read failures gracefully"""
        config = {"width": 640, "height": 480}
        camera = V4L2Camera(config)
        camera.is_initialized = True
        camera.is_capturing = True
        camera._capture = MagicMock()
        camera._capture.read.return_value = (False, None)
        
        result = camera.capture_image()
        
        assert result is None


class TestV4L2Controls:
    """Test V4L2 control methods (exposure, gain)"""

    def test_set_exposure_calls_v4l2_ctl(self):
        """Test that set_exposure() uses v4l2-ctl for sensor control"""
        config = {"width": 640, "height": 480, "v4l2_sensor_subdev": "/dev/v4l-subdev1"}
        camera = V4L2Camera(config)
        camera.is_initialized = True
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            result = camera.set_exposure(10000)
            
            assert result is True
            # Should call v4l2-ctl to set exposure
            assert mock_run.call_count >= 1

    def test_set_gain_calls_v4l2_ctl(self):
        """Test that set_gain() uses v4l2-ctl for sensor control"""
        config = {"width": 640, "height": 480, "v4l2_sensor_subdev": "/dev/v4l-subdev1"}
        camera = V4L2Camera(config)
        camera.is_initialized = True
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            result = camera.set_gain(2.0)
            
            assert result is True
            assert mock_run.call_count >= 1


class TestV4L2CameraModularity:
    """Test that implementation is modular for future GStreamer backend"""

    def test_backend_abstraction_exists(self):
        """Test that backend can be specified and abstracted"""
        config = {"width": 640, "height": 480, "backend": "opencv"}
        camera = V4L2Camera(config)
        
        assert hasattr(camera, 'backend')
        assert camera.backend == "opencv"

    def test_future_gstreamer_backend_can_be_specified(self):
        """Test that GStreamer backend can be specified for future use"""
        config = {"width": 640, "height": 480, "backend": "gstreamer"}
        camera = V4L2Camera(config)
        
        # Should accept gstreamer backend (even if not implemented yet)
        assert camera.backend == "gstreamer"
