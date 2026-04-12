"""
板块求解算法模块 / Plate solving algorithm module

基于 astrometry (astrometry.net Python 封装) 实现天文图像的板块求解，
用于确定图像中心的天球坐标 (RA/Dec)。
Based on astrometry (astrometry.net Python wrapper) for astronomical image plate solving,
determining the celestial coordinates (RA/Dec) of the image center.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
from loguru import logger

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment,misc]

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

# astrometry 包可用性检查 / astrometry package availability check
_ASTROMETRY_AVAILABLE = False
try:
    import astrometry

    _ASTROMETRY_AVAILABLE = True
except ImportError:
    astrometry = None  # type: ignore[assignment]


class SolveStatus(str, Enum):
    """求解状态 / Solve status"""

    SUCCESS = "success"
    FAILED = "failed"
    NO_STARS = "no_stars"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class SolveResult:
    """板块求解结果 / Plate solve result

    包含图像中心的天球坐标和求解元数据。
    Contains celestial coordinates of the image center and solve metadata.
    """

    # 求解状态 / Solve status
    status: SolveStatus = SolveStatus.FAILED

    # 图像中心天球坐标 / Image center celestial coordinates
    ra: Optional[float] = None  # 赤经 (度) / Right ascension (degrees)
    dec: Optional[float] = None  # 赤纬 (度) / Declination (degrees)
    roll: Optional[float] = None  # 相对北天极的旋转角 (度) / Roll relative to NCP (degrees)

    # 视场信息 / Field of view info
    fov: Optional[float] = None  # 水平视场角 (度) / Horizontal FOV (degrees)
    scale_arcsec_per_pixel: Optional[float] = None  # 像素比例 (角秒/像素) / Pixel scale (arcsec/pixel)

    # 求解质量 / Solve quality metrics
    logodds: Optional[float] = None  # 对数赔率 / Log-odds of match
    matches: Optional[int] = None  # 匹配星数 / Number of matched stars

    # 性能信息 / Performance info
    solve_time_ms: Optional[float] = None  # 求解耗时 (ms) / Solve time (ms)
    extract_time_ms: Optional[float] = None  # 星点提取耗时 (ms) / Extraction time (ms)
    total_time_ms: Optional[float] = None  # 总耗时 (ms) / Total time (ms)

    # 匹配的星点 / Matched stars
    matched_stars: Optional[list] = None  # [(ra_deg, dec_deg, metadata), ...]
    matched_centroids: Optional[list] = None  # [(x, y), ...]
    detected_stars: int = 0  # 检测到的星点数 / Number of detected stars

    # 叠加层图像 / Overlay annotated image
    annotated_image: Optional[bytes] = None  # JPEG 字节 / JPEG bytes

    # 错误信息 / Error info
    error_message: Optional[str] = None

    @property
    def is_solved(self) -> bool:
        """是否求解成功 / Whether solve succeeded"""
        return self.status == SolveStatus.SUCCESS and self.ra is not None

    @property
    def ra_hms(self) -> Optional[str]:
        """赤经 HMS 格式 / RA in HMS format"""
        if self.ra is None:
            return None
        hours = self.ra / 15.0
        h = int(hours)
        m = int((hours - h) * 60)
        s = ((hours - h) * 60 - m) * 60
        return f"{h:02d}h{m:02d}m{s:05.2f}s"

    @property
    def dec_dms(self) -> Optional[str]:
        """赤纬 DMS 格式 / Dec in DMS format"""
        if self.dec is None:
            return None
        sign = "+" if self.dec >= 0 else "-"
        dec_abs = abs(self.dec)
        d = int(dec_abs)
        m = int((dec_abs - d) * 60)
        s = ((dec_abs - d) * 60 - m) * 60
        return f"{sign}{d:02d}°{m:02d}'{s:05.2f}\""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典 / Convert to dictionary"""
        return {
            "status": self.status.value,
            "ra": self.ra,
            "dec": self.dec,
            "roll": self.roll,
            "ra_hms": self.ra_hms,
            "dec_dms": self.dec_dms,
            "fov": self.fov,
            "scale_arcsec_per_pixel": self.scale_arcsec_per_pixel,
            "logodds": self.logodds,
            "matches": self.matches,
            "detected_stars": self.detected_stars,
            "solve_time_ms": self.solve_time_ms,
            "extract_time_ms": self.extract_time_ms,
            "total_time_ms": self.total_time_ms,
            "error_message": self.error_message,
        }


