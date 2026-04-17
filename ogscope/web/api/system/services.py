"""
系统信息服务兼容导出 / Compatibility exports for system services.
"""

from ogscope.domain.system import services as _domain_services

SystemInfoService = _domain_services.SystemInfoService
read_systemd_logs = _domain_services.read_systemd_logs
system_info_service = _domain_services.system_info_service
# 兼容测试对模块级 Path monkeypatch / Keep module-level Path for tests.
Path = _domain_services.Path

__all__ = ["SystemInfoService", "system_info_service", "read_systemd_logs", "Path"]
