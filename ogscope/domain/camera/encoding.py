"""预览图像编码器 / Preview image encoders."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EncodedImage:
    """编码结果 / Encoded image result."""

    data: bytes
    encoder: str
    source_format: str


class PreviewEncoder(Protocol):
    """预览编码器协议 / Preview encoder protocol."""

    name: str

    def encode_jpeg(
        self, frame: Any, *, quality: int = 75, source_format: str = "RGB888"
    ) -> EncodedImage | None: ...

    def encode_png(
        self, frame: Any, *, source_format: str = "RGB888"
    ) -> bytes | None: ...


class OpenCVEncoder:
    """OpenCV 后备编码器 / OpenCV fallback encoder."""

    name = "opencv"

    @staticmethod
    def _to_cv_bgr(frame: Any, cv2_module: Any, source_format: str) -> Any:
        """按源格式转换给 OpenCV；相机默认 RGB888 / Convert source frame for OpenCV."""
        fmt = str(source_format or "RGB888").upper()
        try:
            if getattr(frame, "ndim", 0) == 3 and int(frame.shape[2]) >= 3:
                if fmt in {"RGB888", "RGB", "RGB24"}:
                    return cv2_module.cvtColor(frame, cv2_module.COLOR_RGB2BGR)
                if fmt in {"BGR888", "BGR", "BGR24"}:
                    return frame
        except Exception:
            return frame
        return frame

    def encode_jpeg(
        self, frame: Any, *, quality: int = 75, source_format: str = "RGB888"
    ) -> EncodedImage | None:
        """编码 JPEG / Encode JPEG."""
        try:
            import cv2

            frame_for_cv = self._to_cv_bgr(frame, cv2, source_format)
            ok, buf = cv2.imencode(
                ".jpg",
                frame_for_cv,
                [cv2.IMWRITE_JPEG_QUALITY, int(max(10, min(100, quality)))],
            )
            if not ok:
                return None
            return EncodedImage(buf.tobytes(), self.name, source_format)
        except Exception as exc:
            logger.debug("OpenCV JPEG encode failed / OpenCV JPEG 编码失败: %s", exc)
            return None

    def encode_png(self, frame: Any, *, source_format: str = "RGB888") -> bytes | None:
        """编码 PNG / Encode PNG."""
        try:
            import cv2

            frame_for_cv = self._to_cv_bgr(frame, cv2, source_format)
            ok, buf = cv2.imencode(".png", frame_for_cv)
            if not ok:
                return None
            return buf.tobytes()
        except Exception as exc:
            logger.debug("OpenCV PNG encode failed / OpenCV PNG 编码失败: %s", exc)
            return None


class TurboJPEGEncoder:
    """可选 TurboJPEG 编码器 / Optional TurboJPEG encoder."""

    name = "turbojpeg"

    def __init__(self) -> None:
        from turbojpeg import TJPF_BGR, TJPF_RGB, TurboJPEG

        self._jpeg = TurboJPEG()
        self._tjpf_rgb = TJPF_RGB
        self._tjpf_bgr = TJPF_BGR

    @classmethod
    def available(cls) -> bool:
        """探测 TurboJPEG 是否可用 / Check whether TurboJPEG is importable and loadable."""
        try:
            cls()
            return True
        except Exception:
            return False

    def encode_jpeg(
        self, frame: Any, *, quality: int = 75, source_format: str = "RGB888"
    ) -> EncodedImage | None:
        """编码 JPEG；TurboJPEG 支持直接输入 RGB/BGR / Encode JPEG from RGB/BGR."""
        fmt = str(source_format or "RGB888").upper()
        pixel_format = (
            self._tjpf_bgr if fmt in {"BGR888", "BGR", "BGR24"} else self._tjpf_rgb
        )
        try:
            data = self._jpeg.encode(
                frame,
                quality=int(max(10, min(100, quality))),
                pixel_format=pixel_format,
            )
            return EncodedImage(bytes(data), self.name, source_format)
        except Exception as exc:
            logger.debug("TurboJPEG encode failed / TurboJPEG 编码失败: %s", exc)
            return None

    def encode_png(self, frame: Any, *, source_format: str = "RGB888") -> bytes | None:
        """TurboJPEG 不负责 PNG，交给 OpenCV / TurboJPEG does not encode PNG; delegate elsewhere."""
        return OpenCVEncoder().encode_png(frame, source_format=source_format)


class AutoPreviewEncoder:
    """按真实首帧测速选择编码器 / Select encoder by benchmarking the first real frame."""

    def __init__(self) -> None:
        self._opencv = OpenCVEncoder()
        try:
            self._turbo: PreviewEncoder | None = TurboJPEGEncoder()
        except Exception:
            self._turbo = None
        self._selected: PreviewEncoder | None = None

    @property
    def name(self) -> str:
        """当前选择的编码器名称 / Current selected encoder name."""
        if self._selected is not None:
            return self._selected.name
        return "auto"

    def encode_jpeg(
        self, frame: Any, *, quality: int = 75, source_format: str = "RGB888"
    ) -> EncodedImage | None:
        """首帧同时试跑候选编码器，后续固定使用更快者 / Benchmark candidates once, then reuse winner."""
        if self._selected is not None:
            return self._selected.encode_jpeg(
                frame, quality=quality, source_format=source_format
            )
        if self._turbo is None:
            self._selected = self._opencv
            return self._opencv.encode_jpeg(
                frame, quality=quality, source_format=source_format
            )

        results: list[tuple[float, PreviewEncoder, EncodedImage]] = []
        for encoder in (self._opencv, self._turbo):
            t0 = time.perf_counter()
            encoded = encoder.encode_jpeg(
                frame, quality=quality, source_format=source_format
            )
            if encoded is not None:
                results.append(((time.perf_counter() - t0) * 1000.0, encoder, encoded))
        if not results:
            return None
        results.sort(key=lambda item: item[0])
        self._selected = results[0][1]
        logger.info(
            "Auto preview encoder selected %s (%.1f ms) / 自动预览编码器选择 %s (%.1f ms)",
            self._selected.name,
            results[0][0],
            self._selected.name,
            results[0][0],
        )
        return results[0][2]

    def encode_png(self, frame: Any, *, source_format: str = "RGB888") -> bytes | None:
        """PNG 仍使用 OpenCV / PNG still uses OpenCV."""
        return self._opencv.encode_png(frame, source_format=source_format)


def create_preview_encoder(preference: str = "auto") -> PreviewEncoder:
    """创建预览编码器，auto 优先 TurboJPEG / Create preview encoder; auto prefers TurboJPEG."""
    pref = str(preference or "auto").lower()
    if pref == "auto":
        return AutoPreviewEncoder()
    if pref == "turbojpeg":
        try:
            return TurboJPEGEncoder()
        except Exception as exc:
            logger.warning(
                "TurboJPEG unavailable, fallback to OpenCV / TurboJPEG 不可用，回退 OpenCV: %s",
                exc,
            )
    return OpenCVEncoder()
