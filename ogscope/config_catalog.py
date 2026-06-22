"""
配置项目录（供 Web 配置页与示例文件引用）/ Config catalog for Web UI and examples.
"""

from __future__ import annotations

from typing import Any, Literal

from ogscope.config import Settings

ConfigFileScope = Literal["ogscope", "network", "both"]

_CATALOG_SECTIONS: tuple[tuple[str, str, str, ConfigFileScope, tuple[str, ...]], ...] = (
    (
        "basic",
        "基础",
        "Basic",
        "ogscope",
        (
            "environment",
            "debug",
            "development_mode",
            "log_level",
            "log_file",
            "simulation_mode",
            "force_exit_on_shutdown",
        ),
    ),
    (
        "web",
        "Web 服务",
        "Web service",
        "ogscope",
        ("host", "port", "reload"),
    ),
    (
        "hardware_plane",
        "硬件平面",
        "Hardware plane",
        "ogscope",
        (
            "hardware_plane_enabled",
            "hardware_plane_role",
            "hardware_plane_rpc_timeout_ms",
            "hardware_plane_uds_socket",
            "hardware_plane_remote_uds_socket",
            "hardware_plane_camera_autostart",
            "enable_local_sensors",
            "enable_hmi",
            "enable_ui",
            "subordinate_local_dev_only",
        ),
    ),
    (
        "camera",
        "相机",
        "Camera",
        "ogscope",
        (
            "camera_type",
            "camera_width",
            "camera_height",
            "camera_fps",
            "camera_sampling_mode",
            "camera_exposure",
            "camera_gain",
            "camera_ae_polar_preset",
            "camera_ae_exposure_value",
            "camera_auto_exposure_max_us",
            "camera_ae_flicker_mode",
            "camera_noise_reduction_mode",
            "camera_lores_enabled",
            "camera_lores_width",
            "camera_lores_height",
            "camera_lores_format",
            "camera_flip_horizontal",
            "camera_flip_vertical",
            "camera_white_balance_mode",
            "camera_white_balance_gain_r",
            "camera_white_balance_gain_b",
            "camera_night_mode",
        ),
    ),
    (
        "preview",
        "预览与抓帧",
        "Preview & grabber",
        "ogscope",
        (
            "shared_preview_fps",
            "preview_jpeg_quality",
            "preview_encoder",
            "debug_preview_min_interval_ms",
            "camera_probe_timeout_sec",
            "camera_grab_failures_offline",
            "camera_idle_shutdown_sec",
            "camera_frame_stale_timeout_sec",
            "keep_raw_cache",
            "stream_max_mjpeg_clients",
            "stream_mjpeg_frame_fetch_timeout_ms",
        ),
    ),
    (
        "display",
        "SPI 屏幕",
        "SPI display",
        "ogscope",
        (
            "display_enabled",
            "display_type",
            "display_width",
            "display_height",
            "display_rotation",
            "display_dc_pin",
            "display_spi_max_speed_hz",
        ),
    ),
    (
        "polar",
        "极轴校准",
        "Polar alignment",
        "ogscope",
        ("polar_align_timeout", "polar_align_precision"),
    ),
    (
        "paths",
        "路径与数据",
        "Paths & data",
        "ogscope",
        (
            "database_url",
            "data_dir",
            "upload_dir",
            "analysis_dir",
            "plate_solve_dir",
            "solver_tetra_database_path",
            "static_dir",
        ),
    ),
    (
        "solver",
        "星图解算",
        "Plate solve",
        "ogscope",
        (
            "solver_hint_ra_deg",
            "solver_hint_dec_deg",
            "solver_fov_deg",
            "solver_max_stars",
            "solver_fullsolve_interval_frames",
            "solver_centroid_sigma",
            "solver_centroid_max_area",
            "solver_centroid_min_area",
            "solver_centroid_filtsize",
            "solver_centroid_binary_open",
            "solver_centroid_bg_sub_mode",
            "solver_centroid_sigma_mode",
            "solver_centroid_max_axis_ratio",
            "solver_max_image_side",
            "solver_max_stars_hard_cap",
            "solver_max_image_side_hard_cap",
            "solver_large_scale_bg_downsample",
            "solver_fov_max_error_deg",
            "solver_timeout_ms",
        ),
    ),
    (
        "star_analysis",
        "实时星空分析",
        "Realtime star analysis",
        "ogscope",
        (
            "star_analysis_target_fps",
            "star_analysis_min_interval_ms",
            "star_analysis_max_interval_ms",
            "star_analysis_request_timeout_ms",
            "star_analysis_slow_threshold_ms",
        ),
    ),
    (
        "wifi",
        "WiFi 运行时",
        "WiFi runtime",
        "both",
        (
            "wifi_switch_script",
            "wifi_switch_use_sudo",
            "wifi_switch_timeout_seconds",
            "wifi_nmcli_use_sudo",
            "wifi_sta_connection",
            "wifi_ap_connection",
            "wifi_interface",
            "wifi_ap_url_host",
            "wifi_emergency_gpio_enabled",
            "wifi_emergency_pin_out_bcm",
            "wifi_emergency_pin_in_bcm",
            "wifi_emergency_hold_seconds",
            "device_id_suffix",
            "wifi_ap_ssid",
            "wifi_sta_rollback_timeout_seconds",
            "wifi_sta_rollback_interval_seconds",
        ),
    ),
)

