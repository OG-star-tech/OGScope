"""
素材分析服务 / Asset analysis services
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from ogscope.algorithms.plate_solve import PlateSolver
from ogscope.algorithms.star_extract import StarExtractor
from ogscope.config import get_settings


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

    async def save_upload(self, filename: str, payload: bytes) -> dict[str, Any]:
        """保存上传文件 / Save uploaded file"""
        safe_name = Path(filename).name
        if not safe_name:
            raise ValueError("文件名无效 / Invalid filename")
        target = self.upload_root / safe_name
        target.write_bytes(payload)
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
    ) -> dict[str, Any]:
        """创建并执行任务 / Create and execute job"""
        if input_type not in {"image", "video"}:
            raise ValueError("input_type 仅支持 image 或 video / input_type must be image or video")

        source = self.upload_root / Path(input_name).name
        if not source.exists():
            raise FileNotFoundError("上传文件不存在 / Uploaded file not found")

        job = AnalysisJob(job_id=str(uuid.uuid4()), input_name=source.name, input_type=input_type)
        self._jobs[job.job_id] = job
        self._persist_job(job)

        try:
            job.status = "running"
            job.message = "开始分析 / Analysis started"
            self._persist_job(job)
            if input_type == "image":
                results = await asyncio.to_thread(
                    self._analyze_image,
                    source=source,
                    hint_ra_deg=hint_ra_deg,
                    hint_dec_deg=hint_dec_deg,
                    fov_estimate=fov_estimate,
                    fov_max_error=fov_max_error,
                    solve_timeout_ms=solve_timeout_ms,
                )
            else:
                results = await asyncio.to_thread(
                    self._analyze_video,
                    source=source,
                    hint_ra_deg=hint_ra_deg,
                    hint_dec_deg=hint_dec_deg,
                    frame_step=frame_step,
                    max_frames=max_frames,
                    job=job,
                    fov_estimate=fov_estimate,
                    fov_max_error=fov_max_error,
                    solve_timeout_ms=solve_timeout_ms,
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
        self,
        input_name: str,
        hint_ra_deg: float | None = None,
        hint_dec_deg: float | None = None,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """直接解算单图 / Solve a single image directly"""
        source = self.upload_root / Path(input_name).name
        if not source.exists():
            raise FileNotFoundError("上传文件不存在 / Uploaded file not found")
        rows = await asyncio.to_thread(
            self._analyze_image,
            source=source,
            hint_ra_deg=hint_ra_deg,
            hint_dec_deg=hint_dec_deg,
            fov_estimate=fov_estimate,
            fov_max_error=fov_max_error,
            solve_timeout_ms=solve_timeout_ms,
        )
        return {
            "success": True,
            "input_name": source.name,
            "result": rows[0] if rows else None,
        }

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

    def _analyze_image(
        self,
        source: Path,
        hint_ra_deg: float | None,
        hint_dec_deg: float | None,
        fov_estimate: float | None = None,
        fov_max_error: float | None = None,
        solve_timeout_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        """分析单图 / Analyze image"""
        frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("无法读取图片 / Unable to read image")
        # 与 Tetra3 solve_from_image 一致：内置提星（背景减除+σ 阈值），非自研 OTSU / Match Cedar-Solve extraction
        solved = self.solver.solve_from_bgr_frame(
            frame_bgr=frame,
            max_stars=self._solver_max_stars,
            hint_ra_deg=hint_ra_deg if hint_ra_deg is not None else self.default_hint_ra,
            hint_dec_deg=hint_dec_deg if hint_dec_deg is not None else self.default_hint_dec,
            solve_source="full",
            fov_estimate=fov_estimate,
            fov_max_error=fov_max_error,
            solve_timeout_ms=solve_timeout_ms,
        )
        row = {"frame_index": 0, **solved.to_dict()}
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


analysis_service = AnalysisService()
