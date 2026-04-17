import { useEffect, useRef, useState } from "react";
import {
  Camera,
  Circle,
  Download,
  FileText,
  FolderOpen,
  Info,
  Moon,
  Play,
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
  analogue_gain?: number;
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
  color_mode?: string;
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

type CameraForm = {
  exposure: number;
  gain: number;
  digitalGain: number;
  autoExposure: boolean;
  contrast: number;
  brightness: number;
  saturation: number;
  sharpness: number;
  noiseReduction: number;
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

const RES_PRESETS = ["640x360", "1280x720", "1600x900", "1920x1080"] as const;
const ROTATION_PRESETS = [0, 90, 180, 270] as const;
const FILE_PAGE_SIZE = 12;

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

function toNum(v: unknown, fallback: number): number {
  if (v == null || Number.isNaN(Number(v))) return fallback;
  return Number(v);
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

/** 探测 MJPEG 是否可连：503=名额被占；ok 则立即取消 body 释放名额 / Probe stream; 503 = busy; cancel body to release slot */
async function probeMjpegStream(url: string): Promise<"busy" | "ok" | "fail"> {
  try {
    const res = await fetch(url, { cache: "no-store", credentials: "same-origin" });
    if (res.status === 503) return "busy";
    if (!res.ok) return "fail";
    await res.body?.cancel().catch(() => {});
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
  return (
    <label className={`block ${disabled ? "opacity-50" : ""}`}>
      <div className="mb-1 flex items-center justify-between">
        <span>{label}</span>
        <span className="font-mono text-[11px]">
          {value.toFixed(step >= 1 ? 0 : step >= 0.1 ? 1 : 2)}
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
  const [fpsValue, setFpsValue] = useState("5");
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
  const [recordElapsed, setRecordElapsed] = useState(0);
  const [rotationValue, setRotationValue] = useState(180);
  const [flipHorizontal, setFlipHorizontal] = useState(false);
  const [flipVertical, setFlipVertical] = useState(false);
  const [form, setForm] = useState<CameraForm>({
    exposure: 5000,
    gain: 1.0,
    digitalGain: 1.0,
    autoExposure: true,
    contrast: 1.0,
    brightness: 0.0,
    saturation: 1.0,
    sharpness: 1.0,
    noiseReduction: 0,
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

  const startPreview = async () => {
    if (previewBusy) return;
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
      const streamUrl = `${debugApi("/camera/stream")}?t=${nonce}`;
      const probe = await probeMjpegStream(streamUrl);
      if (probe === "busy") {
        setPreviewStreamHint(t("cam.err.streamBusy"));
        setPreviewStreamIsBusy(true);
        return;
      }
      if (probe === "fail") {
        setPreviewStreamHint(t("cam.err.streamProbeFailed"));
        setPreviewStreamIsBusy(false);
        return;
      }
      setPreviewActive(true);
      previewActiveRef.current = true;
      setNotice(t("cam.notice.previewStart"));
      resetStreamStats();
      streamStartedAtRef.current = performance.now();
      setStreamNonce(nonce);
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const stopPreview = async () => {
    if (previewBusy) return;
    setPreviewBusy(true);
    setErr(null);
    try {
      // 先卸载预览，释放长连接，再通知后端停止 / Release stream before stop API
      clearReconnectTimer();
      setPreviewActive(false);
      previewActiveRef.current = false;
      setPreviewStreamHint(null);
      setPreviewStreamIsBusy(false);
      resetStreamStats();
      setStatus((prev) => (prev ? { ...prev, streaming: false, recording: false } : prev));
      if (imgRef.current) {
        imgRef.current.onload = null;
        imgRef.current.onerror = null;
        imgRef.current.src = "";
        imgRef.current.removeAttribute("src");
      }
      setStreamNonce(Date.now());
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      await requestJson("/api/debug/camera/stop", { method: "POST" });
      setNotice(t("cam.notice.previewStop"));
      await updateCameraStatus();
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
        body: JSON.stringify(form),
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
      await requestJson(`/api/debug/camera/auto-exposure?enabled=${form.autoExposure ? "true" : "false"}`, {
        method: "POST",
      });
      await requestJson(
        `/api/debug/camera/white-balance?mode=${encodeURIComponent(form.whiteBalanceMode)}&gain_r=${form.whiteBalanceGainR}&gain_b=${form.whiteBalanceGainB}`,
        { method: "POST" },
      );
      await requestJson(`/api/debug/camera/color-mode?color_mode=${encodeURIComponent(form.colorMode)}`, {
        method: "POST",
      });
      setNotice(t("cam.notice.modeApplied"));
      await updateCameraStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const syncFormFromStatus = (info: CameraInfo | undefined) => {
    if (!info) return;
    setForm({
      exposure: clamp(Math.round(toNum(info.exposure_us, 5000)), 100, 120000),
      gain: clamp(toNum(info.analogue_gain, 1.0), 1.0, 24.0),
      digitalGain: clamp(toNum(info.digital_gain, 1.0), 1.0, 8.0),
      autoExposure: Boolean(info.auto_exposure ?? true),
      contrast: clamp(toNum(info.contrast, 1.0), 0, 2),
      brightness: clamp(toNum(info.brightness, 0.0), -1, 1),
      saturation: clamp(toNum(info.saturation, 1.0), 0, 2),
      sharpness: clamp(toNum(info.sharpness, 1.0), 0, 2),
      noiseReduction: clamp(Math.round(toNum(info.noise_reduction, 0)), 0, 4),
      whiteBalanceMode: String(info.white_balance_mode ?? "auto"),
      whiteBalanceGainR: clamp(toNum(info.white_balance_gain_r, 1.0), 0.1, 3.0),
      whiteBalanceGainB: clamp(toNum(info.white_balance_gain_b, 1.0), 0.1, 3.0),
      colorMode: String(info.color_mode ?? "color"),
    });
    setFpsValue(String(Math.round(toNum(info.fps, 5))));
    setResValue(`${Math.round(toNum(info.width, 1280))}x${Math.round(toNum(info.height, 720))}`);
    setSamplingMode(String(info.sampling_mode ?? "supersample"));
    setRuntimeDirty(false);
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
          exposure_us: form.exposure,
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
    syncFormFromStatus(status.info);
  }, [status?.info, formDirty]);

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
    }
  }, [previewActive]);

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
  const nightModeEnabled = Boolean(status?.info?.night_mode);
  const isStreaming = previewActive;
  const canStartPreview = !previewBusy && !previewActive && !Boolean(status?.recording);
  const canStopPreview = !previewBusy && previewActive;
  const canCapture = !previewBusy && !captureBusy && isStreaming;
  const canRecordToggle = !previewBusy && !recordBusy && isStreaming;
  const totalFilePages = Math.max(1, Math.ceil(files.length / FILE_PAGE_SIZE));
  const filePageClamped = Math.min(filePage, totalFilePages);
  const fileStart = (filePageClamped - 1) * FILE_PAGE_SIZE;
  const pagedFiles = files.slice(fileStart, fileStart + FILE_PAGE_SIZE);
  return (
    <div className="min-h-screen bg-background text-on-surface">
      <header className="sticky top-0 z-30 border-b border-outline-variant/20 bg-surface-container-low/90 px-4 py-3 backdrop-blur">
        <div className="flex w-full items-center justify-between gap-4">
          <div>
            <h1 className="font-headline text-xl font-bold text-primary">{`OGScope ${t("cam.title")}`}</h1>
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
        <aside className="order-3 col-span-12 space-y-4 xl:order-1 xl:col-span-2">
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
            <div className="grid grid-cols-2 gap-2">
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
                  <div className="mt-1 text-on-surface-variant">{t("cam.controls.exposure")}: {p.exposure_us}us | {t("cam.controls.gain")}: {p.analogue_gain}</div>
                  <div className="mt-2 flex gap-2">
                    <button type="button" disabled={presetBusy} onClick={() => void applyPreset(p.name)} className="rounded border border-outline-variant/40 px-2 py-1 disabled:opacity-50">{t("cam.presets.apply")}</button>
                    <button type="button" disabled={presetBusy} onClick={() => void deletePreset(p.name)} className="rounded border border-outline-variant/40 px-2 py-1 disabled:opacity-50">{t("cam.presets.delete")}</button>
                  </div>
                </div>
              ))}
            </div>
          </section>

        </aside>

        <section className="order-1 col-span-12 grid grid-cols-12 items-start gap-4 xl:order-2 xl:col-span-10">
          <div className="col-span-12 space-y-4 xl:col-span-9">
          <section className="self-start rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <div className="mb-2 grid grid-cols-3 gap-2 text-xs">
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1">
                CPU: <span className="font-mono">{Number(sysInfo?.cpu_usage ?? 0).toFixed(1)}%</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1">
                MEM: <span className="font-mono">{Number(sysInfo?.memory_usage ?? 0).toFixed(1)}%</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1">
                TEMP: <span className="font-mono">{Number(sysInfo?.temperature ?? 0).toFixed(1)}°C</span>
              </div>
            </div>
            <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wider">{t("cam.preview.title")}</h2>
                <p className="mt-1 max-w-2xl text-[11px] leading-snug text-on-surface-variant">
                  {t("cam.hint.mjpegSingleStream")}
                </p>
              </div>
              <div className="shrink-0 font-mono text-xs text-on-surface-variant">
                {t("cam.preview.state")}: {status?.streaming ? t("cam.state.streaming") : t("cam.state.idle")}
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
            <div className="relative aspect-video overflow-hidden rounded border border-outline-variant/20 bg-black">
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
                      const p = await probeMjpegStream(src);
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
            <div className="mt-3 grid grid-cols-1 gap-2 text-xs md:grid-cols-4">
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.frameFps")}: </span>
                <span className="font-mono text-on-surface">{liveFps.toFixed(2)}</span>
                <p className="mt-0.5 text-[10px] leading-tight text-on-surface-variant/90">
                  {t("cam.stats.fpsMeasureNote")}
                </p>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.targetFps")}: </span>
                <span className="font-mono text-on-surface">{Number(status?.info?.fps ?? 0).toFixed(2)}</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.stats.uptime")}: </span>
                <span className="font-mono text-on-surface">{streamStartedAtRef.current != null ? `${Math.max(0, Math.round((performance.now() - streamStartedAtRef.current) / 1000))}s` : "0s"}</span>
              </div>
              <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-1.5 text-left">
                <span className="text-on-surface-variant">{t("cam.system.sensor")}: </span>
                <span className="font-mono">{String(status?.info?.sensor ?? "—")}</span>
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
                {fileInfo.exposure_us != null && <div>{t("cam.controls.exposure")}: <span className="font-mono">{fileInfo.exposure_us}us</span></div>}
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

          <section className="col-span-12 grid grid-cols-12 gap-4 xl:col-span-3 xl:self-start">
            <section className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider">{t("cam.controls.title")}</h2>
              <div className="space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    {t("cam.controls.fps")}
                    <input value={fpsValue} onChange={(e) => { setFpsValue(e.target.value); setRuntimeDirty(true); }} className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5" />
                  </label>
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
                <ParamSlider label={t("cam.controls.exposure")} value={form.exposure} min={100} max={120000} step={100} unit="us" disabled={exposureLocked} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, exposure: v })); }} />
                <ParamSlider label={t("cam.controls.gain")} value={form.gain} min={1} max={24} step={0.1} disabled={exposureLocked} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, gain: Number(v.toFixed(1)) })); }} />
                <ParamSlider label={t("cam.controls.digitalGain")} value={form.digitalGain} min={1} max={8} step={0.1} disabled={exposureLocked} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, digitalGain: Number(v.toFixed(1)) })); }} />
                <ParamSlider label={t("cam.controls.noiseReduction")} value={form.noiseReduction} min={0} max={4} step={1} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, noiseReduction: Math.round(v) })); }} />
                <ParamSlider label={t("cam.controls.contrast")} value={form.contrast} min={0} max={2} step={0.1} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, contrast: Number(v.toFixed(1)) })); }} />
                <ParamSlider label={t("cam.controls.brightness")} value={form.brightness} min={-1} max={1} step={0.1} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, brightness: Number(v.toFixed(1)) })); }} />
                <ParamSlider label={t("cam.controls.saturation")} value={form.saturation} min={0} max={2} step={0.1} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, saturation: Number(v.toFixed(1)) })); }} />
                <ParamSlider label={t("cam.controls.sharpness")} value={form.sharpness} min={0} max={2} step={0.1} onChange={(v) => { setFormDirty(true); setForm((p) => ({ ...p, sharpness: Number(v.toFixed(1)) })); }} />
              </div>
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
                    <option value="auto">{t("cam.controls.auto")}</option>
                    <option value="manual">{t("cam.controls.manual")}</option>
                    <option value="night">{t("cam.controls.night")}</option>
                  </select>
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
