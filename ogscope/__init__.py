"""
OGScope - 电子极轴镜

基于 Orange Pi Zero 2W 和 IMX327 的智能极轴校准系统
"""

# 使 vendored tetra3 可被 import / Make vendored tetra3 importable
import sys
from pathlib import Path

_vendor_root = Path(__file__).resolve().parent / "vendor"
if _vendor_root.is_dir() and str(_vendor_root) not in sys.path:
    sys.path.insert(0, str(_vendor_root))

from ogscope.__version__ import __version__

__all__ = ["__version__"]