_NETWORK_ONLY_KEYS: tuple[tuple[str, str, str, str], ...] = (
    (
        "OGSCOPE_WIFI_STA_SSID",
        "STA 目标 WiFi SSID（NetworkManager 连接配置参考）。",
        "Target STA WiFi SSID (reference for NM profile).",
        "network",
    ),
    (
        "OGSCOPE_WIFI_STA_PASSWORD",
        "STA 目标 WiFi 密码（NetworkManager 连接配置参考）。",
        "Target STA WiFi password (reference for NM profile).",
        "network",
    ),
    (
        "OGSCOPE_BOOT_STA_WAIT_SEC",
        "开机引导：等待 STA 获得 IPv4 的总秒数（ogscope-network-boot）。",
        "Boot script: seconds to wait for STA IPv4 (ogscope-network-boot).",
        "network",
    ),
    (
        "OGSCOPE_BOOT_POLL_SEC",
        "开机引导：IPv4 轮询间隔（秒）。",
        "Boot script: IPv4 poll interval in seconds.",
        "network",
    ),
    (
        "OGSCOPE_BOOT_STA_UP_RETRIES",
        "开机引导：尝试 nmcli up STA 的次数。",
        "Boot script: nmcli STA up retry count.",
        "network",
    ),
    (
        "OGSCOPE_BOOT_POST_UP_WAIT",
        "开机引导：每次 up STA 后再等待的秒数。",
        "Boot script: wait seconds after each STA up.",
        "network",
    ),
)


def _field_default_repr(field_name: str) -> str | None:
    field = Settings.model_fields.get(field_name)
    if field is None:
        return None
    default = field.default
    if default is None and field.default_factory is not None:
        try:
            default = field.default_factory()  # type: ignore[misc]
        except Exception:
            return None
    if default is None:
        return None
    return str(default)


def _split_description(description: str | None) -> tuple[str, str]:
    if not description:
        return "", ""
    if " / " in description:
        zh, en = description.split(" / ", 1)
        return zh.strip(), en.strip()
    return description.strip(), description.strip()


def build_config_catalog() -> dict[str, Any]:
    """构建配置目录 JSON / Build config catalog payload for API consumers."""
    sections: list[dict[str, Any]] = []
    for section_id, title_zh, title_en, scope, field_names in _CATALOG_SECTIONS:
        entries: list[dict[str, Any]] = []
        for field_name in field_names:
            model_field = Settings.model_fields.get(field_name)
            if model_field is None:
                continue
            zh, en = _split_description(model_field.description)
            entries.append(
                {
                    "key": f"OGSCOPE_{field_name.upper()}",
                    "field": field_name,
                    "scope": scope,
                    "default": _field_default_repr(field_name),
                    "zh": zh,
                    "en": en,
                }
            )
        sections.append(
            {
                "id": section_id,
                "title_zh": title_zh,
                "title_en": title_en,
                "scope": scope,
                "entries": entries,
            }
        )

    network_only = [
        {
            "key": key,
            "scope": scope,
            "default": None,
            "zh": zh,
            "en": en,
        }
        for key, zh, en, scope in _NETWORK_ONLY_KEYS
    ]

    return {
        "env_prefix": "OGSCOPE_",
        "env_files": {
            "ogscope": "/etc/ogscope/ogscope.env",
            "network": "/etc/ogscope/network.env",
            "local": ".env",
        },
        "sections": sections,
        "network_only": network_only,
    }
