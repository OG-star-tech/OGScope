"""
调试服务适配器 / Adapter for debug service implementation.
"""

from __future__ import annotations

import importlib


def get_debug_services_module():
    """延迟加载调试实现模块 / Lazy load debug implementation module."""
    return importlib.import_module("ogscope.web.api.debug.services")
