"""
素材分析服务 / Asset analysis services
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from ogscope.algorithms.plate_solve import (
    CentroidExtractionParams,
    PlateSolver,
    centroid_extraction_preview,
    merge_centroid_params,
)
from ogscope.algorithms.star_extract import StarExtractor
from ogscope.config import get_settings
from ogscope.web.api.analysis.lab_store import AnalysisLabStore
from ogscope.web.api.models.schemas import (
    AnalysisBatchSolveRequest,
    AnalysisExperimentCreate,
    AnalysisExtractPreviewRequest,
    AnalysisPresetCreate,
    AnalysisSolveImageRequest,
    AnalysisSolveVideoFrameRequest,
    CentroidParamsPayload,
)

_SOLVE_PROFILE_DEFAULT = "balanced"
_SOLVE_PROFILE_OVERRIDES: dict[str, dict[str, Any]] = {
    "speed": {
        "timeout_ms": 1000,
        "max_stars": 40,
        "centroid": {
            "sigma": 3.4,
            "min_area": 8,
            "max_area": 280,
            "binary_open": True,
            "max_axis_ratio": 2.2,
        },
    },
    "balanced": {
        "timeout_ms": 1500,
        "max_stars": 60,
        "centroid": {
            "sigma": 3.0,
            "min_area": 6,
            "max_area": 360,
            "binary_open": True,
            "max_axis_ratio": 2.8,
        },
    },
    "robust": {
        "timeout_ms": 3000,
        "max_stars": 90,
        "centroid": {
            "sigma": 2.5,
            "min_area": 4,
            "max_area": 500,
            "binary_open": True,
            "max_axis_ratio": None,
        },
    },
}


def _merge_debug_style_sidecar_into_info(
    info: dict[str, Any], capture_info: dict[str, Any]
) -> None:
    """将侧车 JSON 的 camera/extra 展开到顶层，与调试页 info 一致 / Match debug file info shape."""
    cam = capture_info.get("camera")
    if isinstance(cam, dict):
        for k in (
            "exposure_us",
            "analogue_gain",
            "digital_gain",
            "fps",
            "auto_exposure",
            "rotation",
            "sampling_mode",
            "color_mode",
            "sensor",
            "resolution",
        ):
            if k not in capture_info and k in cam:
                capture_info[k] = cam[k]
        if capture_info.get("resolution") is None:
            ow = cam.get("output_width") or cam.get("width")
            oh = cam.get("output_height") or cam.get("height")
            if ow and oh:
                capture_info["resolution"] = f"{ow}x{oh}"
    extra = capture_info.get("extra")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in capture_info:
                capture_info[k] = v
    info.update(capture_info)


@dataclass(slots=True)
class AnalysisJob:
    """分析任务 / Analysis job"""

    job_id: str
    input_name: str
    input_type: str
    status: str = "queued"
    progress: float = 0.0
    message: str = ""
    result_path: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "input_name": self.input_name,
            "input_type": self.input_type,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result_path": self.result_path,
            "created_at": self.created_at,
        }


class AnalysisService:
    """分析服务 / Analysis service"""

    def __init__(self) -> None:
        settings = get_settings()
        self.upload_root = settings.upload_dir / "analysis"
        self.jobs_root = settings.analysis_dir / "jobs"
        self.results_root = settings.analysis_dir / "results"
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.results_root.mkdir(parents=True, exist_ok=True)
        # 解算专用线程池（避免与相机预览等争用默认线程池）/ Dedicated executor for solving tasks
        self._solver_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="solver"
        )
        self._solver_max_stars = settings.solver_max_stars
        self.extractor = StarExtractor(max_stars=settings.solver_max_stars)
        self.solver = PlateSolver(
            fov_deg=settings.solver_fov_deg,
            fov_max_error_deg=settings.solver_fov_max_error_deg,
            solve_timeout_ms=settings.solver_timeout_ms,
        )
        self.default_hint_ra = settings.solver_hint_ra_deg
        self.default_hint_dec = settings.solver_hint_dec_deg
        self._jobs: dict[str, AnalysisJob] = {}
        self._lab = AnalysisLabStore(settings)

    def _centroid_params_from_payload(
        self, payload: CentroidParamsPayload | None
    ) -> CentroidExtractionParams | None:
        """合并请求中的提星覆盖项与默认配置 / Merge API overrides with Settings defaults."""
        if payload is None:
            return None
        base = CentroidExtractionParams.from_settings(get_settings())
        return merge_centroid_params(base, payload.model_dump(exclude_none=True))

    def _resolve_solve_profile(
        self,
        profile_name: str | None,
        payload: CentroidParamsPayload | None,
        solve_timeout_ms: int | None,
    ) -> tuple[CentroidExtractionParams, int, int, str]:
        """解析解算分档并返回参数 / Resolve solve profile into concrete params."""
        settings = get_settings()
        effective = str(profile_name or _SOLVE_PROFILE_DEFAULT).lower()
        if effective not in _SOLVE_PROFILE_OVERRIDES:
            effective = _SOLVE_PROFILE_DEFAULT

        profile_cfg = _SOLVE_PROFILE_OVERRIDES[effective]
        base = CentroidExtractionParams.from_settings(settings)
        centroid = merge_centroid_params(base, profile_cfg.get("centroid", {}))
        if payload is not None:
            centroid = merge_centroid_params(
                centroid, payload.model_dump(exclude_none=True)
            )

        max_stars = int(profile_cfg.get("max_stars", self._solver_max_stars))
        timeout_ms = int(
            solve_timeout_ms
            if solve_timeout_ms is not None
            else profile_cfg.get("timeout_ms", settings.solver_timeout_ms)
        )
        return centroid, max(4, max_stars), max(200, timeout_ms), effective

    def resolve_upload_path(self, filename: str) -> Path:
        """解析上传目录内安全路径（仅单层文件名）/ Safe path under upload_root (basename only)."""
        clean = filename.strip()
        name = Path(clean).name
        if not name or name != clean:
            raise ValueError("文件名无效 / Invalid filename")
        path = (self.upload_root / name).resolve()
        root = self.upload_root.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("路径非法 / Invalid path") from exc
        return path

    def get_upload_file_info(self, filename: str) -> dict[str, Any]:
        """从上传目录读取文件与 stem.txt 侧车 / File + optional sidecar from upload pool."""
        path = self.resolve_upload_path(filename)
        if not path.is_file():
            raise FileNotFoundError("上传文件不存在 / Uploaded file not found")
        st = path.stat()
        image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
        video_ext = {
            ".mp4",
            ".avi",
            ".mov",
            ".mkv",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }
        suffix = path.suffix.lower()
        file_type = (
            "image"
            if suffix in image_ext
            else "video" if suffix in video_ext else "file"
        )
        info: dict[str, Any] = {
            "filename": path.name,
            "size": st.st_size,
            "modified": datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc
            ).isoformat(),
            "type": file_type,
        }
        sidecar = self.upload_root / f"{path.stem}.txt"
        if sidecar.is_file():
            try:
                raw = json.loads(sidecar.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    _merge_debug_style_sidecar_into_info(info, raw)
            except (json.JSONDecodeError, OSError):
                pass
        return info

    def list_uploads(self) -> dict[str, Any]:
        """列出已持久化上传的文件 / List persisted uploads (flat, no recursion)."""
        root = self.upload_root
        files: list[dict[str, Any]] = []
        if not root.is_dir():
            return {"upload_dir": str(root.resolve()), "files": []}
        for p in root.iterdir():
            if not p.is_file():
                continue
            if p.name.startswith("."):
                continue
            if p.name == "manifest.json":
                continue
            # 侧车 .txt 不单独列入素材池 / Hide sidecar metadata from pool list
            if p.suffix.lower() == ".txt":
                continue
            st = p.stat()
            base = {
                "filename": p.name,
                "size": st.st_size,
                "modified_at": datetime.fromtimestamp(
                    st.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
            files.append(self._lab.merge_list_entry(p.name, base))
        files.sort(key=lambda x: x["modified_at"], reverse=True)
        return {"upload_dir": str(root.resolve()), "files": files}

    async def save_upload(
        self, filename: str, payload: bytes, source: str = "analysis_upload"
    ) -> dict[str, Any]:
        """保存上传文件 / Save uploaded file"""
        safe_name = Path(filename).name
        if not safe_name:
            raise ValueError("文件名无效 / Invalid filename")
        target = self.upload_root / safe_name
        target.write_bytes(payload)
        self._lab.set_file_source(safe_name, source)
        return {
            "success": True,
            "filename": safe_name,
            "path": str(target),
            "size": target.stat().st_size,
        }

    async def create_job(
        self,
        input_name: str,
        input_type: str,
        hint_ra_deg: float | None = None,
        hint_dec_deg: float | None = None,
        frame_step: int = 1,
        max_frames: int = 180,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
        centroid: CentroidParamsPayload | None = None,
        max_image_side: int | None = None,
        large_scale_bg_subtract: bool = False,
    ) -> dict[str, Any]:
        """创建并执行任务 / Create and execute job"""
        if input_type not in {"image", "video"}:
            raise ValueError(
                "input_type 仅支持 image 或 video / input_type must be image or video"
            )

        source = self.upload_root / Path(input_name).name
        if not source.exists():
            raise FileNotFoundError("上传文件不存在 / Uploaded file not found")

        job = AnalysisJob(
            job_id=str(uuid.uuid4()), input_name=source.name, input_type=input_type
        )
        self._jobs[job.job_id] = job
        self._persist_job(job)
        centroid_params = self._centroid_params_from_payload(centroid)

        try:
            job.status = "running"
            job.message = "开始分析 / Analysis started"
            self._persist_job(job)
            loop = asyncio.get_running_loop()
            if input_type == "image":
                results = await loop.run_in_executor(
                    self._solver_executor,
                    self._analyze_image,
                    source,
                    hint_ra_deg,
                    hint_dec_deg,
                    fov_estimate,
                    fov_max_error,
                    solve_timeout_ms,
                    centroid_params,
                    max_image_side,
                    None,
                    large_scale_bg_subtract,
                )
            else:
                results = await loop.run_in_executor(
                    self._solver_executor,
                    self._analyze_video,
                    source,
                    hint_ra_deg,
                    hint_dec_deg,
                    frame_step,
                    max_frames,
                    job,
                    fov_estimate,
                    fov_max_error,
                    solve_timeout_ms,
                )
            result_path = self.results_root / f"{job.job_id}.json"
            result_payload = {
                "job_id": job.job_id,
                "input_name": job.input_name,
                "input_type": job.input_type,
                "results": results,
            }
            result_path.write_text(
                json.dumps(result_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            job.status = "succeeded"
            job.progress = 1.0
            job.message = "分析完成 / Analysis finished"
            job.result_path = str(result_path)
            self._persist_job(job)
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.message = f"分析失败 / Analysis failed: {exc}"
            self._persist_job(job)
            raise
        return job.to_dict()

    async def solve_single_image(
        self, body: AnalysisSolveImageRequest
    ) -> dict[str, Any]:
        """直接解算单图（JSON body）/ Solve a single image via JSON body."""
        source = self.upload_root / Path(body.input_name).name
        if not source.exists():
            raise FileNotFoundError("上传文件不存在 / Uploaded file not found")
        loop = asyncio.get_running_loop()
        # 档位与两段策略解析 / Resolve profile and two-stage strategy
        centroid_params, max_stars, timeout_ms, requested_profile = (
            self._resolve_solve_profile(
                body.solve_profile, body.centroid, body.solve_timeout_ms
            )
        )

        ls_bg = bool(body.large_scale_bg_subtract)

        def _run_single() -> list[dict[str, Any]]:
            return self._analyze_image(
                source=source,
                hint_ra_deg=body.hint_ra_deg,
                hint_dec_deg=body.hint_dec_deg,
                fov_estimate=body.fov_estimate,
                fov_max_error=body.fov_max_error,
                solve_timeout_ms=timeout_ms,
                centroid_params=centroid_params,
                max_image_side=body.max_image_side,
                max_stars=max_stars,
                large_scale_bg_subtract=ls_bg,
            )

        def _run_two_stage() -> list[dict[str, Any]]:
            """平衡档位使用 speed→robust 两段策略 / Balanced profile: speed then robust fallback."""
            # 第 1 段：speed 档快速尝试 / Stage 1: quick speed attempt
            speed_centroid, speed_max_stars, speed_timeout_ms, _ = (
                self._resolve_solve_profile("speed", body.centroid, body.solve_timeout_ms)
            )
            first = self._analyze_image(
                source=source,
                hint_ra_deg=body.hint_ra_deg,
                hint_dec_deg=body.hint_dec_deg,
                fov_estimate=body.fov_estimate,
                fov_max_error=body.fov_max_error,
                solve_timeout_ms=speed_timeout_ms,
                centroid_params=speed_centroid,
                max_image_side=body.max_image_side,
                max_stars=speed_max_stars,
                large_scale_bg_subtract=ls_bg,
            )
            row0 = first[0] if first else None
            if row0 and row0.get("status") == "MATCH_FOUND":
                row0["solve_profile"] = "speed"
                return [row0]

            # 噪点图动态 max_stars 收紧 / Heuristic: tighten max_stars for noisy frames
            detected = int(row0.get("detected_stars") or 0) if row0 else 0
            robust_centroid, robust_max_stars, robust_timeout_ms, _ = (
                self._resolve_solve_profile("robust", body.centroid, body.solve_timeout_ms)
            )
            if detected > 0 and detected > robust_max_stars:
                robust_max_stars = max(20, int(robust_max_stars * 0.7))

            second = self._analyze_image(
                source=source,
                hint_ra_deg=body.hint_ra_deg,
                hint_dec_deg=body.hint_dec_deg,
                fov_estimate=body.fov_estimate,
                fov_max_error=body.fov_max_error,
                solve_timeout_ms=robust_timeout_ms,
                centroid_params=robust_centroid,
                max_image_side=body.max_image_side,
                max_stars=robust_max_stars,
                large_scale_bg_subtract=ls_bg,
            )
            if second:
                second[0]["solve_profile"] = "robust"
            return second

        # balanced 档默认启用两段策略，其他档位单次解算 / Balanced uses two-stage, others single-pass
        if requested_profile == "balanced":
            rows = await loop.run_in_executor(self._solver_executor, _run_two_stage)
            effective_profile = (
                rows[0].get("solve_profile") if rows and rows[0].get("solve_profile") else "balanced"
            )
        else:
            rows = await loop.run_in_executor(self._solver_executor, _run_single)
            effective_profile = requested_profile

        row = rows[0] if rows else None
        if row and "solve_profile" not in row:
            row["solve_profile"] = effective_profile
        # 默认精简 raw，大字段仅在 detail_level==full 时返回 / Drop heavy raw unless client asks for full detail.
        detail_level = getattr(body, "detail_level", None) or "summary"
        if row and detail_level != "full":
            row.pop("tetra", None)
        if row:
            self._lab.update_last_solve(
                source.name,
                self._metrics_from_solve_row(row),
            )
        return {
            "success": True,
            "input_name": source.name,
            "result": row,
        }

    @staticmethod
    def _metrics_from_solve_row(row: dict[str, Any]) -> dict[str, Any]:
        """提取列表与实验用指标 / Metrics for manifest and experiments."""
        return {
            "matches": row.get("matches"),
            "rmse_arcsec": row.get("rmse_arcsec"),
            "status": row.get("status"),
            "prob": row.get("prob"),
            "t_solve_ms": row.get("t_solve_ms"),
        }

    async def batch_solve(self, body: AnalysisBatchSolveRequest) -> dict[str, Any]:
        """多组参数顺序解算同一文件 / Batch solve same file with multiple param sets."""
        results: list[dict[str, Any]] = []
        for run in body.runs:
            params = run.params.model_dump(exclude_none=True)
            req = AnalysisSolveImageRequest.model_validate(
                {"input_name": body.input_name, **params}
            )
            try:
                out = await self.solve_single_image(req)
                results.append(
                    {
                        "label": run.label,
                        "success": True,
                        "result": out.get("result"),
                        "input_name": out.get("input_name"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "label": run.label,
                        "success": False,
                        "error": str(exc),
                    }
                )
        return {"input_name": body.input_name, "results": results}

    def import_from_debug_capture(self, filename: str) -> dict[str, Any]:
        """从 ~/dev_captures 复制到分析素材池并标记来源 / Copy debug capture into pool."""
        src = Path.home() / "dev_captures" / Path(filename).name
        if not src.is_file():
            raise FileNotFoundError(
                "调试采集文件不存在 / Debug capture file not found in dev_captures"
            )
        dst = self.upload_root / src.name
        shutil.copy2(src, dst)
        side_txt = Path.home() / "dev_captures" / f"{src.stem}.txt"
        if side_txt.is_file():
            shutil.copy2(side_txt, self.upload_root / side_txt.name)
        self._lab.set_file_source(dst.name, "debug_console")
        return {
            "success": True,
            "filename": dst.name,
            "size": dst.stat().st_size,
        }

    def list_presets(self, scope: str) -> dict[str, Any]:
        """列出官方或用户预设 / List official or user presets."""
        if scope not in {"official", "user"}:
            raise ValueError(
                "scope 须为 official 或 user / scope must be official or user"
            )
        return {"scope": scope, "presets": self._lab.list_presets(scope)}

    def create_user_preset(self, body: AnalysisPresetCreate) -> dict[str, Any]:
        """创建用户预设 / Create user preset."""
        params = body.params.model_dump(exclude_none=True)
        return self._lab.save_user_preset(body.name, params)

    def delete_user_preset(self, preset_id: str) -> None:
        """删除用户预设 / Delete user preset."""
        self._lab.delete_user_preset(preset_id)

    def create_experiment(self, body: AnalysisExperimentCreate) -> dict[str, Any]:
        """保存实验记录 / Save experiment record."""
        return self._lab.create_experiment(
            input_name=body.input_name,
            preset_label=body.preset_label,
            result_json=body.result_json,
            metrics=body.metrics,
            thumbnail_png_base64=body.thumbnail_png_base64,
            replay=body.replay,
            save_asset_snapshot=body.save_asset_snapshot,
        )

    def list_experiments(
        self, q: str | None, page: int, page_size: int
    ) -> dict[str, Any]:
        """分页实验列表 / Paginated experiments."""
        return self._lab.list_experiments(q, page, page_size)

    def delete_upload(
        self, filename: str, delete_experiments: bool = False
    ) -> dict[str, Any]:
        """删除素材池文件及 stem.txt 侧车；可选级联实验记录 / Delete pool file and sidecar; optional cascade."""
        path = self.resolve_upload_path(filename)
        if path.name == "manifest.json":
            raise ValueError("不可删除清单文件 / Cannot delete manifest")
        if not path.is_file():
            raise FileNotFoundError("上传文件不存在 / Uploaded file not found")
        n_exp = 0
        if delete_experiments:
            n_exp = self._lab.delete_experiments_for_input(path.name)
        path.unlink()
        side = self.upload_root / f"{path.stem}.txt"
        if side.is_file():
            side.unlink()
        self._lab.remove_manifest_entry(path.name)
        return {"success": True, "filename": path.name, "deleted_experiments": n_exp}

    def delete_experiment(self, experiment_id: str) -> None:
        """删除一条实验记录 / Delete one experiment record."""
        self._lab.delete_experiment(experiment_id)

    def export_experiments(self, fmt: str) -> str:
        """导出实验记录 / Export experiments."""
        if fmt == "json":
            return self._lab.export_experiments_json()
        if fmt == "csv":
            return self._lab.export_experiments_csv()
        raise ValueError("format 须为 json 或 csv / format must be json or csv")

    async def extract_preview(
        self, body: AnalysisExtractPreviewRequest
    ) -> dict[str, Any]:
        """提星二值掩膜预览（不调 Tetra3 解算）/ Preview binary mask without plate solve."""
        source = self.upload_root / Path(body.input_name).name
        if not source.exists():
            raise FileNotFoundError("上传文件不存在 / Uploaded file not found")
        centroid_params = self._centroid_params_from_payload(body.centroid)
        settings = get_settings()
        max_side = (
            body.max_image_side
            if body.max_image_side is not None
            else settings.solver_max_image_side
        )
        if centroid_params is None:
            centroid_params = CentroidExtractionParams.from_settings(settings)

        def _run() -> dict[str, Any]:
            frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("无法读取图片 / Unable to read image")
            return centroid_extraction_preview(
                frame,
                max_stars=self._solver_max_stars,
                centroid_params=centroid_params,
                max_image_side=int(max_side),
                large_scale_bg_subtract=bool(body.large_scale_bg_subtract),
                downsample_max_side=int(settings.solver_large_scale_bg_downsample),
            )

        return await asyncio.to_thread(_run)

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """获取任务状态 / Get job status"""
        job = self._jobs.get(job_id)
        if job:
            return job.to_dict()

        job_file = self.jobs_root / f"{job_id}.json"
        if not job_file.exists():
            raise FileNotFoundError("任务不存在 / Job not found")
        return json.loads(job_file.read_text(encoding="utf-8"))

    async def get_job_result(self, job_id: str) -> dict[str, Any]:
        """获取任务结果 / Get job result"""
        status = await self.get_job_status(job_id)
        result_path = status.get("result_path")
        if not result_path:
            raise FileNotFoundError("任务结果未生成 / Result not generated")
        rp = Path(result_path)
        if not rp.exists():
            raise FileNotFoundError("结果文件不存在 / Result file not found")
        return json.loads(rp.read_text(encoding="utf-8"))

    def _persist_job(self, job: AnalysisJob) -> None:
        """持久化任务 / Persist job"""
        target = self.jobs_root / f"{job.job_id}.json"
        target.write_text(
            json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _solve_bgr_to_row(
        self,
        frame_bgr: Any,
        hint_ra_deg: float | None,
        hint_dec_deg: float | None,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
        centroid_params: CentroidExtractionParams | None = None,
        max_image_side: int | None = None,
        max_stars: int | None = None,
        large_scale_bg_subtract: bool = False,
    ) -> dict[str, Any]:
        """BGR 帧送 Tetra3 解算 / Plate-solve one BGR frame."""
        solved = self.solver.solve_from_bgr_frame(
            frame_bgr=frame_bgr,
            max_stars=int(
                max_stars if max_stars is not None else self._solver_max_stars
            ),
            hint_ra_deg=(
                hint_ra_deg if hint_ra_deg is not None else self.default_hint_ra
            ),
            hint_dec_deg=(
                hint_dec_deg if hint_dec_deg is not None else self.default_hint_dec
            ),
            solve_source="full",
            fov_estimate=fov_estimate,
            fov_max_error=fov_max_error,
            solve_timeout_ms=solve_timeout_ms,
            centroid_params=centroid_params,
            max_image_side=max_image_side,
            large_scale_bg_subtract=large_scale_bg_subtract,
        )
        return {"frame_index": 0, **solved.to_dict()}

    def _analyze_image(
        self,
        source: Path,
        hint_ra_deg: float | None,
        hint_dec_deg: float | None,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
        centroid_params: CentroidExtractionParams | None = None,
        max_image_side: int | None = None,
        max_stars: int | None = None,
        large_scale_bg_subtract: bool = False,
    ) -> list[dict[str, Any]]:
        """分析单图 / Analyze image"""
        t_total = time.perf_counter()
        t_decode = time.perf_counter()
        frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
        t_open_decode_ms = (time.perf_counter() - t_decode) * 1000.0
        if frame is None:
            raise ValueError("无法读取图片 / Unable to read image")
        row = self._solve_bgr_to_row(
            frame,
            hint_ra_deg,
            hint_dec_deg,
            fov_estimate=fov_estimate,
            fov_max_error=fov_max_error,
            solve_timeout_ms=solve_timeout_ms,
            centroid_params=centroid_params,
            max_image_side=max_image_side,
            max_stars=max_stars,
            large_scale_bg_subtract=large_scale_bg_subtract,
        )
        row["t_open_decode_ms"] = round(t_open_decode_ms, 3)
        row["t_backend_total_ms"] = round((time.perf_counter() - t_total) * 1000.0, 3)
        return [row]

    def _analyze_video(
        self,
        source: Path,
        hint_ra_deg: float | None,
        hint_dec_deg: float | None,
        frame_step: int,
        max_frames: int,
        job: AnalysisJob,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        """分析视频 / Analyze video"""
        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            raise ValueError("无法打开视频 / Unable to open video")
        hint_ra = hint_ra_deg if hint_ra_deg is not None else self.default_hint_ra
        hint_dec = hint_dec_deg if hint_dec_deg is not None else self.default_hint_dec
        results: list[dict[str, Any]] = []
        idx = -1
        processed = 0
        full_limit = max(1, max_frames)
        step = max(1, frame_step)

        while processed < full_limit:
            ok, frame = cap.read()
            if not ok:
                break
            idx += 1
            if idx % step != 0:
                continue
            stars = self.extractor.extract(frame)
            solved = self.solver.solve(
                stars=stars,
                frame_shape=frame.shape,
                hint_ra_deg=hint_ra,
                hint_dec_deg=hint_dec,
                solve_source="full",
                fov_estimate=fov_estimate,
                fov_max_error=fov_max_error,
                solve_timeout_ms=solve_timeout_ms,
            )
            hint_ra = solved.ra_deg
            hint_dec = solved.dec_deg
            results.append({"frame_index": idx, **solved.to_dict()})
            processed += 1
            job.progress = min(0.99, processed / full_limit)
            self._persist_job(job)

        cap.release()
        return results

    async def solve_video_frame(self, body: AnalysisSolveVideoFrameRequest) -> dict[str, Any]:
        """相机或视频文件单帧解算 / Single-frame solve from camera or video file."""
        t_total = time.perf_counter()
        t_open_decode_ms = None
        frame = None
        frame_id = None
        frame_ts = None
        if body.source == "camera":
            from ogscope.web.camera_shared import get_camera_manager

            t_decode = time.perf_counter()
            frame, frame_id, frame_ts = await get_camera_manager().get_raw_frame()
            t_open_decode_ms = (time.perf_counter() - t_decode) * 1000.0
        else:
            if not body.input_name:
                raise ValueError("需要 input_name / input_name required for file source")
            path = self.resolve_upload_path(body.input_name)
            if not path.is_file():
                raise FileNotFoundError("上传文件不存在 / Uploaded file not found")
            t_decode = time.perf_counter()
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                raise ValueError("无法打开视频 / Cannot open video")
            try:
                if body.time_sec is not None:
                    cap.set(cv2.CAP_PROP_POS_MSEC, float(body.time_sec) * 1000.0)
                else:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, float(body.frame_index))
                ok, frame = cap.read()
                if not ok or frame is None:
                    raise ValueError("无法读取视频帧 / Cannot read video frame")
            finally:
                cap.release()
            t_open_decode_ms = (time.perf_counter() - t_decode) * 1000.0
        centroid_params, max_stars, timeout_ms, effective_profile = (
            self._resolve_solve_profile(
                body.solve_profile, body.centroid, body.solve_timeout_ms
            )
        )
        loop = asyncio.get_running_loop()

        def _run() -> dict[str, Any]:
            return self._solve_bgr_to_row(
                frame,
                body.hint_ra_deg,
                body.hint_dec_deg,
                body.fov_estimate,
                body.fov_max_error,
                timeout_ms,
                centroid_params,
                body.max_image_side,
                max_stars,
                bool(body.large_scale_bg_subtract),
            )

        row = await loop.run_in_executor(self._solver_executor, _run)
        if t_open_decode_ms is not None:
            row["t_open_decode_ms"] = round(t_open_decode_ms, 3)
        row["t_backend_total_ms"] = round((time.perf_counter() - t_total) * 1000.0, 3)
        row["solve_profile"] = effective_profile
        # 默认精简 raw，大字段仅在 detail_level==full 时返回 / Drop heavy raw unless client asks for full detail.
        detail_level = getattr(body, "detail_level", None) or "summary"
        if detail_level != "full":
            row.pop("tetra", None)
        return {
            "success": True,
            "input_name": body.input_name or "",
            "result": row,
            "frame_id": frame_id,
            "frame_ts": frame_ts,
        }

    def lab_public_settings(self) -> dict[str, Any]:
        """分析台默认参数（供前端）/ Public defaults for analysis UI."""
        s = get_settings()
        return {
            "solver_timeout_ms": s.solver_timeout_ms,
            "star_analysis_target_fps": s.star_analysis_target_fps,
            "camera_width": s.camera_width,
            "camera_height": s.camera_height,
            "camera_fps": s.camera_fps,
            "solver_fov_deg": s.solver_fov_deg,
            "solver_max_image_side": s.solver_max_image_side,
            "solver_large_scale_bg_downsample": s.solver_large_scale_bg_downsample,
            "solve_profile_default": _SOLVE_PROFILE_DEFAULT,
            "solve_profiles": list(_SOLVE_PROFILE_OVERRIDES.keys()),
        }

    def upload_experiment_count(self, filename: str) -> dict[str, Any]:
        """引用该素材的实验条数 / Number of experiments referencing upload."""
        return {"count": self._lab.count_experiments_for_input(filename)}

    def get_experiment_asset_path(self, experiment_id: str) -> Path:
        """实验快照路径 / Snapshot path for replay."""
        return self._lab.experiment_asset_path(experiment_id)


analysis_service = AnalysisService()
