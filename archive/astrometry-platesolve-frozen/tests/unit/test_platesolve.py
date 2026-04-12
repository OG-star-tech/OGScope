"""
板块求解单元测试 / Plate solver unit tests
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ogscope.algorithms.plate_solver import (
    PlateSolver,
    SolveOptions,
    SolveResult,
    SolveStatus,
)

# 测试图像目录 / Test images directory
TEST_IMAGES_DIR = Path(__file__).resolve().parents[1] / "images"


# ============================================================
# SolveResult 测试 / SolveResult tests
# ============================================================


@pytest.mark.unit
class TestSolveResult:
    """SolveResult 数据类测试 / SolveResult dataclass tests"""

    def test_default_is_failed(self):
        """默认结果为失败 / Default result is failed"""
        result = SolveResult()
        assert result.status == SolveStatus.FAILED
        assert not result.is_solved

    def test_is_solved_true(self):
        """成功结果 / Successful result"""
        result = SolveResult(status=SolveStatus.SUCCESS, ra=180.0, dec=45.0)
        assert result.is_solved

    def test_is_solved_false_without_ra(self):
        """成功状态但没有 RA 仍为未求解 / Success status without RA still unsolved"""
        result = SolveResult(status=SolveStatus.SUCCESS, ra=None, dec=45.0)
        assert not result.is_solved

    def test_ra_hms_format(self):
        """赤经 HMS 格式转换 / RA HMS format conversion"""
        # 180 degrees = 12 hours
        result = SolveResult(ra=180.0)
        assert result.ra_hms == "12h00m00.00s"

    def test_ra_hms_none(self):
        """无 RA 返回 None / No RA returns None"""
        result = SolveResult()
        assert result.ra_hms is None

    def test_dec_dms_positive(self):
        """正赤纬 DMS 格式 / Positive Dec DMS format"""
        result = SolveResult(dec=45.5)
        assert result.dec_dms is not None
        assert result.dec_dms.startswith("+45\u00b030'")

    def test_dec_dms_negative(self):
        """负赤纬 DMS 格式 / Negative Dec DMS format"""
        result = SolveResult(dec=-23.5)
        assert result.dec_dms is not None
        assert result.dec_dms.startswith("-23\u00b030'")

    def test_dec_dms_none(self):
        """无 Dec 返回 None / No Dec returns None"""
        result = SolveResult()
        assert result.dec_dms is None

    def test_to_dict(self):
        """转换为字典 / Convert to dict"""
        result = SolveResult(
            status=SolveStatus.SUCCESS,
            ra=37.95,
            dec=89.26,
            roll=120.5,
            fov=11.4,
            matches=15,
            logodds=150.0,
            total_time_ms=150.0,
        )
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["ra"] == 37.95
        assert d["dec"] == 89.26
        assert d["ra_hms"] is not None
        assert d["dec_dms"] is not None
        assert d["fov"] == 11.4
        assert d["matches"] == 15
        assert d["total_time_ms"] == 150.0
        assert d["logodds"] == 150.0


# ============================================================
# SolveOptions 测试 / SolveOptions tests
# ============================================================


@pytest.mark.unit
class TestSolveOptions:
    """SolveOptions 数据类测试 / SolveOptions dataclass tests"""

    def test_defaults(self):
        """默认参数 / Default parameters"""
        opts = SolveOptions()
        assert opts.fov_estimate is None
        assert opts.detection_sigma == 3.0
        assert opts.max_stars == 200
        assert opts.max_area == 500

    def test_custom_values(self):
        """自定义参数 / Custom parameters"""
        opts = SolveOptions(
            fov_estimate=11.0,
            fov_max_error=0.5,
            detection_sigma=5.0,
            max_area=300,
        )
        assert opts.fov_estimate == 11.0
        assert opts.fov_max_error == 0.5
        assert opts.detection_sigma == 5.0
        assert opts.max_area == 300


# ============================================================
# PlateSolver 测试 / PlateSolver tests
# ============================================================


@pytest.mark.unit
class TestPlateSolver:
    """PlateSolver 类测试 / PlateSolver class tests"""

    def test_init_defaults(self):
        """默认初始化 / Default initialization"""
        solver = PlateSolver()
        assert not solver.is_initialized

    def test_init_with_fov_defaults(self):
        """带默认 FOV 初始化 / Init with FOV defaults"""
        solver = PlateSolver(
            default_fov_estimate=11.0,
            default_fov_max_error=0.5,
        )
        assert solver._default_fov_estimate == 11.0
        assert solver._default_fov_max_error == 0.5

    @patch("ogscope.algorithms.plate_solver._ASTROMETRY_AVAILABLE", False)
    def test_is_available_false(self):
        """astrometry 不可用时返回 False / Returns False when astrometry unavailable"""
        solver = PlateSolver()
        assert not solver.is_available

    @patch("ogscope.algorithms.plate_solver._ASTROMETRY_AVAILABLE", False)
    def test_initialize_without_astrometry(self):
        """没有 astrometry 时初始化失败 / Init fails without astrometry"""
        solver = PlateSolver()
        assert not solver.initialize()
        assert not solver.is_initialized

    @patch("ogscope.algorithms.plate_solver._ASTROMETRY_AVAILABLE", False)
    def test_solve_without_init(self):
        """未初始化时求解返回错误 / Solve returns error when not initialized"""
        solver = PlateSolver()
        result = solver.solve_image(np.zeros((100, 100), dtype=np.uint8))
        assert result.status == SolveStatus.ERROR
        assert result.error_message is not None

    def test_solve_file_not_found(self):
        """求解不存在的文件 / Solve nonexistent file"""
        solver = PlateSolver()
        result = solver.solve_file("/nonexistent/path.png")
        assert result.status == SolveStatus.ERROR
        assert "\u4e0d\u5b58\u5728" in result.error_message or "not found" in result.error_message.lower()

    def test_extract_stars_empty_image(self):
        """空图像无星点 / Empty image has no stars"""
        solver = PlateSolver()
        gray = np.zeros((100, 100), dtype=np.uint8)
        stars = solver._extract_stars(gray, SolveOptions())
        assert len(stars) == 0

    def test_extract_stars_bright_spots(self):
        """检测亮点 / Detect bright spots"""
        import cv2

        solver = PlateSolver()
        gray = np.zeros((200, 200), dtype=np.uint8)
        cv2.circle(gray, (50, 50), 3, 255, -1)
        cv2.circle(gray, (100, 100), 3, 255, -1)
        cv2.circle(gray, (150, 150), 3, 255, -1)
        stars = solver._extract_stars(gray, SolveOptions(detection_sigma=2.0))
        assert len(stars) >= 3

    def test_solve_image_no_stars(self):
        """无星点图像求解 / Solve image with no stars"""
        solver = PlateSolver()
        solver._initialized = True
        solver._solver = MagicMock()
        result = solver.solve_image(np.zeros((100, 100), dtype=np.uint8))
        assert result.status == SolveStatus.NO_STARS

    def test_solve_bytes_invalid(self):
        """无效字节数据 / Invalid bytes data"""
        solver = PlateSolver()
        solver._initialized = True
        solver._solver = MagicMock()

        result = solver.solve_bytes(b"not an image")
        assert result.status == SolveStatus.ERROR

    def test_build_size_hint_with_fov(self):
        """FOV 转 SizeHint / FOV to SizeHint"""
        solver = PlateSolver()
        opts = SolveOptions(fov_estimate=10.0, fov_max_error=2.0)
        with patch("ogscope.algorithms.plate_solver._ASTROMETRY_AVAILABLE", True):
            with patch("ogscope.algorithms.plate_solver.astrometry") as mock_astro:
                mock_astro.SizeHint = MagicMock()
                solver._build_size_hint(opts, 1920, 1080)
                mock_astro.SizeHint.assert_called_once()

    def test_build_position_hint(self):
        """位置提示构建 / Position hint construction"""
        solver = PlateSolver()
        opts = SolveOptions(hint_ra=180.0, hint_dec=45.0, hint_radius=5.0)
        with patch("ogscope.algorithms.plate_solver._ASTROMETRY_AVAILABLE", True):
            with patch("ogscope.algorithms.plate_solver.astrometry") as mock_astro:
                mock_astro.PositionHint = MagicMock()
                solver._build_position_hint(opts)
                mock_astro.PositionHint.assert_called_once_with(
                    ra_deg=180.0, dec_deg=45.0, radius_deg=5.0
                )

    def test_to_grayscale_gray(self):
        """灰度图转换 / Grayscale conversion"""
        gray = np.zeros((100, 100), dtype=np.uint8)
        result = PlateSolver._to_grayscale(gray)
        assert result is not None
        assert result.shape == (100, 100)

    def test_to_grayscale_bgr(self):
        """BGR 图转灰度 / BGR to grayscale"""
        bgr = np.zeros((100, 100, 3), dtype=np.uint8)
        result = PlateSolver._to_grayscale(bgr)
        assert result is not None
        assert len(result.shape) == 2

    def test_to_cv2_image_bytes(self):
        """字节转 OpenCV 图像 / Bytes to OpenCV image"""
        from PIL import Image
        import io

        img = Image.new("RGB", (50, 50), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        result = PlateSolver._to_cv2_image(buf.getvalue())
        assert result is not None
        assert result.shape[2] == 3


# ============================================================
# API 路由测试 / API route tests
# ============================================================


@pytest.mark.unit
class TestPlateSolveAPI:
    """板块求解 API 测试 / Plate solve API tests"""

    def test_status_endpoint(self, client):
        """求解器状态端点 / Solver status endpoint"""
        response = client.get("/api/platesolve/status")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert "initialized" in data

    def test_file_endpoint_not_found(self, client):
        """文件不存在 / File not found"""
        response = client.post(
            "/api/platesolve/file",
            params={"file_path": "/nonexistent/image.png"},
        )
        assert response.status_code in (403, 503)

    def test_file_endpoint_path_traversal(self, client):
        """路径穿越攻击防护 / Path traversal protection"""
        response = client.post(
            "/api/platesolve/file",
            params={"file_path": "/etc/passwd"},
        )
        assert response.status_code in (403, 503)

    def test_upload_empty_file(self, client):
        """上传空文件 / Upload empty file"""
        import io

        response = client.post(
            "/api/platesolve/upload",
            files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
        )
        # 400 (空文件) 或 503 (astrometry 不可用) / 400 (empty) or 503 (unavailable)
        assert response.status_code in (400, 503)
