import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import {
  Camera,
  Circle,
  Crosshair,
  Download,
  FileText,
  FolderOpen,
  Info,
  Moon,
  Play,
  RotateCcw,
  Save,
  Settings2,
  SlidersHorizontal,
  Square,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import { useI18n } from "@shared/i18n/I18nProvider";
import { useSystemInfo } from "@shared/context/SystemInfoContext";
import { requestJson as rawRequestJson } from "@shared/transport/http";

const DEV_DEBUG_API_BASE = "/api/dev/debug";

function debugApi(path: string): string {
  return `${DEV_DEBUG_API_BASE}${path}`;
}

async function requestJson<T>(
  url: string,
  options: RequestInit & { cache?: RequestCache } = {},
): Promise<T> {
  const normalizedUrl = url.startsWith("/api/debug/")
    ? url.replace("/api/debug/", "/api/dev/debug/")
    : url;
  return rawRequestJson<T>(normalizedUrl, options);
}

type CameraInfo = {
  exposure_us?: number;
  actual_exposure_us?: number;
  analogue_gain?: number;
  actual_analogue_gain?: number;
  digital_gain?: number;
  auto_exposure?: boolean;
  contrast?: number;
  brightness?: number;
  saturation?: number;
  sharpness?: number;
  noise_reduction?: number;
  noise_reduction_mode?: string;
  ae_flicker_mode?: string;
  auto_exposure_max_us?: number;
  white_balance_mode?: string;
  white_balance_gain_r?: number;
  white_balance_gain_b?: number;
  color_mode?: string;
  actual_digital_gain?: number;
  colour_temperature?: number;
  lux?: number;
  frame_duration_limits?: number[];
  lores_enabled?: boolean;
  lores_available?: boolean;
  lores_width?: number;
  lores_height?: number;
  lores_format?: string;
  capabilities?: {
    awb_modes?: string[];
    ae_flicker?: boolean;
    noise_reduction_modes?: string[];
    manual_digital_gain?: boolean;
    lores_stream?: boolean;
    autofocus?: boolean;
    hdr?: boolean;
    [key: string]: unknown;
  };
  driver?: string;
  backend?: string;
  rotation?: number;
  flip_horizontal?: boolean;
  flip_vertical?: boolean;
  width?: number;
  height?: number;
  fps?: number;
  sampling_mode?: string;
  sensor?: string;
  [key: string]: unknown;
};

type CameraStatus = {
  streaming?: boolean;
  recording?: boolean;
  camera_ready?: boolean;
  info?: CameraInfo;
  runtime_overrides?: Record<string, unknown>;
};

type StreamMetrics = {
  target_preview_fps?: number;
  sensor_target_fps?: number;
  preview_target_fps?: number;
  actual_capture_fps?: number;
  actual_preview_fps?: number;
  actual_exposure_us?: number;
  frame_duration_us?: number;
  preview_consumers?: number;
  analysis_consumers?: number;
  recording_consumers?: number;
  jpeg_average_encode_ms?: number;
  jpeg_cached_bytes?: number;
  preview_encoder?: string;
  jpeg_encode_failures?: number;
  jpeg_source_format?: string;
  camera_driver?: string;
  camera_backend?: string;
  lores_enabled?: boolean;
  lores_available?: boolean;
  lores_width?: number;
  lores_height?: number;
  lores_format?: string;
  throttle_reason?: string | null;
  process_rss_kb?: number;
  process_swap_kb?: number;
  cma_free_kb?: number;
};

type FocusStarMetric = {
  x: number;
  y: number;
  hfd_px: number;
  fwhm_px: number;
  snr: number;
  peak_snr: number;
  roundness: number;
  concentration: number;
  aperture_radius_px: number;
  saturated: boolean;
  undersampled: boolean;
  source: "auto" | "target";
};

type FocusMetrics = {
  success: boolean;
  state: "measuring" | "low_confidence" | "no_stars";
  frame_id: number;
  timestamp: number;
  frame: { width: number; height: number };
  stars_detected: number;
  stars_measured: number;
  stars_used: number;
  detection: {
    pipeline: string;
    noise_sigma: number;
    threshold: number;
    components: number;
    rejected_large: number;
    rejected_weak: number;
    target_forced: boolean;
    measurement_rejections: Record<string, number>;
    quality_rejections: Record<string, number>;
  };
  aggregate: {
    median_hfd_px: number;
    hfd_mad_px: number;
    median_fwhm_px: number;
    median_concentration: number;
  } | null;
  selected_star: FocusStarMetric | null;
  stars: FocusStarMetric[];
  warnings: string[];
};

type FocusSample = {
  frameId: number;
  hfd: number;
};

type CameraForm = {
  exposureSeconds: number;
  gain: number;
  digitalGain: number;
  autoExposure: boolean;
  contrast: number;
  brightness: number;
  saturation: number;
  sharpness: number;
  noiseReduction: number;
  noiseReductionMode: string;
  aeFlickerMode: string;
  autoExposureMaxSeconds: number;
  whiteBalanceMode: string;
  whiteBalanceGainR: number;
  whiteBalanceGainB: number;
  colorMode: string;
};

type CameraPreset = {
  name: string;
  description?: string;
  exposure_us: number;
  analogue_gain: number;
  digital_gain?: number;
  auto_exposure?: boolean;
  contrast?: number;
  brightness?: number;
  saturation?: number;
  sharpness?: number;
  noise_reduction?: number;
  white_balance_mode?: string;
  white_balance_gain_r?: number;
  white_balance_gain_b?: number;
  rotation?: number;
  flip_horizontal?: boolean;
  flip_vertical?: boolean;
  color_mode?: string;
};

type DebugFileItem = {
  name: string;
  size: number;
  modified: string;
  type: "image" | "video";
};

type DebugFileInfo = {
  filename: string;
  size: number;
  modified: string;
  type: "image" | "video";
  exposure_us?: number;
  analogue_gain?: number;
  digital_gain?: number;
  resolution?: string;
  duration_s?: number;
  fps?: number;
};

const RES_PRESETS = ["640x360", "1280x720", "1600x900", "1920x1020"] as const;
const ROTATION_PRESETS = [0, 90, 180, 270] as const;
const FILE_PAGE_SIZE = 12;

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

function toNum(v: unknown, fallback: number): number {
  if (v == null || Number.isNaN(Number(v))) return fallback;
  return Number(v);
}

function exposureUsToSeconds(value: unknown, fallbackUs: number): number {
  return toNum(value, fallbackUs) / 1_000_000;
}

function exposureSecondsToUs(value: number): number {
  return Math.round(value * 1_000_000);
}

function formatExposureSeconds(valueUs: unknown): string {
  return `${exposureUsToSeconds(valueUs, 0).toFixed(4)} s`;
}

function cameraSettingsPayload(form: CameraForm): Record<string, unknown> {
  const { exposureSeconds, autoExposureMaxSeconds, ...settings } = form;
  return {
    ...settings,
    exposure: exposureSecondsToUs(exposureSeconds),
    autoExposureMaxUs: exposureSecondsToUs(autoExposureMaxSeconds),
  };
}

function formatSize(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let idx = 0;
  let val = bytes;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx += 1;
  }
  return `${val.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function FocusHistoryChart({ samples, emptyLabel }: { samples: FocusSample[]; emptyLabel: string }) {
  if (samples.length < 2) {
    return (
      <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-outline-variant/30 text-[11px] text-on-surface-variant">
        {emptyLabel}
      </div>
    );
  }
  const values = samples.map((sample) => sample.hfd);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(0.2, max - min);
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(1, values.length - 1)) * 320;
      const y = 76 - ((value - min) / spread) * 60;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox="0 0 320 88" className="h-24 w-full rounded-lg border border-outline-variant/20 bg-black/25" role="img">
      <line x1="0" y1="76" x2="320" y2="76" stroke="currentColor" opacity="0.18" />
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" className="text-primary" />
      <circle cx="320" cy={points.split(" ").at(-1)?.split(",")[1] ?? "44"} r="4" fill="currentColor" className="text-primary" />
    </svg>
  );
}

/**
 * 用 stream/status 探测是否还有 MJPEG 名额（勿 fetch MJPEG URL，否则会额外占用 try_acquire 与长连接重叠）。
 * Check limiter via JSON; never fetch the MJPEG URL for probe (that consumes a slot and overlaps with <img>).
 */
async function probeMjpegSlotsAvailable(): Promise<"busy" | "ok" | "fail"> {
  try {
    const res = await fetch(`${debugApi("/camera/stream/status")}`, {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!res.ok) return "fail";
    const j = (await res.json()) as { max_clients?: number; active_clients?: number };
    const maxC = Number(j.max_clients ?? 0);
    const active = Number(j.active_clients ?? 0);
    if (maxC > 0 && active >= maxC) return "busy";
    return "ok";
  } catch {
    return "fail";
  }
}

function ParamSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  disabled = false,
  unit = "",
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  unit?: string;
}) {
  const decimals = step >= 1 ? 0 : Math.min(6, Math.max(1, Math.ceil(-Math.log10(step))));
  return (
    <label className={`block ${disabled ? "opacity-50" : ""}`}>
      <div className="mb-1 flex items-center justify-between">
        <span>{label}</span>
        <span className="font-mono text-[11px]">
          {value.toFixed(decimals)}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-primary"
      />
    </label>
  );
}

export function CameraConsoleApp() {
  const { t, locale, setLocale } = useI18n();
  const { info: sysInfo } = useSystemInfo();
  const [status, setStatus] = useState<CameraStatus | null>(null);
  const [previewActive, setPreviewActive] = useState(false);
  const [streamNonce, setStreamNonce] = useState<number>(() => Date.now());
  const [err, setErr] = useState<string | null>(null);
  /** 预览区：流被占或无法拉流 / In-preview hint when MJPEG busy or stream fails */
  const [previewStreamHint, setPreviewStreamHint] = useState<string | null>(null);
  /** 是否为 503 名额占满 / True when 503 for extra copy */
  const [previewStreamIsBusy, setPreviewStreamIsBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [recordBusy, setRecordBusy] = useState(false);
  const [captureBusy, setCaptureBusy] = useState(false);
  const [fpsValue, setFpsValue] = useState("8");
  const [previewFpsValue, setPreviewFpsValue] = useState("8");
  const [resValue, setResValue] = useState("1280x720");
  const [samplingMode, setSamplingMode] = useState("supersample");
  const [runtimeDirty, setRuntimeDirty] = useState(false);
  const [showHistogram, setShowHistogram] = useState(true);
  const [showRgb, setShowRgb] = useState(true);
  const [showLuminance, setShowLuminance] = useState(false);
  const [showOverExposure, setShowOverExposure] = useState(false);
  const [histCollapsed, setHistCollapsed] = useState(false);
  const [histStats, setHistStats] = useState({ mean: 0, std: 0, over: 0 });
  /** 最近约 1s 内画面像素变化次数（rAF 采样）/ ~1s sliding window from pixel deltas */
  const [liveFps, setLiveFps] = useState(0);
  /** 与 OGSCOPE_SHARED_PREVIEW_FPS 一致：共享抓帧与 MJPEG 最小帧间隔 / Env stream pacing cap */
  const [streamMetrics, setStreamMetrics] = useState<StreamMetrics | null>(null);
  const [focusActive, setFocusActive] = useState(false);
  const [focusBusy, setFocusBusy] = useState(false);
  const [focusMetrics, setFocusMetrics] = useState<FocusMetrics | null>(null);
  const [focusHistory, setFocusHistory] = useState<FocusSample[]>([]);
  const [focusBestHfd, setFocusBestHfd] = useState<number | null>(null);
  const [focusTarget, setFocusTarget] = useState<{ x: number; y: number } | null>(null);
  const [focusError, setFocusError] = useState<string | null>(null);
  const [recordElapsed, setRecordElapsed] = useState(0);
  const [rotationValue, setRotationValue] = useState(180);
  const [flipHorizontal, setFlipHorizontal] = useState(false);
  const [flipVertical, setFlipVertical] = useState(false);
  const [form, setForm] = useState<CameraForm>({
    exposureSeconds: 0.005,
    gain: 1.0,
    digitalGain: 1.0,
    autoExposure: true,
    contrast: 1.0,
    brightness: 0.0,
    saturation: 1.0,
    sharpness: 1.0,
    noiseReduction: 0,
    noiseReductionMode: "fast",
    aeFlickerMode: "off",
    autoExposureMaxSeconds: 2,
    whiteBalanceMode: "auto",
    whiteBalanceGainR: 1.0,
    whiteBalanceGainB: 1.0,
    colorMode: "color",
  });
  const [formDirty, setFormDirty] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [presetDesc, setPresetDesc] = useState("");
  const [presets, setPresets] = useState<CameraPreset[]>([]);
  const [presetBusy, setPresetBusy] = useState(false);
  const [files, setFiles] = useState<DebugFileItem[]>([]);
  const [fileBusy, setFileBusy] = useState(false);
  const [fileInfo, setFileInfo] = useState<DebugFileInfo | null>(null);
  const [fileInfoBusy, setFileInfoBusy] = useState(false);
  /** 当前展开详情的列表项文件名（与 API 返回的 filename 可能不同）/ Key for which row detail is open */
  const [fileDetailKey, setFileDetailKey] = useState<string | null>(null);
  const [filePage, setFilePage] = useState(1);

  const imgRef = useRef<HTMLImageElement>(null);
  const histogramCanvasRef = useRef<HTMLCanvasElement>(null);
  const offscreenCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const offscreenCtxRef = useRef<CanvasRenderingContext2D | null>(null);
  const histogramCtxRef = useRef<CanvasRenderingContext2D | null>(null);
  const recordTickRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const focusRequestInFlightRef = useRef(false);
  const focusSessionActiveRef = useRef(false);
  const previewActiveRef = useRef(false);
  const streamStartedAtRef = useRef<number | null>(null);
  const fpsFrameTsRef = useRef<number[]>([]);
  const fpsLastHashRef = useRef<number>(0);
  const fpsSampleCanvasRef = useRef<HTMLCanvasElement | null>(null);
  /** 预览流统计重置（真实帧率见 liveFps）/ Reset preview stats (real FPS is liveFps) */
  const resetStreamStats = () => {
    fpsFrameTsRef.current = [];
    fpsLastHashRef.current = 0;
    streamStartedAtRef.current = null;
    setLiveFps(0);
  };

  const updateCameraStatus = async () => {
    try {
      const next = await requestJson<CameraStatus>("/api/debug/camera/status", { cache: "no-store" });
      setStatus(next);
      if (!next.streaming) {
        setPreviewActive(false);
        previewActiveRef.current = false;
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const clearReconnectTimer = () => {
    if (reconnectTimerRef.current != null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  const startPreview = async (): Promise<boolean> => {
    if (previewBusy) return false;
    setPreviewBusy(true);
    setErr(null);
    setPreviewStreamHint(null);
    setPreviewStreamIsBusy(false);
    try {
      clearReconnectTimer();
      if (!status?.streaming) {
        await requestJson("/api/debug/camera/start", { method: "POST" });
      }
      const nonce = Date.now();
      const probe = await probeMjpegSlotsAvailable();
      if (probe === "busy") {
        setPreviewStreamHint(t("cam.err.streamBusy"));
        setPreviewStreamIsBusy(true);
        return false;
      }
      if (probe === "fail") {
        setPreviewStreamHint(t("cam.err.streamProbeFailed"));
        setPreviewStreamIsBusy(false);
        return false;
      }
      setPreviewActive(true);
      previewActiveRef.current = true;
      setNotice(t("cam.notice.previewStart"));
      resetStreamStats();
      streamStartedAtRef.current = performance.now();
      setStreamNonce(nonce);
      await updateCameraStatus();
      return true;
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setPreviewBusy(false);
    }
  };

  const startFocusCalibration = async () => {
    if (focusBusy) return;
    setFocusBusy(true);
    setFocusError(null);
    try {
      const ready = previewActive || (await startPreview());
      if (!ready) return;
      const session = await requestJson<{
        active: boolean;
        locked: {
          exposure: number;
          gain: number;
          digitalGain: number;
          noiseReductionMode: string;
        };
      }>(debugApi("/camera/focus/session/start"), { method: "POST" });
      focusSessionActiveRef.current = session.active;
      setForm((previous) => ({
        ...previous,
        autoExposure: false,
        exposureSeconds: exposureUsToSeconds(session.locked.exposure, 5000),
        gain: session.locked.gain,
        digitalGain: session.locked.digitalGain,
        noiseReduction: 0,
        noiseReductionMode: session.locked.noiseReductionMode,
      }));
      setFormDirty(false);
      setFocusMetrics(null);
      setFocusHistory([]);
      setFocusBestHfd(null);
      setFocusTarget(null);
      setHistCollapsed(true);
      setFocusActive(true);
      window.setTimeout(() => {
        document.getElementById("focus-calibration-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 0);
    } catch (error) {
      setFocusError(error instanceof Error ? error.message : String(error));
    } finally {
      setFocusBusy(false);
    }
  };

  const stopFocusCalibration = async () => {
    if (focusBusy) return;
    setFocusBusy(true);
    setFocusActive(false);
    setFocusError(null);
    try {
      if (focusSessionActiveRef.current) {
        const session = await requestJson<{
          restored: boolean;
          restored_settings?: {
            autoExposure: boolean;
            exposure: number;
            gain: number;
            digitalGain: number;
            noiseReductionMode: string;
          };
        }>(debugApi("/camera/focus/session/stop"), { method: "POST" });
        focusSessionActiveRef.current = false;
        if (session.restored_settings) {
          setForm((previous) => ({
            ...previous,
            autoExposure: session.restored_settings!.autoExposure,
            exposureSeconds: exposureUsToSeconds(session.restored_settings!.exposure, 5000),
            gain: session.restored_settings!.gain,
            digitalGain: session.restored_settings!.digitalGain,
            noiseReductionMode: session.restored_settings!.noiseReductionMode,
            noiseReduction: session.restored_settings!.noiseReductionMode === "off" ? 0 : 1,
          }));
          setFormDirty(false);
        }
      }
    } catch (error) {
      setFocusError(error instanceof Error ? error.message : String(error));
    } finally {
      setFocusBusy(false);
    }
  };

  const resetFocusBest = () => {
    setFocusHistory([]);
    setFocusBestHfd(null);
    setFocusError(null);
  };

  const handleFocusPreviewClick = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!focusActive || !imgRef.current) return;
    if ((event.target as HTMLElement).closest("button, label, input")) return;
    const image = imgRef.current;
    const rect = event.currentTarget.getBoundingClientRect();
    const naturalWidth = image.naturalWidth || focusMetrics?.frame.width || 0;
    const naturalHeight = image.naturalHeight || focusMetrics?.frame.height || 0;
    if (naturalWidth <= 0 || naturalHeight <= 0) return;
    const scale = Math.min(rect.width / naturalWidth, rect.height / naturalHeight);
    const shownWidth = naturalWidth * scale;
    const shownHeight = naturalHeight * scale;
    const offsetX = (rect.width - shownWidth) / 2;
    const offsetY = (rect.height - shownHeight) / 2;
    const x = (event.clientX - rect.left - offsetX) / shownWidth;
    const y = (event.clientY - rect.top - offsetY) / shownHeight;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    setFocusTarget({ x, y });
    setFocusHistory([]);
    setFocusBestHfd(null);
    setFocusError(null);
  };

  const resumeFocusAutoSelection = () => {
    setFocusTarget(null);
    setFocusHistory([]);
    setFocusBestHfd(null);
    setFocusError(null);
  };

  const stopPreview = async () => {
    if (previewBusy) return;
    setPreviewBusy(true);
    setErr(null);
    try {
      // 仅卸载预览流，后端会释放消费者并让相机热驻留后延迟关闭。
      // Only detach the preview stream; backend releases the consumer and keeps the camera warm briefly.
      clearReconnectTimer();
      setPreviewActive(false);
      previewActiveRef.current = false;
      setPreviewStreamHint(null);
      setPreviewStreamIsBusy(false);
      resetStreamStats();
      if (imgRef.current) {
        imgRef.current.onload = null;
        imgRef.current.onerror = null;
        imgRef.current.src = "";
        imgRef.current.removeAttribute("src");
      }
      setStreamNonce(Date.now());
      setNotice(t("cam.notice.previewStop"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const capture = async () => {
    if (!previewActive && !status?.streaming) return;
    setCaptureBusy(true);
    setErr(null);
    try {
      const data = await requestJson<{ filename?: string }>("/api/debug/camera/capture", { method: "POST" });
      setNotice(t("cam.notice.captureSaved", { name: data.filename || "capture" }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCaptureBusy(false);
    }
  };

  const toggleRecord = async () => {
    if (recordBusy) return;
    setRecordBusy(true);
    setErr(null);
    try {
      if (status?.recording) {
        await requestJson("/api/debug/camera/record/stop", { method: "POST" });
        setNotice(t("cam.notice.recordStop"));
      } else {
        const data = await requestJson<{ filename?: string }>("/api/debug/camera/record/start", { method: "POST" });
        setNotice(t("cam.notice.recordStart", { name: data.filename || "video.avi" }));
      }
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRecordBusy(false);
    }
  };


  const applyRuntimeSettings = async () => {
    setErr(null);
    try {
      const fps = clamp(parseInt(fpsValue, 10) || 5, 1, 60);
      await requestJson(`/api/debug/camera/fps?fps=${fps}`, { method: "POST" });
      const previewFps = clamp(parseInt(previewFpsValue, 10) || 8, 1, 30);
      await requestJson(`/api/debug/camera/preview-fps?fps=${previewFps}`, {
        method: "POST",
      });
      const [w, h] = resValue.split("x").map((x) => parseInt(x, 10));
      if (w && h) {
        await requestJson(`/api/debug/camera/size?width=${w}&height=${h}`, { method: "POST" });
      }
      await requestJson(`/api/debug/camera/sampling?mode=${encodeURIComponent(samplingMode)}`, {
        method: "POST",
      });
      setNotice(t("cam.notice.runtimeApplied"));
      setRuntimeDirty(false);
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const applyCoreSettings = async () => {
    setErr(null);
    try {
      await requestJson("/api/debug/camera/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cameraSettingsPayload(form)),
      });
      setNotice(t("cam.notice.settingsApplied"));
      setFormDirty(false);
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const applyModeSettings = async () => {
    setErr(null);
    try {
      await requestJson("/api/debug/camera/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cameraSettingsPayload(form)),
      });
      setNotice(t("cam.notice.modeApplied"));
      setFormDirty(false);
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const syncFormFromStatus = (info: CameraInfo | undefined, options?: { syncRuntime?: boolean }) => {
    if (!info) return;
    const syncRuntime = options?.syncRuntime ?? true;
    setForm({
      exposureSeconds: clamp(exposureUsToSeconds(info.exposure_us, 5000), 0.0001, 0.12),
      gain: clamp(toNum(info.analogue_gain, 1.0), 1.0, 24.0),
      digitalGain: clamp(toNum(info.digital_gain, 1.0), 1.0, 8.0),
      autoExposure: Boolean(info.auto_exposure ?? true),
      contrast: clamp(toNum(info.contrast, 1.0), 0, 2),
      brightness: clamp(toNum(info.brightness, 0.0), -1, 1),
      saturation: clamp(toNum(info.saturation, 1.0), 0, 2),
      sharpness: clamp(toNum(info.sharpness, 1.0), 0, 2),
      noiseReduction: clamp(Math.round(toNum(info.noise_reduction, 0)), 0, 4),
      noiseReductionMode: String(info.noise_reduction_mode ?? "fast"),
      aeFlickerMode: String(info.ae_flicker_mode ?? "off"),
      autoExposureMaxSeconds: clamp(exposureUsToSeconds(info.auto_exposure_max_us, 2000000), 0.01, 10),
      whiteBalanceMode: String(info.white_balance_mode ?? "auto"),
      whiteBalanceGainR: clamp(toNum(info.white_balance_gain_r, 1.0), 0.1, 3.0),
      whiteBalanceGainB: clamp(toNum(info.white_balance_gain_b, 1.0), 0.1, 3.0),
      colorMode: String(info.color_mode ?? "color"),
    });
    if (syncRuntime) {
      // 用户修改运行时参数但尚未应用时，轮询状态不应把选项弹回旧值。
      // Do not let status polling snap runtime controls back while the user has unapplied edits.
      setFpsValue(String(Math.round(toNum(info.fps, 8))));
      setResValue(`${Math.round(toNum(info.width, 1280))}x${Math.round(toNum(info.height, 720))}`);
      setSamplingMode(String(info.sampling_mode ?? "supersample"));
      setRuntimeDirty(false);
    }
    setRotationValue(clamp(Math.round(toNum(info.rotation, 180)), 0, 270));
    setFlipHorizontal(Boolean(info.flip_horizontal));
    setFlipVertical(Boolean(info.flip_vertical));
    setFormDirty(false);
  };

  const applyMirror = async (nextH: boolean, nextV: boolean) => {
    setErr(null);
    try {
      await requestJson("/api/debug/camera/mirror", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flip_horizontal: nextH, flip_vertical: nextV }),
      });
      setFlipHorizontal(nextH);
      setFlipVertical(nextV);
      setNotice(t("cam.notice.mirrorApplied"));
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const applyRotation = async (rotation: number) => {
    setErr(null);
    try {
      await requestJson(`/api/debug/camera/rotation/${rotation}`, { method: "POST" });
      setRotationValue(rotation);
      setNotice(t("cam.notice.rotationApplied", { value: rotation }));
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const toggleNightMode = async (enabled: boolean) => {
    setErr(null);
    try {
      await requestJson(`/api/debug/camera/night-mode?enabled=${enabled ? "true" : "false"}`, {
        method: "POST",
      });
      setNotice(enabled ? t("cam.notice.nightOn") : t("cam.notice.nightOff"));
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const resetSettings = async () => {
    if (!window.confirm(t("cam.confirm.reset"))) return;
    setErr(null);
    try {
      await requestJson("/api/debug/camera/reset", { method: "POST" });
      setNotice(t("cam.notice.reset"));
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const backupSettings = async () => {
    setErr(null);
    try {
      await requestJson("/api/debug/camera/backup-settings", { method: "POST" });
      setNotice(t("cam.notice.backup"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const restoreSettings = async () => {
    setErr(null);
    try {
      await requestJson("/api/debug/camera/restore-settings", { method: "POST" });
      setNotice(t("cam.notice.restore"));
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const loadPresets = async () => {
    setPresetBusy(true);
    try {
      const data = await requestJson<{ presets?: CameraPreset[] }>("/api/debug/camera/presets", { cache: "no-store" });
      setPresets(data.presets ?? []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPresetBusy(false);
    }
  };

  const savePreset = async () => {
    const name = presetName.trim();
    if (!name) return;
    setPresetBusy(true);
    setErr(null);
    try {
      await requestJson("/api/debug/camera/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: presetDesc.trim(),
          exposure_us: exposureSecondsToUs(form.exposureSeconds),
          analogue_gain: form.gain,
          digital_gain: form.digitalGain,
          auto_exposure: form.autoExposure,
          contrast: form.contrast,
          brightness: form.brightness,
          saturation: form.saturation,
          sharpness: form.sharpness,
          noise_reduction: form.noiseReduction,
          white_balance_mode: form.whiteBalanceMode,
          white_balance_gain_r: form.whiteBalanceGainR,
          white_balance_gain_b: form.whiteBalanceGainB,
          rotation: rotationValue,
          flip_horizontal: flipHorizontal,
          flip_vertical: flipVertical,
          color_mode: form.colorMode,
        }),
      });
      setNotice(t("cam.notice.presetSaved", { name }));
      setPresetName("");
      setPresetDesc("");
      await loadPresets();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPresetBusy(false);
    }
  };

  const applyPreset = async (name: string) => {
    setPresetBusy(true);
    setErr(null);
    try {
      await requestJson(`/api/debug/camera/presets/${encodeURIComponent(name)}/apply`, { method: "POST" });
      setNotice(t("cam.notice.presetApplied", { name }));
      await updateCameraStatus();
      await loadPresets();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPresetBusy(false);
    }
  };

  const deletePreset = async (name: string) => {
    if (!window.confirm(t("cam.confirm.deletePreset", { name }))) return;
    setPresetBusy(true);
    setErr(null);
    try {
      await requestJson(`/api/debug/camera/presets/${encodeURIComponent(name)}`, { method: "DELETE" });
      setNotice(t("cam.notice.presetDeleted", { name }));
      await loadPresets();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPresetBusy(false);
    }
  };

  const loadFiles = async () => {
    setFileBusy(true);
    try {
      const data = await requestJson<{ files?: DebugFileItem[] }>("/api/debug/files", { cache: "no-store" });
      setFiles(data.files ?? []);
      setFilePage(1);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setFileBusy(false);
    }
  };

  const closeFileInfo = () => {
    setFileDetailKey(null);
    setFileInfo(null);
    setFileInfoBusy(false);
  };

  const showFileInfo = async (name: string) => {
    // 再次点击同一行：关闭详情 / Toggle same row: close detail
    if (fileDetailKey === name) {
      closeFileInfo();
      return;
    }
    setFileDetailKey(name);
    setFileInfo(null);
    setFileInfoBusy(true);
    setErr(null);
    try {
      const data = await requestJson<DebugFileInfo>(`/api/debug/files/${encodeURIComponent(name)}/info`, { cache: "no-store" });
      setFileInfo(data);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setFileDetailKey(null);
    } finally {
      setFileInfoBusy(false);
    }
  };

  const downloadFile = (name: string) => {
    const triggerDownload = (filename: string, href: string) => {
      const a = document.createElement("a");
      a.href = href;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    };
    triggerDownload(name, `${debugApi("/files")}/${encodeURIComponent(name)}`);
    const mediaMatch = name.match(/\.(jpe?g|png|bmp|tiff?|webp|mp4|avi|mov|mkv|wmv|flv|webm|m4v)$/i);
    if (mediaMatch) {
      const stem = name.slice(0, -mediaMatch[0].length);
      const sidecar = `${stem}.txt`;
      void (async () => {
        try {
          const res = await fetch(`${debugApi("/files")}/${encodeURIComponent(sidecar)}`);
          if (!res.ok) return;
          triggerDownload(sidecar, `${debugApi("/files")}/${encodeURIComponent(sidecar)}`);
          setNotice(t("cam.notice.downloadWithSidecar", { name, sidecar }));
        } catch {
          setNotice(t("cam.notice.download", { name }));
        }
      })();
      return;
    }
    setNotice(t("cam.notice.download", { name }));
  };

  const deleteFile = async (name: string) => {
    if (!window.confirm(t("cam.confirm.deleteFile", { name }))) return;
    setErr(null);
    try {
      await requestJson(`/api/debug/files/${encodeURIComponent(name)}`, { method: "DELETE" });
      setNotice(t("cam.notice.fileDeleted", { name }));
      if (fileDetailKey === name || fileInfo?.filename === name) closeFileInfo();
      await loadFiles();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const updateHistogramFromImage = () => {
    if (!showHistogram || !imgRef.current || !histogramCanvasRef.current) return;
    const imageElement = imgRef.current;
    if (!imageElement.naturalWidth || !imageElement.naturalHeight) return;

    if (!offscreenCanvasRef.current) {
      offscreenCanvasRef.current = document.createElement("canvas");
      offscreenCtxRef.current = offscreenCanvasRef.current.getContext("2d", { willReadFrequently: true });
    }
    if (!histogramCtxRef.current) {
      histogramCtxRef.current = histogramCanvasRef.current.getContext("2d");
    }
    if (!offscreenCtxRef.current || !histogramCtxRef.current) return;

    const maxSampleWidth = 320;
    const scale = Math.min(1, maxSampleWidth / imageElement.naturalWidth);
    const sampleWidth = Math.max(1, Math.round(imageElement.naturalWidth * scale));
    const sampleHeight = Math.max(1, Math.round(imageElement.naturalHeight * scale));
    offscreenCanvasRef.current.width = sampleWidth;
    offscreenCanvasRef.current.height = sampleHeight;
    offscreenCtxRef.current.drawImage(imageElement, 0, 0, sampleWidth, sampleHeight);
    const imageData = offscreenCtxRef.current.getImageData(0, 0, sampleWidth, sampleHeight).data;

    const histR = new Array(256).fill(0);
    const histG = new Array(256).fill(0);
    const histB = new Array(256).fill(0);
    const histL = new Array(256).fill(0);
    let lumSum = 0;
    let lumSq = 0;
    let over = 0;
    const pixelsCount = sampleWidth * sampleHeight;

    for (let i = 0; i < imageData.length; i += 4) {
      const r = imageData[i];
      const g = imageData[i + 1];
      const b = imageData[i + 2];
      const lum = Math.round(0.2126 * r + 0.7152 * g + 0.0722 * b);
      histR[r] += 1;
      histG[g] += 1;
      histB[b] += 1;
      histL[lum] += 1;
      lumSum += lum;
      lumSq += lum * lum;
      if (lum >= 250) over += 1;
    }

    const mean = pixelsCount ? lumSum / pixelsCount : 0;
    const variance = pixelsCount ? lumSq / pixelsCount - mean * mean : 0;
    setHistStats({ mean, std: Math.sqrt(Math.max(0, variance)), over: pixelsCount ? (over / pixelsCount) * 100 : 0 });

    const canvas = histogramCanvasRef.current;
    const ctx = histogramCtxRef.current;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, canvas.clientWidth || 240);
    const h = Math.max(1, canvas.clientHeight || 120);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const peak = Math.max(
      1,
      ...(showRgb ? [Math.max(...histR), Math.max(...histG), Math.max(...histB)] : [0]),
      ...(showLuminance ? [Math.max(...histL)] : [0]),
    );

    const draw = (hist: number[], color: string) => {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      for (let i = 0; i < 256; i += 1) {
        const x = (i / 255) * w;
        const y = h - (hist[i] / peak) * h;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    };

    if (showRgb) {
      draw(histR, "rgba(255,80,80,0.85)");
      draw(histG, "rgba(80,255,80,0.85)");
      draw(histB, "rgba(80,160,255,0.85)");
    }
    if (showLuminance) draw(histL, "rgba(255,255,255,0.95)");
    if (showOverExposure) {
      const warnX = (250 / 255) * w;
      ctx.fillStyle = "rgba(255,100,100,0.12)";
      ctx.fillRect(warnX, 0, w - warnX, h);
    }
  };

  useEffect(() => {
    void updateCameraStatus();
    void loadPresets();
    void loadFiles();
    const statusPoll = window.setInterval(() => {
      if (!document.hidden) {
        void updateCameraStatus();
      }
    }, 2000);
    return () => window.clearInterval(statusPoll);
  }, [status?.streaming]);

  useEffect(() => {
    if (!status?.info || formDirty) return;
    syncFormFromStatus(status.info, { syncRuntime: !runtimeDirty });
  }, [status?.info, formDirty, runtimeDirty]);

  useEffect(() => {
    if (!status?.recording) {
      if (recordTickRef.current) {
        window.clearInterval(recordTickRef.current);
        recordTickRef.current = null;
      }
      setRecordElapsed(0);
      return;
    }
    if (recordTickRef.current) return;
    const start = Date.now();
    recordTickRef.current = window.setInterval(() => {
      setRecordElapsed(Math.max(0, Math.floor((Date.now() - start) / 1000)));
    }, 1000);
    return () => {
      if (!recordTickRef.current) return;
      window.clearInterval(recordTickRef.current);
      recordTickRef.current = null;
    };
  }, [status?.recording]);

  useEffect(() => {
    previewActiveRef.current = previewActive;
    if (!previewActive) {
      clearReconnectTimer();
      setFocusActive(false);
      if (focusSessionActiveRef.current) void stopFocusCalibration();
    }
  }, [previewActive]);

  useEffect(() => () => {
    if (!focusSessionActiveRef.current) return;
    navigator.sendBeacon(debugApi("/camera/focus/session/stop"));
    focusSessionActiveRef.current = false;
  }, []);

  useEffect(() => {
    if (!focusActive || !previewActive) return;
    let cancelled = false;
    const pullFocus = async () => {
      if (focusRequestInFlightRef.current || document.hidden) return;
      focusRequestInFlightRef.current = true;
      try {
        const params = new URLSearchParams();
        if (focusTarget) {
          params.set("target_x", focusTarget.x.toFixed(6));
          params.set("target_y", focusTarget.y.toFixed(6));
        }
        const suffix = params.size > 0 ? `?${params.toString()}` : "";
        const result = await requestJson<FocusMetrics>(
          `${debugApi("/camera/focus/metrics")}${suffix}`,
          { cache: "no-store" },
        );
        if (cancelled) return;
        setFocusMetrics(result);
        setFocusError(null);
        const hfd = focusTarget
          ? result.selected_star?.hfd_px
          : result.aggregate?.median_hfd_px;
        if (typeof hfd === "number" && Number.isFinite(hfd)) {
          setFocusHistory((previous) => {
            if (previous.at(-1)?.frameId === result.frame_id) return previous;
            return [...previous, { frameId: result.frame_id, hfd }].slice(-60);
          });
          setFocusBestHfd((previous) => previous == null ? hfd : Math.min(previous, hfd));
        }
      } catch (error) {
        if (!cancelled) {
          setFocusError(error instanceof Error ? error.message : String(error));
        }
      } finally {
        focusRequestInFlightRef.current = false;
      }
    };
    void pullFocus();
    const timer = window.setInterval(pullFocus, 850);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [focusActive, previewActive, focusTarget?.x, focusTarget?.y]);

  // MJPEG 在 <img> 上通常不按帧触发 onLoad；勿用 lastFrameTime 做断流重连以免与单槽位冲突导致 503
  // MJPEG <img> rarely fires onLoad per frame; do not watchdog-reconnect on lastFrameTime (503 with single slot)

  useEffect(() => {
    if (!previewActive) return;
    fpsFrameTsRef.current = [];
    fpsLastHashRef.current = 0;
  }, [streamNonce, previewActive]);

  useEffect(() => {
    if (!previewActive) {
      fpsFrameTsRef.current = [];
      fpsLastHashRef.current = 0;
      setLiveFps(0);
      return;
    }
    if (!fpsSampleCanvasRef.current) {
      const c = document.createElement("canvas");
      c.width = 32;
      c.height = 32;
      fpsSampleCanvasRef.current = c;
    }
    const canvas = fpsSampleCanvasRef.current;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    let raf = 0;
    const tick = () => {
      const img = imgRef.current;
      if (img?.complete && img.naturalWidth > 0) {
        try {
          ctx.drawImage(img, 0, 0, 32, 32);
          const d = ctx.getImageData(0, 0, 32, 32).data;
          let h = 2166136261;
          for (let i = 0; i < d.length; i += 4) {
            h ^= d[i] + d[i + 1] + d[i + 2];
            h = Math.imul(h, 16777619);
          }
          if (fpsLastHashRef.current !== 0 && h !== fpsLastHashRef.current) {
            const tNow = performance.now();
            fpsFrameTsRef.current.push(tNow);
            const cutoff = tNow - 1000;
            while (fpsFrameTsRef.current.length && fpsFrameTsRef.current[0] < cutoff) {
              fpsFrameTsRef.current.shift();
            }
          }
          fpsLastHashRef.current = h;
        } catch {
          /* CORS / tainted canvas — ignore */
        }
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [previewActive]);

  useEffect(() => {
    if (!previewActive) {
      setLiveFps(0);
      return;
    }
    const timer = window.setInterval(() => {
      const now = performance.now();
      const cutoff = now - 1000;
      const arr = fpsFrameTsRef.current;
      while (arr.length && arr[0] < cutoff) arr.shift();
      setLiveFps(arr.length);
    }, 200);
    return () => window.clearInterval(timer);
  }, [previewActive]);

  useEffect(() => {
    if (!previewActive) {
      setStreamMetrics(null);
      return;
    }
    let cancelled = false;
    const pull = async () => {
      try {
        const res = await fetch(`${debugApi("/camera/stream/status")}`, {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!res.ok || cancelled) return;
        const j = (await res.json()) as StreamMetrics;
        if (!cancelled) {
          setStreamMetrics(j);
          const v = Number(j.preview_target_fps ?? j.target_preview_fps ?? 0);
          if (Number.isFinite(v) && v > 0 && !runtimeDirty) {
            setPreviewFpsValue(String(Math.round(v)));
          }
        }
      } catch {
        if (!cancelled) setStreamMetrics(null);
      }
    };
    void pull();
    const id = window.setInterval(pull, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [previewActive, runtimeDirty]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => () => clearReconnectTimer(), []);

  useEffect(() => {
    const total = Math.max(1, Math.ceil(files.length / FILE_PAGE_SIZE));
    if (filePage > total) {
      setFilePage(total);
    }
  }, [files.length, filePage]);

  const streamSrc = previewActive ? `${debugApi("/camera/stream")}?t=${streamNonce}` : "";
  const exposureLocked = form.autoExposure;
  const wbManual = form.whiteBalanceMode === "manual";
  const caps = status?.info?.capabilities ?? {};
  const wbModeOptions = Array.isArray(caps.awb_modes) && caps.awb_modes.length > 0
    ? caps.awb_modes
    : ["auto", "daylight", "cloudy", "tungsten", "fluorescent", "indoor", "manual", "night"];
  const nrModeOptions = Array.isArray(caps.noise_reduction_modes) && caps.noise_reduction_modes.length > 0
    ? caps.noise_reduction_modes
    : ["off", "fast", "high_quality"];
  const digitalGainWritable = caps.manual_digital_gain !== false;
  const nightModeEnabled = Boolean(status?.info?.night_mode);
  const isStreaming = previewActive;
  const canStartPreview = !previewBusy && !previewActive && !Boolean(status?.recording);
  const canStopPreview = !previewBusy && previewActive;
  const canCapture = !previewBusy && !captureBusy && isStreaming;
  const canRecordToggle = !previewBusy && !recordBusy && isStreaming;
  const focusSelectedMetric = focusTarget ? focusMetrics?.selected_star : null;
  const focusHfd = focusTarget
    ? focusSelectedMetric?.hfd_px ?? null
    : focusMetrics?.aggregate?.median_hfd_px ?? null;
  const focusFwhm = focusTarget
    ? focusSelectedMetric?.fwhm_px ?? null
    : focusMetrics?.aggregate?.median_fwhm_px ?? null;
  const focusConcentration = focusTarget
    ? focusSelectedMetric?.concentration ?? null
    : focusMetrics?.aggregate?.median_concentration ?? null;
  const focusDeltaPercent = focusHfd != null && focusBestHfd != null && focusBestHfd > 0
    ? ((focusHfd - focusBestHfd) / focusBestHfd) * 100
    : null;
  const focusRecent = focusHistory.slice(-3).map((sample) => sample.hfd);
  const focusPrevious = focusHistory.slice(-6, -3).map((sample) => sample.hfd);
  const focusAverage = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length);
  let focusGuidanceKey = "cam.focus.guidance.collecting";
  if (focusMetrics?.state === "no_stars") {
    focusGuidanceKey = "cam.focus.guidance.noStars";
  } else if (focusHistory.length >= 5 && focusDeltaPercent != null && focusDeltaPercent <= 3) {
    focusGuidanceKey = "cam.focus.guidance.best";
  } else if (focusRecent.length === 3 && focusPrevious.length === 3) {
    const trend = focusAverage(focusRecent) - focusAverage(focusPrevious);
    const threshold = Math.max(0.04, focusAverage(focusPrevious) * 0.02);
    focusGuidanceKey = trend < -threshold
      ? "cam.focus.guidance.improving"
      : trend > threshold
        ? "cam.focus.guidance.worsening"
        : "cam.focus.guidance.steady";
  }
  const focusConfidenceKey = (focusMetrics?.stars_used ?? 0) >= 5
    ? "cam.focus.confidence.high"
    : (focusMetrics?.stars_used ?? 0) >= 3
      ? "cam.focus.confidence.medium"
      : "cam.focus.confidence.low";
  const totalFilePages = Math.max(1, Math.ceil(files.length / FILE_PAGE_SIZE));
  const filePageClamped = Math.min(filePage, totalFilePages);
  const fileStart = (filePageClamped - 1) * FILE_PAGE_SIZE;
  const pagedFiles = files.slice(fileStart, fileStart + FILE_PAGE_SIZE);
  return (
    <div className="min-h-screen bg-background text-on-surface">
      <header className="sticky top-0 z-30 border-b border-outline-variant/20 bg-surface-container-low/90 px-4 py-3 backdrop-blur">
        <div className="flex w-full flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="break-words font-headline text-lg font-bold text-primary sm:text-xl">{`OGScope ${t("cam.title")}`}</h1>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <button
              type="button"
              className={`inline-flex h-7 items-center rounded px-2 py-1 ${locale === "zh" ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant"}`}
              onClick={() => setLocale("zh")}
            >
              {t("lang.zh")}
            </button>
            <button
              type="button"
              className={`inline-flex h-7 items-center rounded px-2 py-1 ${locale === "en" ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant"}`}
              onClick={() => setLocale("en")}
            >
              {t("lang.en")}
            </button>
            <a href="/debug" className="inline-flex h-7 items-center gap-1 rounded border border-outline-variant/30 px-2 py-1 hover:bg-surface-container">
              <Settings2 className="h-3.5 w-3.5" /> {t("cam.btn.system")}
            </a>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1880px] grid-cols-12 gap-4 p-4">
        <aside className="order-3 col-span-12 space-y-4 2xl:order-1 2xl:col-span-2">
          <section className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <div className="mb-2 text-sm font-semibold uppercase tracking-wider">{t("cam.controls.tools")}</div>
            <div className="mb-2 flex flex-wrap gap-1 text-xs">
              {ROTATION_PRESETS.map((rot) => (
                <button key={rot} type="button" onClick={() => void applyRotation(rot)} className={`rounded border px-2 py-1 ${rotationValue === rot ? "border-primary text-primary" : "border-outline-variant/30"}`}>
                  {rot}°
                </button>
              ))}
            </div>
            <div className="mb-2 text-[11px] text-on-surface-variant">{t("cam.mirror.hint")}</div>
            <div className="mb-2 flex flex-wrap gap-1 text-xs">
              <button
                type="button"
                onClick={() => void applyMirror(!flipHorizontal, flipVertical)}
                className={`rounded border px-2 py-1 ${flipHorizontal ? "border-primary text-primary" : "border-outline-variant/30"}`}
              >
                {t("cam.mirror.horizontal")}
              </button>
              <button
                type="button"
                onClick={() => void applyMirror(flipHorizontal, !flipVertical)}
                className={`rounded border px-2 py-1 ${flipVertical ? "border-primary text-primary" : "border-outline-variant/30"}`}
              >
                {t("cam.mirror.vertical")}
              </button>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <button type="button" onClick={() => void backupSettings()} className="rounded border border-outline-variant/40 px-2 py-1"><Save className="mr-1 inline h-3.5 w-3.5" />{t("cam.controls.backup")}</button>
              <button type="button" onClick={() => void restoreSettings()} className="rounded border border-outline-variant/40 px-2 py-1"><FolderOpen className="mr-1 inline h-3.5 w-3.5" />{t("cam.controls.restore")}</button>
              <button type="button" onClick={() => void resetSettings()} className="rounded border border-outline-variant/40 px-2 py-1">{t("cam.controls.reset")}</button>
            </div>
          </section>

          <section className="rounded-xl border border-outline-variant/20 bg-surface-container p-4 text-xs">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider">{t("cam.quick.title")}</h2>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-on-surface-variant">{t("cam.quick.nightHint")}</span>
              <button
                type="button"
                onClick={() => void toggleNightMode(true)}
                className={`rounded border px-2 py-1 ${nightModeEnabled ? "border-primary/70 text-primary" : "border-outline-variant/40"}`}
              >
                <Moon className="mr-1 inline h-3.5 w-3.5" />{t("cam.controls.nightOn")}
              </button>
              <button
                type="button"
                onClick={() => void toggleNightMode(false)}
                className={`rounded border px-2 py-1 ${nightModeEnabled ? "border-error/60 text-error" : "border-outline-variant/40 text-on-surface-variant"}`}
              >
                <Sun className="mr-1 inline h-3.5 w-3.5" />{t("cam.controls.nightOff")}
              </button>
            </div>
          </section>

          <section className="rounded-xl border border-outline-variant/20 bg-surface-container p-4 text-xs">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider">{t("cam.presets.title")}</h2>
            <div className="grid grid-cols-1 gap-2">
              <input value={presetName} onChange={(e) => setPresetName(e.target.value)} placeholder={t("cam.presets.name")} className="rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5" />
              <input value={presetDesc} onChange={(e) => setPresetDesc(e.target.value)} placeholder={t("cam.presets.desc")} className="rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5" />
            </div>
            <div className="mt-2">
              <button type="button" disabled={presetBusy || !presetName.trim()} onClick={() => void savePreset()} className="rounded border border-outline-variant/40 px-2 py-1 disabled:opacity-50">
                {t("cam.presets.save")}
              </button>
            </div>
            <div className="mt-3 max-h-48 space-y-2 overflow-auto">
              {presets.length === 0 && <div className="text-on-surface-variant">{t("cam.presets.empty")}</div>}
              {presets.map((p) => (
                <div key={p.name} className="rounded border border-outline-variant/20 p-2">
                  <div className="font-semibold">{p.name}</div>
                  <div className="text-on-surface-variant">{p.description || t("cam.presets.noDesc")}</div>
                  <div className="mt-1 text-on-surface-variant">{t("cam.controls.exposure")}: {formatExposureSeconds(p.exposure_us)} | {t("cam.controls.gain")}: {p.analogue_gain}</div>
                  <div className="mt-2 flex gap-2">
                    <button type="button" disabled={presetBusy} onClick={() => void applyPreset(p.name)} className="rounded border border-outline-variant/40 px-2 py-1 disabled:opacity-50">{t("cam.presets.apply")}</button>
                    <button type="button" disabled={presetBusy} onClick={() => void deletePreset(p.name)} className="rounded border border-outline-variant/40 px-2 py-1 disabled:opacity-50">{t("cam.presets.delete")}</button>
                  </div>
                </div>
              ))}
            </div>
          </section>

        </aside>

        <section className="order-1 col-span-12 grid grid-cols-12 items-start gap-4 2xl:order-2 2xl:col-span-10">
          <div className="col-span-12 space-y-4 2xl:col-span-9">
          <section className="self-start rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <div className="mb-2 grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1">
                CPU: <span className="font-mono">{sysInfo?.cpu_usage == null ? "—" : `${Number(sysInfo.cpu_usage).toFixed(1)}%`}</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1">
                MEM: <span className="font-mono">{sysInfo?.memory_usage == null ? "—" : `${Number(sysInfo.memory_usage).toFixed(1)}%`}</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1">
                TEMP: <span className="font-mono">{sysInfo?.temperature == null ? "—" : `${Number(sysInfo.temperature).toFixed(1)}°C`}</span>
              </div>
            </div>
            <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wider">{t("cam.preview.title")}</h2>
                <p className="mt-1 max-w-2xl text-[11px] leading-snug text-on-surface-variant">
                  {t("cam.hint.mjpegSingleStream")}
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
                <button
                  type="button"
                  disabled={focusBusy || previewBusy || Boolean(status?.recording)}
                  onClick={() => focusActive ? void stopFocusCalibration() : void startFocusCalibration()}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-medium disabled:opacity-50 ${focusActive ? "border border-primary/50 text-primary" : "bg-primary-container text-on-primary-container"}`}
                >
                  <Crosshair className="mr-1 inline h-3.5 w-3.5" />
                  {focusBusy ? t("cam.focus.starting") : focusActive ? t("cam.focus.finish") : t("cam.focus.start")}
                </button>
                <span className="font-mono text-xs text-on-surface-variant">
                  {t("cam.preview.state")}: {previewActive ? t("cam.state.streaming") : t("cam.state.idle")}
                </span>
              </div>
            </div>
            {previewStreamHint && !previewActive && (
              <div
                className="mb-2 rounded-lg border border-error/35 bg-error-container/15 px-3 py-2 text-left"
                role="alert"
              >
                <p className="text-sm font-medium text-error">{previewStreamHint}</p>
                {previewStreamIsBusy ? (
                  <p className="mt-1 max-w-2xl text-[11px] leading-snug text-on-surface-variant">
                    {t("cam.err.streamBusyHint")}
                  </p>
                ) : (
                  <p className="mt-1 max-w-2xl text-[11px] leading-snug text-on-surface-variant">
                    {t("cam.err.streamProbeDetail")}
                  </p>
                )}
              </div>
            )}
            <div
              className={`relative aspect-video overflow-hidden rounded border border-outline-variant/20 bg-black ${focusActive ? "cursor-crosshair" : ""}`}
              onClick={handleFocusPreviewClick}
            >
              {previewActive && previewStreamHint && (
                <div
                  className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-black/80 px-4 text-center"
                  role="alert"
                >
                  <p className="text-sm font-medium text-error">{previewStreamHint}</p>
                  {previewStreamIsBusy ? (
                    <p className="max-w-md text-[11px] leading-snug text-on-surface-variant">
                      {t("cam.err.streamBusyHint")}
                    </p>
                  ) : (
                    <p className="max-w-md text-[11px] leading-snug text-on-surface-variant">
                      {t("cam.err.streamProbeDetail")}
                    </p>
                  )}
                </div>
              )}
              {previewActive ? (
                <img
                  ref={imgRef}
                  alt="camera-preview"
                  className="h-full w-full object-contain"
                  src={streamSrc}
                  onLoad={() => {
                    setPreviewStreamHint(null);
                    setPreviewStreamIsBusy(false);
                    updateHistogramFromImage();
                  }}
                  onError={() => {
                    clearReconnectTimer();
                    if (!previewActiveRef.current) return;
                    const src = imgRef.current?.src;
                    void (async () => {
                      if (!previewActiveRef.current || !src) return;
                      const p = await probeMjpegSlotsAvailable();
                      if (p === "busy") {
                        setPreviewStreamHint(t("cam.err.streamBusy"));
                        setPreviewStreamIsBusy(true);
                        return;
                      }
                      reconnectTimerRef.current = window.setTimeout(() => {
                        if (previewActiveRef.current) {
                          setStreamNonce(Date.now());
                        }
                      }, 400);
                    })();
                  }}
                />
              ) : (
                <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-center text-on-surface-variant">
                  <Camera className="h-10 w-10 text-primary/80" />
                  <div className="text-sm">{t("cam.preview.emptyTitle")}</div>
                  <div className="text-xs">{t("cam.preview.emptyDesc")}</div>
                  <button
                    type="button"
                    disabled={!canStartPreview}
                    onClick={() => void startPreview()}
                    className={`rounded px-3 py-1.5 text-xs disabled:opacity-50 ${canStartPreview ? "bg-primary-container text-on-primary-container" : "border border-outline-variant/40 text-on-surface-variant"}`}
                  >
                    <Play className="mr-1 inline h-3.5 w-3.5" />
                    {previewBusy ? t("cam.btn.starting") : t("cam.btn.start")}
                  </button>
                </div>
              )}
              {previewActive && focusActive && focusMetrics?.frame ? (
                <svg
                  className="pointer-events-none absolute inset-0 z-10 h-full w-full"
                  viewBox={`0 0 ${focusMetrics.frame.width} ${focusMetrics.frame.height}`}
                  preserveAspectRatio="xMidYMid meet"
                  aria-hidden="true"
                >
                  {focusMetrics.stars.map((star, index) => {
                    const selected = focusMetrics.selected_star
                      && Math.abs(focusMetrics.selected_star.x - star.x) < 1
                      && Math.abs(focusMetrics.selected_star.y - star.y) < 1;
                    return (
                      <circle
                        key={`${focusMetrics.frame_id}-${index}`}
                        cx={star.x}
                        cy={star.y}
                        r={selected ? 16 : 10}
                        fill="none"
                        stroke={selected ? "#facc15" : "#38bdf8"}
                        strokeWidth={selected ? 3 : 2}
                        vectorEffect="non-scaling-stroke"
                      />
                    );
                  })}
                  {focusTarget ? (
                    <g
                      transform={`translate(${focusTarget.x * focusMetrics.frame.width} ${focusTarget.y * focusMetrics.frame.height})`}
                      stroke="#facc15"
                      strokeWidth="2"
                      vectorEffect="non-scaling-stroke"
                    >
                      <line x1="-12" y1="0" x2="12" y2="0" />
                      <line x1="0" y1="-12" x2="0" y2="12" />
                    </g>
                  ) : null}
                </svg>
              ) : null}
              {status?.recording && (
                <div className="absolute right-3 top-3 flex items-center gap-2 rounded bg-black/60 px-2 py-1 text-xs text-error">
                  <Circle className="h-3.5 w-3.5 fill-current" /> {t("cam.state.rec")}
                  <span className="font-mono">{`${Math.floor(recordElapsed / 60).toString().padStart(2, "0")}:${(recordElapsed % 60).toString().padStart(2, "0")}`}</span>
                </div>
              )}
              <div className="absolute left-3 top-3">
                <button
                  type="button"
                  onClick={() => setHistCollapsed((v) => !v)}
                  className="rounded border border-outline-variant/40 bg-black/70 px-2 py-1 text-xs text-white"
                >
                  {histCollapsed ? t("cam.hist.expand") : t("cam.hist.collapse")}
                </button>
              </div>
              {!histCollapsed && (
                <div className="absolute left-3 top-12 w-[360px] max-w-[calc(100%-1.5rem)] rounded border border-outline-variant/30 bg-black/70 p-2 text-white">
                  <div className="mb-2 flex flex-wrap items-center gap-3 text-[11px]">
                    <label className="inline-flex items-center gap-1"><input type="checkbox" checked={showHistogram} onChange={(e) => setShowHistogram(e.target.checked)} /> {t("cam.hist.enabled")}</label>
                    <label className="inline-flex items-center gap-1"><input type="checkbox" checked={showRgb} onChange={(e) => setShowRgb(e.target.checked)} /> RGB</label>
                    <label className="inline-flex items-center gap-1"><input type="checkbox" checked={showLuminance} onChange={(e) => setShowLuminance(e.target.checked)} /> {t("cam.hist.luminance")}</label>
                    <label className="inline-flex items-center gap-1"><input type="checkbox" checked={showOverExposure} onChange={(e) => setShowOverExposure(e.target.checked)} /> {t("cam.hist.over")}</label>
                  </div>
                  <canvas ref={histogramCanvasRef} className="h-24 w-full rounded border border-white/20 bg-black/60" />
                  <div className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
                    <div>mean: <span className="font-mono">{histStats.mean.toFixed(1)}</span></div>
                    <div>std: <span className="font-mono">{histStats.std.toFixed(1)}</span></div>
                    <div>over: <span className="font-mono">{histStats.over.toFixed(2)}%</span></div>
                  </div>
                </div>
              )}
            </div>
            <section id="focus-calibration-panel" className={`mt-3 scroll-mt-20 rounded-xl border p-3 ${focusActive ? "border-primary/45 bg-primary-container/10" : "border-outline-variant/20 bg-surface-container-low"}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Crosshair className="h-5 w-5 text-primary" />
                    <h3 className="text-sm font-semibold">{t("cam.focus.title")}</h3>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${focusActive ? "bg-primary-container text-on-primary-container" : "bg-surface-container-high text-on-surface-variant"}`}>
                      {focusActive ? t("cam.focus.active") : t("cam.focus.idle")}
                    </span>
                  </div>
                  <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-on-surface-variant">
                    {t("cam.focus.intro")}
                  </p>
                  {focusActive ? (
                    <p className="mt-1 text-[10px] text-primary">{t("cam.focus.sessionLocked")}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  {!focusActive ? (
                    <button
                      type="button"
                      disabled={focusBusy || previewBusy || Boolean(status?.recording)}
                      onClick={() => void startFocusCalibration()}
                      className="rounded-lg bg-primary-container px-3 py-2 text-xs font-medium text-on-primary-container disabled:opacity-50"
                    >
                      <Crosshair className="mr-1 inline h-4 w-4" />
                      {focusBusy ? t("cam.focus.starting") : t("cam.focus.start")}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void stopFocusCalibration()}
                      className="rounded-lg border border-error/50 px-3 py-2 text-xs text-error"
                    >
                      {t("cam.focus.finish")}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={!focusActive}
                    onClick={resetFocusBest}
                    className="rounded-lg border border-outline-variant/40 px-3 py-2 text-xs disabled:opacity-40"
                  >
                    <RotateCcw className="mr-1 inline h-3.5 w-3.5" />
                    {t("cam.focus.resetBest")}
                  </button>
                  <button
                    type="button"
                    disabled={!focusActive || focusTarget == null}
                    onClick={resumeFocusAutoSelection}
                    className="rounded-lg border border-outline-variant/40 px-3 py-2 text-xs disabled:opacity-40"
                  >
                    {t("cam.focus.autoSelect")}
                  </button>
                </div>
              </div>

              {focusActive ? (
                <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.25fr)_minmax(280px,0.75fr)]">
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="rounded-lg border border-primary/30 bg-black/20 p-3 sm:col-span-2">
                      <div className="text-[10px] uppercase tracking-wider text-on-surface-variant">
                        {t(focusTarget ? "cam.focus.currentHfd.single" : "cam.focus.currentHfd.multi")}
                      </div>
                      <div className="mt-1 flex items-end gap-2">
                        <span className="font-mono text-3xl font-semibold text-primary">{focusHfd == null ? "—" : focusHfd.toFixed(2)}</span>
                        <span className="pb-1 text-xs text-on-surface-variant">px · {t("cam.focus.lowerBetter")}</span>
                      </div>
                      <p className="mt-2 rounded-md border border-outline-variant/20 bg-surface-container-low/70 px-2 py-1.5 text-xs font-medium">
                        {t(focusGuidanceKey)}
                      </p>
                    </div>
                    <div className="rounded-lg border border-outline-variant/20 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-on-surface-variant">{t("cam.focus.bestHfd")}</div>
                      <div className="mt-1 font-mono text-xl">{focusBestHfd == null ? "—" : `${focusBestHfd.toFixed(2)} px`}</div>
                      <div className="mt-1 text-[11px] text-on-surface-variant">
                        {focusDeltaPercent == null ? "—" : `+${Math.max(0, focusDeltaPercent).toFixed(1)}%`}
                      </div>
                    </div>
                    <div className="rounded-lg border border-outline-variant/20 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-on-surface-variant">{t("cam.focus.stars")}</div>
                      <div className="mt-1 font-mono text-xl">
                        {focusMetrics?.stars_used ?? 0} / {focusMetrics?.stars_measured ?? 0} / {focusMetrics?.stars_detected ?? 0}
                      </div>
                      <div className="mt-1 text-[11px] text-on-surface-variant">{t(focusConfidenceKey)}</div>
                    </div>
                    <div className="rounded-lg border border-outline-variant/20 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-on-surface-variant">{t("cam.focus.fwhm")}</div>
                      <div className="mt-1 font-mono text-lg">{focusFwhm == null ? "—" : `${focusFwhm.toFixed(2)} px`}</div>
                    </div>
                    <div className="rounded-lg border border-outline-variant/20 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-on-surface-variant">{t("cam.focus.concentration")}</div>
                      <div className="mt-1 font-mono text-lg">{focusConcentration == null ? "—" : `${(focusConcentration * 100).toFixed(0)}%`}</div>
                    </div>
                    <div className="rounded-lg border border-outline-variant/20 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-on-surface-variant">{t("cam.focus.selectedStar")}</div>
                      <div className="mt-1 font-mono text-lg">{focusMetrics?.selected_star ? `HFD ${focusMetrics.selected_star.hfd_px.toFixed(2)}` : "—"}</div>
                      <div className="mt-1 text-[11px] text-on-surface-variant">
                        {focusTarget ? t("cam.focus.manualTarget") : t("cam.focus.autoTarget")}
                      </div>
                    </div>
                    <div className="rounded-lg border border-outline-variant/20 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-on-surface-variant">{t("cam.focus.stability")}</div>
                      <div className="mt-1 font-mono text-lg">{focusMetrics?.aggregate ? `±${focusMetrics.aggregate.hfd_mad_px.toFixed(2)} px` : "—"}</div>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-[11px] text-on-surface-variant">
                      <span>{t("cam.focus.history")}</span>
                      <span>{t("cam.focus.clickHint")}</span>
                    </div>
                    <FocusHistoryChart samples={focusHistory} emptyLabel={t("cam.focus.historyEmpty")} />
                    {focusError ? (
                      <p className="rounded-lg border border-error/35 bg-error-container/15 px-3 py-2 text-xs text-error" role="alert">{focusError}</p>
                    ) : null}
                    {focusMetrics?.warnings.includes("saturated_stars_rejected") ? (
                      <p className="rounded-lg border border-tertiary/35 bg-tertiary-container/15 px-3 py-2 text-[11px] text-tertiary">
                        {t("cam.focus.warning.saturated")}
                      </p>
                    ) : null}
                    {focusMetrics?.warnings.includes("target_star_not_found") ? (
                      <p className="rounded-lg border border-tertiary/35 bg-tertiary-container/15 px-3 py-2 text-[11px] text-tertiary">
                        {t("cam.focus.warning.targetNotFound")}
                      </p>
                    ) : null}
                    {focusMetrics?.warnings.includes("undersampled_stars") ? (
                      <p className="rounded-lg border border-primary/30 bg-primary-container/10 px-3 py-2 text-[11px] text-on-surface">
                        {t("cam.focus.warning.undersampled")}
                      </p>
                    ) : null}
                    {focusMetrics?.warnings.includes("target_may_be_hot_pixel") ? (
                      <p className="rounded-lg border border-tertiary/35 bg-tertiary-container/15 px-3 py-2 text-[11px] text-tertiary">
                        {t("cam.focus.warning.hotPixel")}
                      </p>
                    ) : null}
                    {focusMetrics?.detection ? (
                      <p className="text-[10px] leading-relaxed text-on-surface-variant">
                        {t("cam.focus.detectionSummary", {
                          measured: focusMetrics.stars_measured,
                          detected: focusMetrics.stars_detected,
                          rejected: Object.values(focusMetrics.detection.quality_rejections).reduce((sum, value) => sum + value, 0),
                        })}
                      </p>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="mt-3 grid gap-2 text-[11px] text-on-surface-variant sm:grid-cols-3">
                  <div className="rounded-lg border border-outline-variant/20 px-3 py-2">1. {t("cam.focus.step.start")}</div>
                  <div className="rounded-lg border border-outline-variant/20 px-3 py-2">2. {t("cam.focus.step.adjust")}</div>
                  <div className="rounded-lg border border-outline-variant/20 px-3 py-2">3. {t("cam.focus.step.lock")}</div>
                </div>
              )}
            </section>
            <div className="mt-3 grid grid-cols-1 gap-2 text-xs md:grid-cols-4">
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.frameFps")}: </span>
                <span className="font-mono text-on-surface">
                  {Number(streamMetrics?.actual_preview_fps ?? liveFps).toFixed(2)}
                </span>
                <p className="mt-0.5 text-[10px] leading-tight text-on-surface-variant/90">
                  {t("cam.stats.fpsMeasureNote")}
                </p>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.targetFps")}: </span>
                <span className="font-mono text-on-surface">{Number(status?.info?.fps ?? 0).toFixed(2)}</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.streamPacingFps")}: </span>
                <span className="font-mono text-on-surface">
                  {streamMetrics?.preview_target_fps ?? streamMetrics?.target_preview_fps ?? "—"}
                </span>
                <p className="mt-0.5 text-[10px] leading-tight text-on-surface-variant/90">
                  {t("cam.stats.streamPacingHint")}
                </p>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.captureFps")}: </span>
                <span className="font-mono text-on-surface">
                  {Number(streamMetrics?.actual_capture_fps ?? 0).toFixed(2)}
                </span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.encodeMs")}: </span>
                <span className="font-mono text-on-surface">
                  {Number(streamMetrics?.jpeg_average_encode_ms ?? 0).toFixed(1)} ms
                </span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.encoder")}: </span>
                <span className="font-mono text-on-surface">
                  {String(streamMetrics?.preview_encoder ?? "—")}
                </span>
                <p className="mt-0.5 text-[10px] leading-tight text-on-surface-variant/90">
                  {`${streamMetrics?.jpeg_source_format ?? "RGB888"} / fail ${streamMetrics?.jpeg_encode_failures ?? 0}`}
                </p>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.consumers")}: </span>
                <span className="font-mono text-on-surface">
                  {`${streamMetrics?.preview_consumers ?? 0}/${streamMetrics?.analysis_consumers ?? 0}/${streamMetrics?.recording_consumers ?? 0}`}
                </span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.cameraMemory")}: </span>
                <span className="font-mono text-on-surface">
                  {`${Math.round(Number(streamMetrics?.process_rss_kb ?? 0) / 1024)} / ${Math.round(Number(streamMetrics?.process_swap_kb ?? 0) / 1024)} MB`}
                </span>
              </div>
              {streamMetrics?.throttle_reason === "auto_exposure_long" && (
                <div className="rounded border border-tertiary/40 bg-tertiary-container/20 px-2 py-1.5 text-left text-tertiary">
                  {t("cam.stats.longExposureThrottle", {
                    exposure: exposureUsToSeconds(streamMetrics.actual_exposure_us, 0).toFixed(4),
                  })}
                </div>
              )}
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.uptime")}: </span>
                <span className="font-mono text-on-surface">{streamStartedAtRef.current != null ? `${Math.max(0, Math.round((performance.now() - streamStartedAtRef.current) / 1000))}s` : "0s"}</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.system.sensor")}: </span>
                <span className="font-mono">{String(status?.info?.sensor ?? "—")}</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.driver")}: </span>
                <span className="font-mono">{String(status?.info?.driver ?? streamMetrics?.camera_driver ?? "—")}</span>
                <p className="mt-0.5 text-[10px] leading-tight text-on-surface-variant/90">
                  {`${status?.info?.backend ?? streamMetrics?.camera_backend ?? "—"} · lores ${status?.info?.lores_available || streamMetrics?.lores_available ? "on" : "off"}`}
                </p>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.metadata")}: </span>
                <span className="font-mono">{status?.info?.lux != null ? `${Number(status.info.lux).toFixed(1)} lux` : "—"}</span>
                <p className="mt-0.5 text-[10px] leading-tight text-on-surface-variant/90">
                  {status?.info?.colour_temperature != null ? `${Math.round(Number(status.info.colour_temperature))}K` : "—"}
                </p>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.controls.resolution")}: </span>
                <span className="font-mono">{`${status?.info?.width ?? "—"}x${status?.info?.height ?? "—"}`}</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.preview.mode")}: </span>
                <span className="font-mono">{status?.info?.auto_exposure ? t("cam.controls.auto") : t("cam.controls.manual")}</span>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!canStartPreview}
                onClick={() => void startPreview()}
                className={`rounded px-3 py-2 text-sm disabled:opacity-50 ${canStartPreview ? "bg-primary-container text-on-primary-container" : "border border-outline-variant/40 text-on-surface-variant"}`}
              >
                <Play className="inline h-4 w-4" /> {previewBusy ? t("cam.btn.starting") : t("cam.btn.start")}
              </button>
              <button
                type="button"
                disabled={!canStopPreview}
                onClick={() => void stopPreview()}
                className={`rounded border px-3 py-2 text-sm disabled:opacity-50 ${canStopPreview ? "border-error/60 text-error hover:bg-error/10" : "border-outline-variant/40 text-on-surface-variant"}`}
              >
                <Square className="inline h-4 w-4" /> {previewBusy ? t("cam.btn.stopping") : t("cam.btn.stop")}
              </button>
              <button
                type="button"
                disabled={!canCapture}
                onClick={() => void capture()}
                className="rounded border border-outline-variant/40 px-3 py-2 text-sm disabled:opacity-50"
              >
                <Camera className="inline h-4 w-4" /> {captureBusy ? t("cam.btn.capturing") : t("cam.btn.capture")}
              </button>
              <button
                type="button"
                disabled={!canRecordToggle}
                onClick={() => void toggleRecord()}
                className={`rounded border px-3 py-2 text-sm disabled:opacity-50 ${status?.recording ? "border-error/60 bg-error/10 text-error" : "border-outline-variant/40"}`}
              >
                <Circle className="inline h-4 w-4" /> {recordBusy ? t("cam.btn.recordBusy") : status?.recording ? t("cam.btn.recordStop") : t("cam.btn.recordStart")}
              </button>
            </div>
          </section>

          <section className="rounded-xl border border-outline-variant/20 bg-surface-container p-4 text-xs">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider">{t("cam.files.title")}</h2>
            <div className="mb-2">
              <button type="button" disabled={fileBusy} onClick={() => void loadFiles()} className="rounded border border-outline-variant/40 px-2 py-1 disabled:opacity-50">
                {t("cam.files.refresh")}
              </button>
            </div>
            {fileInfoBusy && <div className="mb-2 text-on-surface-variant">{t("cam.files.loadingInfo")}</div>}
            {fileInfo && (
              <div className="mb-3 rounded border border-outline-variant/20 p-2">
                <div className="mb-2 flex items-center justify-between gap-2 font-semibold">
                  <div className="flex min-w-0 items-center gap-1">
                    <FileText className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{fileInfo.filename}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => closeFileInfo()}
                    className="shrink-0 rounded border border-outline-variant/40 p-1 text-on-surface-variant hover:bg-surface-container"
                    aria-label={t("cam.files.closeDetail")}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div>{t("cam.files.size")}: <span className="font-mono">{formatSize(fileInfo.size)}</span></div>
                <div>{t("cam.files.type")}: <span className="font-mono">{fileInfo.type}</span></div>
                <div>{t("cam.files.modified")}: <span className="font-mono">{new Date(fileInfo.modified).toLocaleString()}</span></div>
                {fileInfo.exposure_us != null && <div>{t("cam.controls.exposure")}: <span className="font-mono">{formatExposureSeconds(fileInfo.exposure_us)}</span></div>}
                {fileInfo.analogue_gain != null && <div>{t("cam.controls.gain")}: <span className="font-mono">{fileInfo.analogue_gain}</span></div>}
                {fileInfo.resolution && <div>{t("cam.controls.resolution")}: <span className="font-mono">{fileInfo.resolution}</span></div>}
              </div>
            )}
            <div className="max-h-96 space-y-2 overflow-auto">
              {files.length === 0 && !fileBusy && <div className="text-on-surface-variant">{t("cam.files.empty")}</div>}
              {pagedFiles.map((f) => (
                <div
                  key={f.name}
                  className={`rounded border p-2 ${fileDetailKey === f.name ? "border-primary/50 bg-primary/5" : "border-outline-variant/20"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-semibold">{f.name}</div>
                      <div className="text-on-surface-variant">{formatSize(f.size)} | {new Date(f.modified).toLocaleString()}</div>
                    </div>
                    <div className="shrink-0 text-on-surface-variant">{f.type}</div>
                  </div>
                  <div className="mt-2 flex gap-2">
                    <button type="button" onClick={() => downloadFile(f.name)} className="rounded border border-outline-variant/40 px-2 py-1"><Download className="mr-1 inline h-3.5 w-3.5" />{t("cam.files.download")}</button>
                    <button
                      type="button"
                      onClick={() => void showFileInfo(f.name)}
                      className={`rounded border px-2 py-1 ${fileDetailKey === f.name ? "border-primary text-primary" : "border-outline-variant/40"}`}
                    >
                      <Info className="mr-1 inline h-3.5 w-3.5" />{t("cam.files.info")}
                    </button>
                    <button type="button" onClick={() => void deleteFile(f.name)} className="rounded border border-outline-variant/40 px-2 py-1"><Trash2 className="mr-1 inline h-3.5 w-3.5" />{t("cam.files.delete")}</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between">
              <button
                type="button"
                disabled={filePageClamped <= 1}
                onClick={() => setFilePage((p) => Math.max(1, p - 1))}
                className="rounded border border-outline-variant/40 px-2 py-1 disabled:opacity-50"
              >
                {t("cam.files.prev")}
              </button>
              <div className="text-on-surface-variant">{t("cam.files.page", { current: filePageClamped, total: totalFilePages })}</div>
              <button
                type="button"
                disabled={filePageClamped >= totalFilePages}
                onClick={() => setFilePage((p) => Math.min(totalFilePages, p + 1))}
                className="rounded border border-outline-variant/40 px-2 py-1 disabled:opacity-50"
              >
                {t("cam.files.next")}
              </button>
            </div>
          </section>
          </div>

          <section className="col-span-12 grid grid-cols-12 gap-4 2xl:col-span-3 2xl:self-start">
            <section className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider">{t("cam.controls.title")}</h2>
              <div className="space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    {t("cam.controls.sensorFps")}
                    <input value={fpsValue} onChange={(e) => { setFpsValue(e.target.value); setRuntimeDirty(true); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5" />
                  </label>
                  <label className="block">
                    {t("cam.controls.previewFps")}
                    <input value={previewFpsValue} onChange={(e) => { setPreviewFpsValue(e.target.value); setRuntimeDirty(true); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5" />
                  </label>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  <label className="block">
                    {t("cam.controls.sampling")}
                    <select value={samplingMode} onChange={(e) => { setSamplingMode(e.target.value); setRuntimeDirty(true); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5">
                      <option value="supersample">supersample</option>
                      <option value="native">native</option>
                      <option value="crop">crop</option>
                    </select>
                  </label>
                </div>
                <label className="block">
                  {t("cam.controls.resolution")}
                  <div className="mt-1 grid grid-cols-2 gap-1">
                    {RES_PRESETS.map((res) => (
                      <button key={res} type="button" onClick={() => { setResValue(res); setRuntimeDirty(true); }} className={`rounded border px-2 py-1 ${resValue === res ? "border-primary text-primary" : "border-outline-variant/30"}`}>
                        {res}
                      </button>
                    ))}
                  </div>
                </label>
                <button
                  type="button"
                  disabled={!runtimeDirty}
                  onClick={() => void applyRuntimeSettings()}
                  className="w-full rounded border border-outline-variant/40 px-2 py-1.5 disabled:opacity-50"
                >
                  {t("cam.controls.applyRuntime")}
                </button>
              </div>
            </section>

            <section className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4">
              <div className="mb-2 flex items-center gap-1 text-sm font-semibold uppercase tracking-wider">
                <SlidersHorizontal className="h-3.5 w-3.5" /> {t("cam.controls.core")}
              </div>
              {formDirty && (
                <div className="mb-2 rounded border border-primary/40 bg-primary/10 px-2 py-1 text-[11px] text-primary">
                  {t("cam.controls.pendingChanges")}
                </div>
              )}
              {exposureLocked && <p className="mb-2 text-[11px] text-on-surface-variant">{t("cam.controls.lockedByAe")}</p>}
              <div className="grid grid-cols-2 gap-2 text-xs">
                <ParamSlider label={t("cam.controls.exposure")} value={form.exposureSeconds} min={0.0001} max={0.12} step={0.0001} unit=" s" disabled={exposureLocked} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, exposureSeconds: v })); }} />
                <ParamSlider label={t("cam.controls.gain")} value={form.gain} min={1} max={24} step={0.1} disabled={exposureLocked} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, gain: Number(v.toFixed(1)) })); }} />
                <ParamSlider label={t("cam.controls.digitalGain")} value={form.digitalGain} min={1} max={8} step={0.1} disabled={exposureLocked || !digitalGainWritable} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, digitalGain: Number(v.toFixed(1)) })); }} />
                <label className="block">
                  {t("cam.controls.noiseReductionMode")}
                  <select value={form.noiseReductionMode} onChange={(e) => { setFormDirty(true); setForm((p) => ({ ...p, noiseReductionMode: e.target.value })); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5">
                    {nrModeOptions.map((mode) => (
                      <option key={mode} value={mode}>{t(`cam.controls.nr.${mode}`)}</option>
                    ))}
                  </select>
                </label>
                <ParamSlider label={t("cam.controls.contrast")} value={form.contrast} min={0} max={2} step={0.1} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, contrast: Number(v.toFixed(1)) })); }} />
                <ParamSlider label={t("cam.controls.brightness")} value={form.brightness} min={-1} max={1} step={0.1} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, brightness: Number(v.toFixed(1)) })); }} />
                <ParamSlider label={t("cam.controls.saturation")} value={form.saturation} min={0} max={2} step={0.1} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, saturation: Number(v.toFixed(1)) })); }} />
                <ParamSlider label={t("cam.controls.sharpness")} value={form.sharpness} min={0} max={2} step={0.1} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, sharpness: Number(v.toFixed(1)) })); }} />
              </div>
              {!digitalGainWritable && (
                <p className="mt-2 text-[11px] text-on-surface-variant">
                  {t("cam.controls.digitalGainReadOnly")}: <span className="font-mono">{Number(status?.info?.actual_digital_gain ?? form.digitalGain).toFixed(2)}</span>
                </p>
              )}
              <div className="mt-2">
                <button
                  type="button"
                  disabled={!formDirty}
                  onClick={() => void applyCoreSettings()}
                  className="w-full rounded border border-outline-variant/40 px-2 py-1.5 disabled:opacity-50"
                >
                  {t("cam.controls.applySettings")}
                </button>
              </div>
            </section>

            <section className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4">
              <div className="mb-2 text-sm font-semibold uppercase tracking-wider">{t("cam.controls.mode")}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <label className="block">
                  {t("cam.controls.autoExposure")}
                  <select value={form.autoExposure ? "auto" : "manual"} onChange={(e) => { setForm((p) => ({ ...p, autoExposure: e.target.value === "auto" })); setFormDirty(true); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5">
                    <option value="auto">{t("cam.controls.auto")}</option>
                    <option value="manual">{t("cam.controls.manual")}</option>
                  </select>
                </label>
                <label className="block">
                  {t("cam.controls.colorMode")}
                  <select value={form.colorMode} onChange={(e) => { setForm((p) => ({ ...p, colorMode: e.target.value })); setFormDirty(true); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5">
                    <option value="color">{t("cam.controls.color")}</option>
                    <option value="mono">{t("cam.controls.mono")}</option>
                  </select>
                </label>
                <label className="block">
                  {t("cam.controls.whiteBalance")}
                  <select value={form.whiteBalanceMode} onChange={(e) => { setForm((p) => ({ ...p, whiteBalanceMode: e.target.value })); setFormDirty(true); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5">
                    {wbModeOptions.map((mode) => (
                      <option key={mode} value={mode}>{t(`cam.controls.wb.${mode}`)}</option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  {t("cam.controls.aeFlicker")}
                  <select value={form.aeFlickerMode} onChange={(e) => { setForm((p) => ({ ...p, aeFlickerMode: e.target.value })); setFormDirty(true); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5">
                    <option value="off">{t("cam.controls.off")}</option>
                    <option value="50hz">50 Hz</option>
                    <option value="60hz">60 Hz</option>
                  </select>
                </label>
                <label className="block">
                  {t("cam.controls.maxAeFrame")}
                  <input type="number" min={0.01} max={10} step={0.01} value={form.autoExposureMaxSeconds} onChange={(e) => { setForm((p) => ({ ...p, autoExposureMaxSeconds: clamp(Number(e.target.value) || 2, 0.01, 10) })); setFormDirty(true); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5" />
                </label>
                <ParamSlider label="R Gain" value={form.whiteBalanceGainR} min={0.1} max={3} step={0.1} disabled={!wbManual} onChange={(v) => { setForm((p) => ({ ...p, whiteBalanceGainR: Number(v.toFixed(1)) })); setFormDirty(true); }} />
                <ParamSlider label="B Gain" value={form.whiteBalanceGainB} min={0.1} max={3} step={0.1} disabled={!wbManual} onChange={(v) => { setForm((p) => ({ ...p, whiteBalanceGainB: Number(v.toFixed(1)) })); setFormDirty(true); }} />
              </div>
              {!wbManual && <p className="mt-2 text-[11px] text-on-surface-variant">{t("cam.controls.lockedByWb")}</p>}
              <div className="mt-2">
                <button
                  type="button"
                  onClick={() => void applyModeSettings()}
                  className="w-full rounded border border-outline-variant/40 px-2 py-1.5"
                >
                  {t("cam.controls.applyMode")}
                </button>
              </div>
            </section>
          </section>
        </section>
      </main>

      {(err || notice) && (
        <div className="fixed bottom-4 right-4 z-40 max-w-md space-y-2 text-xs">
          {err && <div className="rounded border border-error/40 bg-error-container/20 px-3 py-2 text-on-error-container">{err}</div>}
          {notice && <div className="rounded border border-primary/30 bg-primary/10 px-3 py-2 text-on-surface">{notice}</div>}
        </div>
      )}
    </div>
  );
}
