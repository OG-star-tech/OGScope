"""
分析域服务 / Analysis domain services.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from ogscope.web.api.analysis.services import analysis_service
from ogscope.web.api.models.schemas import AnalysisSolveImageRequest


class AnalysisDomainService:
    """分析域门面 / Analysis domain facade."""

    def __init__(self) -> None:
        self.analysis_service = analysis_service

    def resolve_upload_file_response(self, filename: str) -> tuple[Path, str]:
        path = self.analysis_service.resolve_upload_path(filename)
        suffix = path.suffix.lower()
        media_map = {
            ".mp4": "video/mp4",
            ".m4v": "video/mp4",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
        }
        media = media_map.get(suffix)
        if not media:
            media, _ = mimetypes.guess_type(path.name)
        return path, media or "application/octet-stream"

    @staticmethod
    def parse_frame_upload_payload(payload: str) -> tuple[AnalysisSolveImageRequest, dict[str, Any]]:
        obj = json.loads(payload)
        if not isinstance(obj, dict):
            raise ValueError("payload 必须为 JSON 对象 / payload must be a JSON object")
        extras = {
            "overlay_topn_count": obj.get("overlay_topn_count"),
            "enable_polar_guide": obj.get("enable_polar_guide"),
            "solve_interval_ms": obj.get("solve_interval_ms"),
        }
        obj.pop("overlay_topn_count", None)
        obj.pop("enable_polar_guide", None)
        obj.pop("solve_interval_ms", None)
        obj.pop("time_sec", None)
        obj.pop("frame_width", None)
        obj.pop("frame_height", None)
        obj.setdefault("input_name", "__frame_upload__.jpg")
        model = AnalysisSolveImageRequest.model_validate(obj)
        return model, extras


analysis_domain_service = AnalysisDomainService()

__all__ = ["analysis_service", "analysis_domain_service", "AnalysisDomainService"]

