"""配置到相机后端参数的映射 / Map settings to camera backend parameters."""

from typing import Any


def build_camera_config(
    settings: Any, overrides: dict[str, Any], capture_timeout_sec: float
) -> dict[str, Any]:
    """保留后端默认值及运行覆盖的合并顺序 / Preserve backend defaults and runtime override precedence."""
    base = {
        # Picamera2/libcamera 是默认产品路径；V4L2 RAW 必须显式启用。
        # Picamera2/libcamera remains the default; V4L2 RAW requires opt-in.
        "type": settings.camera_type,
        "device": settings.camera_device,
        "v4l2_sensor_subdev": settings.camera_v4l2_sensor_subdev,
        "v4l2_media_device": settings.camera_v4l2_media_device,
        "v4l2_configure_media_pipeline": (
            settings.camera_v4l2_configure_media_pipeline
        ),
        "v4l2_sensor_entity": settings.camera_v4l2_sensor_entity,
        "v4l2_receiver_entity": settings.camera_v4l2_receiver_entity,
        "v4l2_sensor_pad": settings.camera_v4l2_sensor_pad,
        "v4l2_receiver_sink_pad": settings.camera_v4l2_receiver_sink_pad,
        "v4l2_receiver_source_pad": settings.camera_v4l2_receiver_source_pad,
        "v4l2_media_bus_format": settings.camera_v4l2_media_bus_format,
        "v4l2_pixel_format": settings.camera_v4l2_pixel_format,
        "v4l2_bit_depth": settings.camera_v4l2_bit_depth,
        "v4l2_black_level": settings.camera_v4l2_black_level,
        "v4l2_white_level": settings.camera_v4l2_white_level,
        "v4l2_bayer_pattern": settings.camera_v4l2_bayer_pattern,
        "v4l2_gamma": settings.camera_v4l2_gamma,
        "v4l2_temporal_nr_alpha": getattr(
            settings, "camera_v4l2_temporal_nr_alpha", 1.0
        ),
        "v4l2_temporal_nr_seconds": settings.camera_v4l2_temporal_nr_seconds,
        "v4l2_temporal_nr_max_frames": (settings.camera_v4l2_temporal_nr_max_frames),
        "v4l2_active_width": settings.camera_v4l2_active_width,
        "v4l2_active_height": settings.camera_v4l2_active_height,
        "v4l2_line_duration_us": settings.camera_v4l2_line_duration_us,
        "v4l2_gain_db_per_step": settings.camera_v4l2_gain_db_per_step,
        "v4l2_auto_gain_max": settings.camera_v4l2_auto_gain_max,
        "v4l2_ae_max_step_stops": settings.camera_v4l2_ae_max_step_stops,
        "v4l2_ae_target_background": (settings.camera_v4l2_ae_target_background),
        "v4l2_ae_target_highlight": settings.camera_v4l2_ae_target_highlight,
        "v4l2_ae_highlight_percentile": (settings.camera_v4l2_ae_highlight_percentile),
        "v4l2_ae_trace_enabled": settings.camera_v4l2_ae_trace_enabled,
        "v4l2_ae_trace_dir": str(
            settings.camera_v4l2_ae_trace_dir
            or (settings.data_dir / "camera-ae-traces")
        ),
        "v4l2_ae_trace_max_events": settings.camera_v4l2_ae_trace_max_events,
        "v4l2_ae_trace_raw_sample_interval": (
            settings.camera_v4l2_ae_trace_raw_sample_interval
        ),
        "v4l2_ae_trace_max_raw_samples": (
            settings.camera_v4l2_ae_trace_max_raw_samples
        ),
        "v4l2_ae_trace_raw_max_side": (settings.camera_v4l2_ae_trace_raw_max_side),
        "width": settings.camera_width,
        "height": settings.camera_height,
        "fps": max(1, int(getattr(settings, "camera_fps", 5) or 5)),
        "exposure_us": settings.camera_exposure,
        "analogue_gain": settings.camera_gain,
        "auto_exposure": True,
        "ae_polar_preset": settings.camera_ae_polar_preset,
        "ae_exposure_value": settings.camera_ae_exposure_value,
        "ae_aggressive_enabled": settings.camera_ae_aggressive_enabled,
        "tuning_file": (
            str(settings.camera_tuning_file)
            if getattr(settings, "camera_tuning_file", None)
            else None
        ),
        "auto_exposure_max_us": getattr(
            settings, "camera_auto_exposure_max_us", 3_000_000
        ),
        "capture_timeout_sec": capture_timeout_sec,
        "ae_flicker_mode": getattr(settings, "camera_ae_flicker_mode", "off"),
        "noise_reduction_mode": getattr(
            settings, "camera_noise_reduction_mode", "fast"
        ),
        "lores_enabled": bool(getattr(settings, "camera_lores_enabled", True)),
        "lores_width": int(getattr(settings, "camera_lores_width", 320)),
        "lores_height": int(getattr(settings, "camera_lores_height", 240)),
        "lores_format": getattr(settings, "camera_lores_format", "YUV420"),
        "rotation": settings.camera_rotation,
        "hardware_transform": settings.camera_hardware_transform,
        "v4l2_processing": settings.camera_v4l2_processing,
        "v4l2_isp_input_device": settings.camera_v4l2_isp_input_device,
        "v4l2_isp_output_device": settings.camera_v4l2_isp_output_device,
        "v4l2_isp_timeout_sec": settings.camera_v4l2_isp_timeout_sec,
        "flip_horizontal": bool(getattr(settings, "camera_flip_horizontal", False)),
        "flip_vertical": bool(getattr(settings, "camera_flip_vertical", False)),
        "sampling_mode": getattr(settings, "camera_sampling_mode", "native"),
        "noise_reduction": 1,
        "white_balance_mode": getattr(settings, "camera_white_balance_mode", "auto"),
        "white_balance_gain_r": getattr(settings, "camera_white_balance_gain_r", 1.0),
        "white_balance_gain_b": getattr(settings, "camera_white_balance_gain_b", 1.0),
        "contrast": 1.0,
        "brightness": 0.0,
        "saturation": 1.0,
        "sharpness": 1.0,
        "night_mode": bool(getattr(settings, "camera_night_mode", False)),
        "color_mode": "color",
    }
    return {**base, **overrides}
