"""
星图解算模块导出 / Plate solving module exports
"""

from ogscope.algorithms.plate_solve.solver import (
    PlateSolver,
    SolveResult,
    reset_tetra3_singleton_for_tests,
)

__all__ = ["PlateSolver", "SolveResult", "reset_tetra3_singleton_for_tests"]
