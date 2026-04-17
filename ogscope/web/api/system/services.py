"""
系统信息服务兼容导出 / Compatibility exports for system services.
"""

from ogscope.domain.system.services import SystemInfoService, read_systemd_logs, system_info_service

__all__ = ["SystemInfoService", "system_info_service", "read_systemd_logs"]
