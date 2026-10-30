"""中性类型独立加载，旧服务导出按需解析 / Load neutral types without eagerly loading services."""

__all__ = ["DebugCameraService", "DebugFileService", "DebugPresetService"]


def __getattr__(name):
    """保留既有导入路径，避免组合入口循环依赖 / Preserve legacy exports without composition cycles."""
    if name in __all__:
        from ogscope.domain.camera import services

        return getattr(services, name)
    raise AttributeError(name)