@dataclass
class SolveOptions:
    """板块求解参数 / Plate solve options"""

    # 像素比例提示 (角秒/像素) / Pixel scale hints (arcsec/pixel)
    fov_estimate: Optional[float] = None  # 视场角估计 (度) / FOV estimate (degrees)
    fov_max_error: Optional[float] = None  # 视场角误差 (度) / FOV max error (degrees)

    # 位置提示 / Position hint
    hint_ra: Optional[float] = None  # 提示赤经 (度) / Hint RA (degrees)
    hint_dec: Optional[float] = None  # 提示赤纬 (度) / Hint Dec (degrees)
    hint_radius: Optional[float] = None  # 搜索半径 (度) / Search radius (degrees)

    # 星点提取参数 / Star extraction parameters
    detection_sigma: float = 3.0  # 检测阈值倍数 / Detection threshold multiplier
    max_stars: int = 200  # 最大星点数 / Max number of stars to extract
    min_area: int = 3  # 最小星点面积 (像素) / Min star area (pixels)
    max_area: int = 500  # 最大星点面积 (像素) / Max star area (pixels)

    # 叠加层绘制 / Overlay drawing
    draw_overlay: bool = False  # 在图像上绘制求解叠加层 / Draw solve overlay on image


class PlateSolver:
    """天文图像板块求解器 / Astronomical image plate solver

    使用 astrometry (astrometry.net) 对天文图像进行板块求解，
    确定图像中心在天球上的位置 (RA/Dec)。
    Uses astrometry (astrometry.net) to plate solve astronomical images,
    determining the image center's position on the celestial sphere (RA/Dec).

    用法 / Usage:
        solver = PlateSolver()
        result = solver.solve_file("path/to/star_image.png")
        if result.is_solved:
            print(f"中心: RA={result.ra_hms}, Dec={result.dec_dms}")
    """

    # 默认索引文件缓存目录 / Default index file cache directory
    DEFAULT_CACHE_DIR = Path.home() / ".cache" / "ogscope" / "astrometry"
    # 默认使用 series_4100 (宽视场 >1°) / Default series_4100 (wide FOV >1°)
    DEFAULT_SCALES = {7, 8, 9, 10, 11, 12}

    def __init__(
        self,
        cache_dir: Optional[Union[str, Path]] = None,
        scales: Optional[set[int]] = None,
        default_fov_estimate: Optional[float] = None,
        default_fov_max_error: Optional[float] = None,
    ):
        """初始化板块求解器 / Initialize plate solver

        Args:
            cache_dir: 索引文件缓存目录 / Index file cache directory
            scales: 使用的索引比例集合 / Set of index scales to use
            default_fov_estimate: 默认视场角估计 (度) / Default FOV estimate (degrees)
            default_fov_max_error: 默认视场角误差 (度) / Default FOV max error (degrees)
        """
        self._solver: Any = None
        self._cache_dir = Path(cache_dir) if cache_dir else self.DEFAULT_CACHE_DIR
        self._scales = scales or self.DEFAULT_SCALES
        self._default_fov_estimate = default_fov_estimate
        self._default_fov_max_error = default_fov_max_error
        self._initialized = False

    @property
    def is_available(self) -> bool:
        """astrometry 是否可用 / Whether astrometry is available"""
        return _ASTROMETRY_AVAILABLE

    @property
    def is_initialized(self) -> bool:
        """求解器是否已初始化 / Whether solver is initialized"""
        return self._initialized and self._solver is not None

    def initialize(self) -> bool:
        """下载索引文件并初始化求解器 / Download index files and initialize solver

        Returns:
            是否初始化成功 / Whether initialization succeeded
        """
        if self._initialized:
            return True

        if not _ASTROMETRY_AVAILABLE:
            logger.error(
                "astrometry 未安装，无法进行板块求解 / "
                "astrometry not installed, plate solving unavailable"
            )
            return False

        try:
            logger.info(
                f"正在初始化 astrometry 求解器 (缓存: {self._cache_dir}, 比例: {self._scales}) / "
                f"Initializing astrometry solver (cache: {self._cache_dir}, scales: {self._scales})"
            )
            start = time.monotonic()

            index_files = astrometry.series_4100.index_files(
                cache_directory=str(self._cache_dir),
                scales=self._scales,
            )

            self._solver = astrometry.Solver(index_files)
            elapsed = (time.monotonic() - start) * 1000
            logger.info(
                f"astrometry 求解器初始化完成 ({elapsed:.0f}ms, {len(index_files)} 个索引文件) / "
                f"astrometry solver initialized ({elapsed:.0f}ms, {len(index_files)} index files)"
            )

            self._initialized = True
            return True

        except Exception as e:
            logger.error(
                f"初始化板块求解器失败: {e} / "
                f"Failed to initialize plate solver: {e}"
            )
            return False

    def close(self) -> None:
        """关闭求解器，释放资源 / Close solver, release resources"""
        if self._solver is not None:
            try:
                self._solver.close()
            except Exception:
                pass
            self._solver = None
            self._initialized = False

    def solve_image(
        self,
        image: Union["Image.Image", np.ndarray],
        options: Optional[SolveOptions] = None,
    ) -> SolveResult:
        """对图像进行板块求解 / Plate solve an image

        Args:
            image: PIL Image 或 numpy 数组 / PIL Image or numpy array
            options: 求解参数 / Solve options

        Returns:
            求解结果 / Solve result
        """
        if not self.is_initialized:
            if not self.initialize():
                return SolveResult(
                    status=SolveStatus.ERROR,
                    error_message="求解器未初始化 / Solver not initialized",
                )

        if options is None:
            options = SolveOptions()

        total_start = time.monotonic()

        # 转换为灰度 numpy 数组 / Convert to grayscale numpy array
        gray = self._to_grayscale(image)
        if gray is None:
            return SolveResult(
                status=SolveStatus.ERROR,
                error_message="无法转换图像格式 / Cannot convert image format",
            )

        h, w = gray.shape[:2]

        # 提取星点 / Extract star centroids
        extract_start = time.monotonic()
        stars = self._extract_stars(gray, options)
        extract_time = (time.monotonic() - extract_start) * 1000

        if len(stars) < 4:
            total_elapsed = (time.monotonic() - total_start) * 1000
            logger.warning(
                f"星点不足 ({len(stars)}), 需要至少4颗 / "
                f"Not enough stars ({len(stars)}), need at least 4"
            )
            return SolveResult(
                status=SolveStatus.NO_STARS,
                detected_stars=len(stars),
                extract_time_ms=extract_time,
                total_time_ms=total_elapsed,
                error_message=f"仅检测到 {len(stars)} 颗星 / Only {len(stars)} stars detected",
            )

        logger.debug(
            f"提取到 {len(stars)} 颗星点 ({extract_time:.0f}ms), "
            f"图像 {w}x{h} / "
            f"Extracted {len(stars)} stars ({extract_time:.0f}ms), "
            f"image {w}x{h}"
        )

        # 构建求解提示 / Build solve hints
        size_hint = self._build_size_hint(options, w, h)
        position_hint = self._build_position_hint(options)

        try:
            solve_start = time.monotonic()
            solution = self._solver.solve(
                stars=stars,
                size_hint=size_hint,
                position_hint=position_hint,
                solution_parameters=astrometry.SolutionParameters(
                    logodds_callback=lambda logodds_list: (
                        astrometry.Action.STOP
                        if logodds_list[0] > 100.0
                        else astrometry.Action.CONTINUE
                    ),
                ),
            )
            solve_time = (time.monotonic() - solve_start) * 1000
            total_elapsed = (time.monotonic() - total_start) * 1000

            result = self._parse_solution(
                solution, w, h, len(stars), solve_time, extract_time, total_elapsed
            )

            # 绘制叠加层 / Draw overlay if requested
            if options.draw_overlay:
                result.annotated_image = self.draw_overlay(image, result)

            return result

        except Exception as e:
            total_elapsed = (time.monotonic() - total_start) * 1000
            logger.error(f"板块求解异常: {e} / Plate solve error: {e}")
            return SolveResult(
                status=SolveStatus.ERROR,
                detected_stars=len(stars),
                error_message=str(e),
                extract_time_ms=extract_time,
                total_time_ms=total_elapsed,
            )

    def solve_file(
        self,
        file_path: Union[str, Path],
        options: Optional[SolveOptions] = None,
    ) -> SolveResult:
        """从文件进行板块求解 / Plate solve from file"""
        path = Path(file_path)
        if not path.exists():
            return SolveResult(
                status=SolveStatus.ERROR,
                error_message=f"文件不存在: {path} / File not found: {path}",
            )

        try:
            if cv2 is not None:
                img = cv2.imread(str(path))
                if img is None:
                    raise ValueError(f"OpenCV 无法读取 / OpenCV cannot read: {path}")
            elif Image is not None:
                img = Image.open(path)
            else:
                return SolveResult(
                    status=SolveStatus.ERROR,
                    error_message="OpenCV 和 Pillow 均未安装 / Neither OpenCV nor Pillow installed",
                )
        except Exception as e:
            return SolveResult(
                status=SolveStatus.ERROR,
                error_message=f"无法读取图像: {e} / Cannot read image: {e}",
            )

        logger.info(f"从文件求解: {path.name} / Solving from file: {path.name}")
        return self.solve_image(img, options)

    def solve_bytes(
        self,
        image_data: bytes,
        options: Optional[SolveOptions] = None,
    ) -> SolveResult:
        """从字节数据进行板块求解 / Plate solve from bytes"""
        if cv2 is not None:
            arr = np.frombuffer(image_data, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return SolveResult(
                    status=SolveStatus.ERROR,
                    error_message="无法解码图像数据 / Cannot decode image data",
                )
            return self.solve_image(img, options)

        if Image is not None:
            import io
            try:
                pil_image = Image.open(io.BytesIO(image_data))
            except Exception as e:
                return SolveResult(
                    status=SolveStatus.ERROR,
                    error_message=f"无法解码图像数据: {e} / Cannot decode image data: {e}",
                )
            return self.solve_image(pil_image, options)

        return SolveResult(
            status=SolveStatus.ERROR,
            error_message="OpenCV 和 Pillow 均未安装 / Neither OpenCV nor Pillow installed",
        )

    def _extract_stars(
        self, gray: np.ndarray, options: SolveOptions
    ) -> list[list[float]]:
        """从灰度图像中提取星点质心 / Extract star centroids from grayscale image

        使用自适应阈值和轮廓检测提取星点位置。
        Uses adaptive thresholding and contour detection to extract star positions.

        Args:
            gray: 灰度图像 / Grayscale image
            options: 求解参数 / Solve options

        Returns:
            星点坐标列表 [[x, y], ...] / Star coordinate list [[x, y], ...]
        """
        if cv2 is None:
            return []

        # 高斯模糊降噪 / Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        # 计算背景统计量 / Calculate background statistics
        mean_val = np.mean(blurred)
        std_val = np.std(blurred)
        threshold = mean_val + options.detection_sigma * std_val
        threshold = min(threshold, 254)

        # 二值化 / Threshold
        _, binary = cv2.threshold(blurred, threshold, 255, cv2.THRESH_BINARY)

        # 查找轮廓 / Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 过滤并计算质心 / Filter and calculate centroids
        centroids: list[tuple[float, float, float]] = []  # (x, y, brightness)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < options.min_area or area > options.max_area:
                continue

            # 计算加权质心 / Calculate weighted centroid
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                continue
            cx = moments["m10"] / moments["m00"]
            cy = moments["m01"] / moments["m00"]

            # 使用像素亮度作为权重来排序 / Use pixel brightness for sorting
            brightness = float(gray[int(cy), int(cx)]) if 0 <= int(cy) < gray.shape[0] and 0 <= int(cx) < gray.shape[1] else 0
            centroids.append((cx, cy, brightness))

        # 按亮度降序排序，取前 max_stars 个 / Sort by brightness descending, take top max_stars
        centroids.sort(key=lambda c: c[2], reverse=True)
        stars = [[c[0], c[1]] for c in centroids[: options.max_stars]]

        return stars

    def _build_size_hint(
        self, options: SolveOptions, width: int, height: int
    ) -> Optional[Any]:
        """根据 FOV 估计构建像素比例提示 / Build size hint from FOV estimate"""
        if not _ASTROMETRY_AVAILABLE:
            return None

        fov_est = options.fov_estimate or self._default_fov_estimate
        fov_err = options.fov_max_error or self._default_fov_max_error

        if fov_est is not None:
            # 将 FOV (度) 转为 arcsec/pixel / Convert FOV (degrees) to arcsec/pixel
            fov_arcsec = fov_est * 3600.0
            scale = fov_arcsec / max(width, height)

            if fov_err is not None:
                err_arcsec = fov_err * 3600.0
                err_scale = err_arcsec / max(width, height)
            else:
                err_scale = scale * 0.5  # 默认 50% 误差 / Default 50% error

            lower = max(0.1, scale - err_scale)
            upper = scale + err_scale
            return astrometry.SizeHint(
                lower_arcsec_per_pixel=lower,
                upper_arcsec_per_pixel=upper,
            )

        return None

    def _build_position_hint(self, options: SolveOptions) -> Optional[Any]:
        """构建位置提示 / Build position hint"""
        if not _ASTROMETRY_AVAILABLE:
            return None

        if options.hint_ra is not None and options.hint_dec is not None:
            radius = options.hint_radius if options.hint_radius is not None else 10.0
            return astrometry.PositionHint(
                ra_deg=options.hint_ra,
                dec_deg=options.hint_dec,
                radius_deg=radius,
            )

        return None

    def _parse_solution(
        self,
        solution: Any,
        width: int,
        height: int,
        num_stars: int,
        solve_time: float,
        extract_time: float,
        total_time: float,
    ) -> SolveResult:
        """解析 astrometry Solution 对象 / Parse astrometry Solution object"""
        if not solution.has_match():
            logger.warning(
                f"板块求解失败 (耗时 {total_time:.0f}ms) / "
                f"Plate solve failed ({total_time:.0f}ms)"
            )
            return SolveResult(
                status=SolveStatus.FAILED,
                detected_stars=num_stars,
                solve_time_ms=solve_time,
                extract_time_ms=extract_time,
                total_time_ms=total_time,
            )

        match = solution.best_match()

        # 计算 FOV / Calculate FOV from scale
        scale = match.scale_arcsec_per_pixel
        fov_deg = (scale * max(width, height)) / 3600.0

        # 从 WCS 计算旋转角 / Calculate roll from WCS
        roll = self._calculate_roll(match)

        # 获取匹配的星点信息 / Get matched star info
        matched_stars = []
        matched_centroids = []
        try:
            wcs = match.astropy_wcs()
            for star in match.stars:
                matched_stars.append([star.ra_deg, star.dec_deg, star.metadata])
                # 转换为像素坐标 / Convert to pixel coordinates
                px = wcs.all_world2pix([[star.ra_deg, star.dec_deg]], 0)
                matched_centroids.append([float(px[0][0]), float(px[0][1])])
        except Exception as e:
            logger.debug(f"获取匹配星点信息失败: {e} / Failed to get matched star info: {e}")

        result = SolveResult(
            status=SolveStatus.SUCCESS,
            ra=float(match.center_ra_deg),
            dec=float(match.center_dec_deg),
            roll=roll,
            fov=fov_deg,
            scale_arcsec_per_pixel=float(scale),
            logodds=float(match.logodds),
            matches=len(match.stars),
            detected_stars=num_stars,
            solve_time_ms=solve_time,
            extract_time_ms=extract_time,
            total_time_ms=total_time,
            matched_stars=matched_stars if matched_stars else None,
            matched_centroids=matched_centroids if matched_centroids else None,
        )

        logger.info(
            f"板块求解成功: RA={result.ra_hms}, Dec={result.dec_dms}, "
            f"FOV={fov_deg:.2f}°, {result.matches}星, "
            f"logodds={match.logodds:.1f}, 耗时{total_time:.0f}ms / "
            f"Plate solve success: RA={result.ra_hms}, Dec={result.dec_dms}, "
            f"FOV={fov_deg:.2f}°, {result.matches} stars, "
            f"logodds={match.logodds:.1f}, {total_time:.0f}ms"
        )

        return result

    @staticmethod
    def _calculate_roll(match: Any) -> Optional[float]:
        """从 WCS 计算图像旋转角 / Calculate image roll from WCS"""
        try:
            wcs = match.astropy_wcs()
            cd = wcs.wcs.cd
            roll = float(np.degrees(np.arctan2(cd[0][1], cd[0][0])))
            return roll
        except Exception:
            return None

    @staticmethod
    def _to_grayscale(image: Union["Image.Image", np.ndarray]) -> Optional[np.ndarray]:
        """将输入图像转换为灰度 numpy 数组 / Convert input to grayscale numpy array"""
        if cv2 is None:
            return None

        if isinstance(image, np.ndarray):
            if len(image.shape) == 2:
                return image
            if len(image.shape) == 3:
                return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            return None

        if Image is not None and isinstance(image, Image.Image):
            arr = np.array(image.convert("L"))
            return arr

        return None

    def draw_overlay(
        self,
        image: Union["Image.Image", np.ndarray, bytes],
        result: SolveResult,
    ) -> Optional[bytes]:
        """在图像上绘制板块求解叠加层 / Draw plate solve overlay on image

        绘制内容 / Draws:
        - 图像中心十字线 / Crosshair at image center
        - 匹配的星点 (红色圆圈+标签) / Matched stars (red circles + labels)
        - RA/Dec 坐标信息 / RA/Dec coordinate info
        - FOV 和匹配质量 / FOV and match quality

        Args:
            image: 原始图像 / Original image (PIL, numpy, or JPEG bytes)
            result: 求解结果 / Solve result

        Returns:
            带叠加层的 JPEG 字节，失败返回 None /
            JPEG bytes with overlay, None on failure
        """
        if cv2 is None:
            logger.warning("OpenCV 未安装，无法绘制叠加层 / OpenCV not installed, cannot draw overlay")
            return None

        # 将输入转为 numpy BGR / Convert input to numpy BGR
        frame = self._to_cv2_image(image)
        if frame is None:
            return None

        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2

        # 根据图像尺寸计算比例 / Scale based on image size
        scale = max(w, h) / 1920.0
        scale = max(scale, 0.4)

        # --- 中心十字线 / Center crosshair ---
        cross_size = int(40 * scale)
        cross_thick = max(1, int(2 * scale))
        cross_color = (0, 255, 255)  # 黄色 (BGR) / Yellow (BGR)
        cv2.line(frame, (cx - cross_size, cy), (cx + cross_size, cy), cross_color, cross_thick)
        cv2.line(frame, (cx, cy - cross_size), (cx, cy + cross_size), cross_color, cross_thick)
        # 中心小圆 / Small center circle
        cv2.circle(frame, (cx, cy), int(6 * scale), cross_color, cross_thick)

        # --- 匹配的星点 / Matched centroids ---
        if result.matched_centroids:
            for centroid in result.matched_centroids:
                # centroid 格式: (x, y) / centroid format: (x, y)
                px, py = int(centroid[0]), int(centroid[1])
                radius = int(8 * scale)
                cv2.circle(frame, (px, py), radius, (0, 0, 255), max(1, int(2 * scale)))

        # --- 匹配的星点标签 / Matched star labels ---
        if result.matched_stars and result.matched_centroids:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.4 * scale
            font_thick = max(1, int(1.5 * scale))
            for i, (star, centroid) in enumerate(
                zip(result.matched_stars, result.matched_centroids)
            ):
                px, py = int(centroid[0]), int(centroid[1])
                label = f"#{i}"
                cv2.putText(
                    frame,
                    label,
                    (px + int(10 * scale), py - int(5 * scale)),
                    font,
                    font_scale,
                    (0, 0, 255),
                    font_thick,
                    cv2.LINE_AA,
                )

        # --- 信息面板 / Info panel ---
        self._draw_info_panel(frame, result, scale)

        # 编码为 JPEG / Encode as JPEG
        _, jpeg_data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return jpeg_data.tobytes()

    @staticmethod
    def _draw_info_panel(
        frame: np.ndarray,
        result: SolveResult,
        scale: float,
    ) -> None:
        """在图像左上角绘制半透明信息面板 / Draw semi-transparent info panel at top-left"""
        if cv2 is None:
            return
        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5 * scale
        font_thick = max(1, int(1.5 * scale))
        line_height = int(24 * scale)
        margin = int(10 * scale)

        # 构建信息行 / Build info lines
        lines: list[tuple[str, tuple[int, int, int]]] = []

        if result.is_solved:
            lines.append(("SOLVED", (0, 255, 0)))
            lines.append((f"RA:  {result.ra_hms}", (255, 255, 255)))
            lines.append((f"Dec: {result.dec_dms}", (255, 255, 255)))
            if result.roll is not None:
                lines.append((f"Roll: {result.roll:.1f} deg", (200, 200, 200)))
            if result.fov is not None:
                lines.append((f"FOV: {result.fov:.2f} deg", (200, 200, 200)))
            if result.matches is not None:
                lines.append((f"Stars: {result.matches} matched", (200, 200, 200)))
            if result.logodds is not None:
                lines.append((f"LogOdds: {result.logodds:.1f}", (200, 200, 200)))
            if result.total_time_ms is not None:
                lines.append((f"Time: {result.total_time_ms:.0f}ms", (180, 180, 180)))
        else:
            lines.append(("NOT SOLVED", (0, 0, 255)))
            if result.error_message:
                msg = result.error_message[:50]
                lines.append((msg, (180, 180, 180)))
            if result.total_time_ms is not None:
                lines.append((f"Time: {result.total_time_ms:.0f}ms", (180, 180, 180)))

        if not lines:
            return

        # 计算面板尺寸 / Calculate panel dimensions
        panel_h = margin * 2 + line_height * len(lines)
        max_text_w = 0
        for text, _ in lines:
            (tw, _), _ = cv2.getTextSize(text, font, font_scale, font_thick)
            max_text_w = max(max_text_w, tw)
        panel_w = margin * 3 + max_text_w

        # 绘制半透明背景 / Draw semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (panel_w, panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # 绘制文本 / Draw text
        y = margin + int(16 * scale)
        for text, color in lines:
            cv2.putText(frame, text, (margin, y), font, font_scale, color, font_thick, cv2.LINE_AA)
            y += line_height

    @staticmethod
    def _to_cv2_image(
        image: Union["Image.Image", np.ndarray, bytes],
    ) -> Optional[np.ndarray]:
        """将输入图像转换为 OpenCV BGR numpy 数组 / Convert input to OpenCV BGR numpy array"""
        if cv2 is None:
            return None

        if isinstance(image, bytes):
            arr = np.frombuffer(image, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return frame

        if isinstance(image, np.ndarray):
            if len(image.shape) == 2:
                return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            if len(image.shape) == 3 and image.shape[2] == 3:
                return image.copy()
            return None

        if Image is not None and isinstance(image, Image.Image):
            arr = np.array(image)
            if len(arr.shape) == 2:
                return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            if len(arr.shape) == 3:
                if arr.shape[2] == 4:
                    return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        return None
