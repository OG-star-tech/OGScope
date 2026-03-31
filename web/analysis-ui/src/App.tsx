import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Database,
  FlaskConical,
  Grid3x3,
  History,
  Home,
  Loader2,
  RefreshCw,
  RotateCcw,
  Trash2,
  Upload,
  ZoomIn,
  ZoomOut,
  ChevronDown,
} from "lucide-react";
import {
  BatchRun,
  debugCaptureFileUrl,
  deleteExperimentRecord,
  deletePoolUpload,
  experimentAssetUrl,
  exportExperiments,
  fetchDebugFileInfo,
  fetchDebugFiles,
  fetchExperiments,
  fetchLabSettings,
  fetchPresets,
  fetchSystemInfo,
  fetchUploadExperimentCount,
  fetchUploadFileInfo,
  fetchUploads,
  importFromDebug,
  replaceTranscodedVideo,
  saveExperiment,
  saveUserPreset,
  solveBatch,
  solveFrameFromBlob,
  solveImage,
  solveVideoFrame,
  uploadFile,
  uploadFileUrl,
  type DebugFileRow,
  type LabPublicSettings,
  type SolveParams,
  type UploadFileRow,
} from "./api";
import {
  drawSolveOverlay,
  drawSolveOverlayVideo,
  type SolveOverlay,
} from "./drawOverlay";
import { transcodeAviToMp4 } from "./utils/transcode";
import { useI18n } from "./i18n/I18nProvider";
import { buildMetaCaptionRows } from "./utils/metaCaption";
import { formatDateTime, formatFileSize } from "./utils/format";
import {
  formatAngleDeg,
  formatProbLine,
  parseSolveResult,
} from "./utils/solveDisplay";

type View = "lab_image" | "lab_video" | "pool" | "history";

const defaultParams = (): SolveParams => ({
  hint_ra_deg: 45,
  hint_dec_deg: 80,
  fov_estimate: 11,
  fov_max_error: undefined,
  solve_timeout_ms: 1500,
  solve_profile: "balanced",
  max_image_side: 1600,
  large_scale_bg_subtract: false,
  detail_level: "summary",
  centroid: {
    sigma: 2.5,
    max_area: 400,
    min_area: 5,
    filtsize: 25,
    binary_open: true,
    max_axis_ratio: undefined,
  },
});

function metricsFromResult(result: Record<string, unknown> | null): Record<string, unknown> {
  if (!result) return {};
  return {
    matches: result.matches,
    rmse_arcsec: result.rmse_arcsec,
    status: result.status,
    prob: result.prob,
    t_solve_ms: result.t_solve_ms,
  };
}

function countStarsFromOverlay(
  result: Record<string, unknown> | null,
): number | null {
  if (!result) return null;
  const ov = result.solve_overlay as SolveOverlay | undefined;
  if (ov?.stars_matched?.length) return ov.stars_matched.length;
  if (ov?.stars_all_centroids?.length) return ov.stars_all_centroids.length;
  if (typeof result.matches === "number") return result.matches;
  return null;
}

const HISTORY_PAGE_SIZE = 30;
/** 调试控制台素材列表每页条数 / Items per page for debug media list */
const DEBUG_PAGE_SIZE = 6;

function isImageAsset(name: string): boolean {
  return /\.(jpe?g|png|webp|bmp|gif|fits?)$/i.test(name);
}
function isVideoAsset(name: string): boolean {
  return /\.(mp4|mov|webm|mkv|avi)$/i.test(name);
}

function compactFilename(name: string, head = 16, tail = 14): string {
  if (name.length <= head + tail + 1) return name;
  return `${name.slice(0, head)}...${name.slice(-tail)}`;
}

export default function App() {
  const { t, locale, setLocale } = useI18n();
  const [view, setView] = useState<View>("lab_image");
  const [uploads, setUploads] = useState<UploadFileRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [params, setParams] = useState<SolveParams>(defaultParams);
  const [official, setOfficial] = useState<
    Array<{ id: string; name: string; params: SolveParams }>
  >([]);
  const [userPresets, setUserPresets] = useState<
    Array<{ id: string; name: string; params: SolveParams }>
  >([]);
  const [selectedPresetIds, setSelectedPresetIds] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<Record<string, unknown> | null>(null);
  const [batchPack, setBatchPack] = useState<{
    results: Array<Record<string, unknown>>;
  } | null>(null);
  const [historyQ, setHistoryQ] = useState("");
  const [historyPage, setHistoryPage] = useState(1);
  const [historyData, setHistoryData] = useState<{ items: unknown[]; total: number } | null>(
    null,
  );
  const [historyExpandId, setHistoryExpandId] = useState<string | null>(null);
  const [newPresetName, setNewPresetName] = useState("");
  const [layers, setLayers] = useState({ matched: true, pattern: true, all: true });
  const [debugFiles, setDebugFiles] = useState<DebugFileRow[]>([]);
  const [debugPick, setDebugPick] = useState<string | null>(null);
  const [debugPage, setDebugPage] = useState(1);
  const [gridOn, setGridOn] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [imgNatural, setImgNatural] = useState({ w: 0, h: 0 });
  /** 视频文件素材的像素尺寸 / Video file intrinsic size */
  const [videoNatural, setVideoNatural] = useState({ w: 0, h: 0 });
  /** 相机预览 JPEG 尺寸 / Live camera preview image size */
  const [cameraPreviewNatural, setCameraPreviewNatural] = useState({ w: 0, h: 0 });
  /** 视频台：文件预览或设备相机 / Video lab: pool file vs device camera */
  const [videoPreviewMode, setVideoPreviewMode] = useState<"file" | "camera">("file");
  /** 设备相机预览图 blob URL（与 X-Frame-Id 去重）/ Camera preview blob URL, deduped by frame id */
  const [cameraPreviewUrl, setCameraPreviewUrl] = useState<string | null>(null);
  const [videoPreviewError, setVideoPreviewError] = useState<string | null>(null);
  const [cameraSolveRunning, setCameraSolveRunning] = useState(false);
  const [fileSolveRunning, setFileSolveRunning] = useState(false);
  const [autoHoldEnabled, setAutoHoldEnabled] = useState(true);
  const [isFrozen, setIsFrozen] = useState(false);
  const [frozenFrameId, setFrozenFrameId] = useState<string | null>(null);
  const [frozenImageUrl, setFrozenImageUrl] = useState<string | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [batchRawOpen, setBatchRawOpen] = useState<Record<number, boolean>>({});
  const [singleFooterRawOpen, setSingleFooterRawOpen] = useState(false);
  /** 最近一次请求全链路耗时（含网络与渲染）/ Last request round-trip (network + render) */
  const [lastRoundTripMs, setLastRoundTripMs] = useState<number | null>(null);
  /** 最近一次解算输入来源 / Last solve input source */
  const [lastSolveSource, setLastSolveSource] = useState<"file" | "camera" | null>(null);
  /** 实时解算调度提示 / Realtime solve gate hint */
  const [lastGateHint, setLastGateHint] = useState<string | null>(null);
  /** 用户期望解算间隔（毫秒）/ User desired realtime solve interval in ms */
  const [desiredSolveIntervalMs, setDesiredSolveIntervalMs] = useState<number | null>(null);
  const [transcodeBusy, setTranscodeBusy] = useState(false);
  const [transcodeProgress, setTranscodeProgress] = useState<number | null>(null);
  const [transcodeHint, setTranscodeHint] = useState<string | null>(null);
  const [debugImportBusy, setDebugImportBusy] = useState(false);
  const [debugImportProgress, setDebugImportProgress] = useState<number | null>(null);
  const [debugImportStep, setDebugImportStep] = useState<string | null>(null);
  const [debugImportMessage, setDebugImportMessage] = useState<string | null>(null);

  const imgRef = useRef<HTMLImageElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraPreviewImgRef = useRef<HTMLImageElement>(null);
  const lastCameraFrameIdRef = useRef<string | null>(null);
  const cameraSolveTimerRef = useRef<number | null>(null);
  const fileSolveTimerRef = useRef<number | null>(null);
  const cameraSolveInFlightRef = useRef(false);
  const fileSolveInFlightRef = useRef(false);
  const cvRef = useRef<HTMLCanvasElement>(null);
  const [sysOverview, setSysOverview] = useState<import("./api").SystemInfo | null>(null);
  const [labSettings, setLabSettings] = useState<LabPublicSettings | null>(null);

  const intervalMinMs = labSettings?.star_analysis_min_interval_ms ?? 2000;
  const intervalMaxMs = labSettings?.star_analysis_max_interval_ms ?? 12000;
  const defaultIntervalMs = useMemo(() => {
    const fps = labSettings?.star_analysis_target_fps ?? 2 / 3;
    const clampedFps = Math.min(Math.max(fps, 0.2), 5.0);
    return Math.round(1000 / clampedFps);
  }, [labSettings]);
  const starAnalysisIntervalMs = useMemo(() => {
    const raw = desiredSolveIntervalMs ?? defaultIntervalMs;
    return Math.min(Math.max(raw, intervalMinMs), intervalMaxMs);
  }, [defaultIntervalMs, desiredSolveIntervalMs, intervalMaxMs, intervalMinMs]);

  const loadLists = useCallback(async () => {
    const [u, o, usr] = await Promise.all([
      fetchUploads(),
      fetchPresets("official"),
      fetchPresets("user"),
    ]);
    setUploads(u.files);
    setOfficial(o.presets as typeof official);
    setUserPresets(usr.presets as typeof userPresets);
  }, []);

  const loadDebugFiles = useCallback(() => {
    fetchDebugFiles()
      .then((r) => setDebugFiles(r.files))
      .catch(() => setDebugFiles([]));
  }, []);

  useEffect(() => {
    fetchLabSettings()
      .then((s) => {
        setLabSettings(s);
        const initialMs = Math.round(1000 / Math.min(Math.max(s.star_analysis_target_fps, 0.2), 5.0));
        const bounded = Math.min(
          Math.max(initialMs, s.star_analysis_min_interval_ms),
          s.star_analysis_max_interval_ms,
        );
        setDesiredSolveIntervalMs(bounded);
      })
      .catch(() => setLabSettings(null));
  }, []);

  useEffect(() => {
    loadLists().catch((e) => setErr(String(e)));
  }, [loadLists]);

  useEffect(() => {
    loadDebugFiles();
  }, [loadDebugFiles]);

  useEffect(() => {
    if (view !== "history") return;
    fetchExperiments(historyQ, historyPage, HISTORY_PAGE_SIZE)
      .then(setHistoryData)
      .catch((e) => setErr(String(e)));
  }, [view, historyQ, historyPage]);

  useEffect(() => {
    if (!selected) {
      setMeta(null);
      return;
    }
    let cancelled = false;
    setMetaLoading(true);
    (async () => {
      try {
        const u = await fetchUploadFileInfo(selected);
        if (cancelled) return;
        let merged: Record<string, unknown> = { ...u };
        try {
          const d = await fetchDebugFileInfo(selected);
          merged = { ...d, ...u };
        } catch {
          /* 仅上传素材时调试目录无同名文件 / No debug file */
        }
        setMeta(merged);
      } catch {
        try {
          const d = await fetchDebugFileInfo(selected);
          if (!cancelled) setMeta(d);
        } catch {
          if (!cancelled) setMeta(null);
        }
      } finally {
        if (!cancelled) setMetaLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  /** 切换素材时清空上一张的解算结果，避免误读 / Clear solve state when switching assets */
  useEffect(() => {
    setLastResult(null);
    setBatchPack(null);
    setBatchRawOpen({});
    setSingleFooterRawOpen(false);
    setLastRoundTripMs(null);
    setLastSolveSource(null);
    setVideoPreviewMode("file");
    setVideoPreviewError(null);
  }, [selected]);

  const overlay = useMemo(() => {
    const r = lastResult?.result as Record<string, unknown> | undefined;
    if (!r) return null;
    const base = (r.solve_overlay || null) as SolveOverlay | null;
    if (!base) return null;
    const ext = (r.overlay_ext || null) as SolveOverlay["overlay_ext"] | null;
    return { ...base, overlay_ext: ext || undefined };
  }, [lastResult]);

  const resultRow = useMemo(() => {
    return (lastResult?.result as Record<string, unknown> | undefined) ?? null;
  }, [lastResult]);

  const starCount = useMemo(() => countStarsFromOverlay(resultRow), [resultRow]);

  /** 主预览区像素尺寸（图片 / 视频文件 / 相机 JPEG）/ Pixel size for metrics panel */
  const previewPixelDims = useMemo(() => {
    if (view === "lab_image") return imgNatural;
    if (view === "lab_video") {
      return videoPreviewMode === "file" ? videoNatural : cameraPreviewNatural;
    }
    return { w: 0, h: 0 };
  }, [view, videoPreviewMode, imgNatural, videoNatural, cameraPreviewNatural]);

  const previewUrl = selected ? uploadFileUrl(selected) : "";

  useEffect(() => {
    if (view !== "lab_image") return;
    const img = imgRef.current;
    const cv = cvRef.current;
    if (!img || !cv || !overlay || !selected) return;
    const draw = () => drawSolveOverlay(cv, img, overlay, layers);
    if (img.complete) draw();
    else img.onload = draw;
  }, [overlay, selected, lastResult, layers, view]);

  /** 视频文件：解算叠加 / Video file: solve overlay on current frame */
  useEffect(() => {
    if (view !== "lab_video" || videoPreviewMode !== "file") return;
    const v = videoRef.current;
    const cv = cvRef.current;
    if (!v || !cv || !overlay || !selected) return;
    const draw = () => drawSolveOverlayVideo(cv, v, overlay, layers);
    v.addEventListener("loadeddata", draw);
    v.addEventListener("seeked", draw);
    if (v.readyState >= 2) draw();
    return () => {
      v.removeEventListener("loadeddata", draw);
      v.removeEventListener("seeked", draw);
    };
  }, [overlay, layers, view, videoPreviewMode, selected, lastResult]);

  /** 设备相机预览：解算叠加在 JPEG 上 / Live camera JPEG + overlay */
  useEffect(() => {
    if (view !== "lab_video" || videoPreviewMode !== "camera") return;
    const img = cameraPreviewImgRef.current;
    const cv = cvRef.current;
    if (!img || !cv || !overlay) return;
    const draw = () => drawSolveOverlay(cv, img, overlay, layers);
    if (img.complete) draw();
    else img.onload = draw;
  }, [overlay, layers, view, videoPreviewMode, lastResult, cameraPreviewUrl]);

  /** 共享预览缓存轮询：仅当 X-Frame-Id 变化时更新图像，减少解码与重绘 / Poll shared cache; update img only on new frame id */
  useEffect(() => {
    if (view !== "lab_video" || videoPreviewMode !== "camera") return;
    let cancelled = false;
    const poll = async () => {
      if (cancelled || isFrozen) return;
      try {
        const qs = lastCameraFrameIdRef.current
          ? `?since_frame_id=${encodeURIComponent(lastCameraFrameIdRef.current)}`
          : "";
        const r = await fetch(`/api/camera/preview${qs}`, { cache: "no-store" });
        if (r.status === 304) return;
        if (!r.ok) return;
        const fid = r.headers.get("X-Frame-Id");
        if (fid != null) lastCameraFrameIdRef.current = fid;
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        setCameraPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
      } catch {
        /* 忽略单次失败 / Ignore transient errors */
      }
    };
    void poll();
    const id = window.setInterval(() => void poll(), 180);
    return () => {
      cancelled = true;
      clearInterval(id);
      setCameraPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      lastCameraFrameIdRef.current = null;
    };
  }, [view, videoPreviewMode, isFrozen]);

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    const upd = () =>
      setImgNatural({ w: img.naturalWidth || 0, h: img.naturalHeight || 0 });
    upd();
    img.addEventListener("load", upd);
    return () => img.removeEventListener("load", upd);
  }, [selected, previewUrl]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const upd = () =>
      setVideoNatural({ w: v.videoWidth || 0, h: v.videoHeight || 0 });
    v.addEventListener("loadedmetadata", upd);
    v.addEventListener("loadeddata", upd);
    upd();
    return () => {
      v.removeEventListener("loadedmetadata", upd);
      v.removeEventListener("loadeddata", upd);
    };
  }, [selected, previewUrl, view]);

  const applyPreset = (p: SolveParams) => {
    setParams({
      ...defaultParams(),
      ...p,
      centroid: { ...defaultParams().centroid, ...p.centroid },
    });
  };

  const onSingleSolve = async () => {
    if (!selected) {
      setErr(t("err.selectFile"));
      return;
    }
    setErr(null);
    setBusy(true);
    const t0 = performance.now();
    try {
      const out = (await solveImage(selected, params)) as { result?: Record<string, unknown> };
      setLastResult(out as Record<string, unknown>);
      setBatchPack(null);
      setLastSolveSource("file");
      setLastRoundTripMs(performance.now() - t0);
    } catch (e) {
      setErr(String(e));
      setLastRoundTripMs(null);
    } finally {
      setBusy(false);
    }
  };

  const onBatch = async () => {
    if (!selected) {
      setErr(t("err.selectFile"));
      return;
    }
    const runs: BatchRun[] = [];
    for (const id of selectedPresetIds) {
      const all = [...official, ...userPresets];
      const pr = all.find((x) => x.id === id);
      if (pr)
        runs.push({
          label: pr.name,
          params: structuredClone(pr.params) as SolveParams,
        });
    }
    if (runs.length === 0) {
      setErr(t("err.selectPresets"));
      return;
    }
    setErr(null);
    setBusy(true);
    const t0 = performance.now();
    try {
      const pack = (await solveBatch(selected, runs)) as { results: unknown[] };
      setBatchPack({
        results: pack.results as Array<Record<string, unknown>>,
      });
      setLastResult(null);
      setBatchRawOpen({});
      setLastSolveSource("file");
      setLastRoundTripMs(performance.now() - t0);
    } catch (e) {
      setErr(String(e));
      setLastRoundTripMs(null);
    } finally {
      setBusy(false);
    }
  };

  /** 设备相机当前帧解算（与素材池视频无关）/ Live camera frame solve */
  const onCameraSolve = async () => {
    if (cameraSolveInFlightRef.current) return;
    setErr(null);
    cameraSolveInFlightRef.current = true;
    const t0 = performance.now();
    try {
      const out = await solveVideoFrame({
        source: "camera",
        overlay_topn_count: 3,
        enable_polar_guide: true,
        solve_interval_ms: starAnalysisIntervalMs,
        solve_timeout_ms: Math.min((labSettings?.solver_timeout_ms ?? 1500) * 0.6, 1200),
        ...params,
      });
      if (out.gate_status && out.gate_status !== "SOLVED") {
        setLastGateHint(`${out.gate_status}${out.gate_reason ? `: ${out.gate_reason}` : ""}`);
      } else {
        setLastGateHint(null);
      }
      setLastResult(out as Record<string, unknown>);
      setBatchPack(null);
      setLastSolveSource("camera");
      setVideoPreviewMode("camera");
      const outResult = (out as { result?: Record<string, unknown> }).result;
      const solveStatus =
        typeof outResult?.status === "string" ? String(outResult.status) : "";
      if (autoHoldEnabled && solveStatus === "MATCH_FOUND") {
        setIsFrozen(true);
        setFrozenFrameId(
          (out as { frame_id?: number }).frame_id != null
            ? String((out as { frame_id?: number }).frame_id)
            : null,
        );
        setFrozenImageUrl(cameraPreviewUrl);
        stopCameraSolveLoop();
      }
      setLastRoundTripMs(performance.now() - t0);
    } catch (e) {
      setErr(String(e));
      setLastRoundTripMs(null);
    } finally {
      cameraSolveInFlightRef.current = false;
    }
  };

  const onVideoFileSolve = async () => {
    if (fileSolveInFlightRef.current) return;
    if (!selected) return;
    const vd = videoRef.current;
    if (!vd || vd.videoWidth < 2 || vd.videoHeight < 2 || videoPreviewError) return;
    setErr(null);
    fileSolveInFlightRef.current = true;
    const t0 = performance.now();
    try {
      const canvas = document.createElement("canvas");
      canvas.width = vd.videoWidth;
      canvas.height = vd.videoHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        throw new Error("无法创建画布上下文 / Cannot create canvas context");
      }
      ctx.drawImage(vd, 0, 0, canvas.width, canvas.height);
      const frameBlob = await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob(
          (b) => (b ? resolve(b) : reject(new Error("帧编码失败 / Frame encode failed"))),
          "image/jpeg",
          0.92,
        );
      });
      const out = await solveFrameFromBlob(frameBlob, {
        ...params,
        solve_interval_ms: starAnalysisIntervalMs,
        solve_timeout_ms: Math.min((labSettings?.solver_timeout_ms ?? 1500) * 0.6, 1200),
        overlay_topn_count: 3,
        enable_polar_guide: true,
      });
      const gateStatus = (out as { gate_status?: string | null }).gate_status;
      const gateReason = (out as { gate_reason?: string | null }).gate_reason;
      if (gateStatus && gateStatus !== "SOLVED") {
        setLastGateHint(`${gateStatus}${gateReason ? `: ${gateReason}` : ""}`);
      } else {
        setLastGateHint(null);
      }
      setLastResult(out as Record<string, unknown>);
      setBatchPack(null);
      setLastSolveSource("file");
      setLastRoundTripMs(performance.now() - t0);
    } catch (e) {
      setErr(String(e));
      setLastRoundTripMs(null);
    } finally {
      fileSolveInFlightRef.current = false;
    }
  };

  const startFileSolveLoop = () => {
    if (fileSolveRunning || !selected) return;
    setFileSolveRunning(true);
    void onVideoFileSolve();
    fileSolveTimerRef.current = window.setInterval(() => {
      void onVideoFileSolve();
    }, starAnalysisIntervalMs);
  };

  const canSolveVideoFile = useMemo(() => {
    if (view !== "lab_video" || videoPreviewMode !== "file") return false;
    if (!selected) return false;
    if (/\.avi$/i.test(selected)) return false;
    if (videoPreviewError) return false;
    return videoNatural.w > 1 && videoNatural.h > 1;
  }, [view, videoPreviewMode, selected, videoPreviewError, videoNatural.w, videoNatural.h]);

  const isSelectedAvi = useMemo(() => !!selected && /\.avi$/i.test(selected), [selected]);

  const onTranscodeAndUploadAvi = async () => {
    if (!selected || !isSelectedAvi || transcodeBusy) return;
    setErr(null);
    setTranscodeBusy(true);
    setTranscodeProgress(0);
    setTranscodeHint(t("lab.transcode.loading"));
    try {
      const srcUrl = uploadFileUrl(selected);
      const res = await fetch(srcUrl, { cache: "no-store" });
      if (!res.ok) throw new Error(t("lab.transcode.fetchFailed"));
      const blob = await res.blob();
      const aviFile = new File([blob], selected, { type: "video/x-msvideo" });
      const out = await transcodeAviToMp4(aviFile, (ratio, msg) => {
        setTranscodeProgress(Math.max(0, Math.min(1, ratio)));
        if (msg === "loading_ffmpeg") setTranscodeHint(t("lab.transcode.loading"));
        else if (msg === "transcoding") setTranscodeHint(t("lab.transcode.running"));
        else if (msg === "packing_output") setTranscodeHint(t("lab.transcode.packaging"));
      });
      setTranscodeHint(t("lab.transcode.uploading"));
      const upload = await uploadFile(out.file, "analysis_transcoded");
      await replaceTranscodedVideo({
        old_filename: selected,
        new_filename: upload.filename,
        duration_s: out.duration_s,
        nominal_fps: null,
        codec_fourcc: "libx264",
        container: "MP4",
      });
      await loadLists();
      setSelected(upload.filename);
      setTranscodeProgress(1);
      setTranscodeHint(t("lab.transcode.done"));
    } catch (e) {
      setErr(String(e));
      setTranscodeHint(t("lab.transcode.failed"));
    } finally {
      setTranscodeBusy(false);
    }
  };

  const transcodePoolAviAndReplace = async (aviFilename: string) => {
    const srcUrl = uploadFileUrl(aviFilename);
    const res = await fetch(srcUrl, { cache: "no-store" });
    if (!res.ok) throw new Error(t("lab.transcode.fetchFailed"));
    const blob = await res.blob();
    const aviFile = new File([blob], aviFilename, { type: "video/x-msvideo" });
    const out = await transcodeAviToMp4(aviFile, (ratio, msg) => {
      const base = 0.2;
      const span = 0.6;
      setDebugImportProgress(base + Math.max(0, Math.min(1, ratio)) * span);
      if (msg === "loading_ffmpeg") setDebugImportStep(t("sidebar.flowLoadingTranscoder"));
      else if (msg === "transcoding") setDebugImportStep(t("sidebar.flowTranscoding"));
      else if (msg === "packing_output") setDebugImportStep(t("sidebar.flowPackaging"));
    });
    setDebugImportStep(t("sidebar.flowUploadingMp4"));
    setDebugImportProgress(0.86);
    const upload = await uploadFile(out.file, "debug_console_transcoded");
    setDebugImportStep(t("sidebar.flowReplacing"));
    setDebugImportProgress(0.94);
    await replaceTranscodedVideo({
      old_filename: aviFilename,
      new_filename: upload.filename,
      duration_s: out.duration_s,
      nominal_fps: null,
      codec_fourcc: "libx264",
      container: "MP4",
    });
    return upload.filename;
  };

  const runDebugImportFlow = async () => {
    if (!debugPick || debugImportBusy) return;
    const isAvi = /\.avi$/i.test(debugPick);
    setErr(null);
    setDebugImportBusy(true);
    setDebugImportProgress(0.02);
    setDebugImportMessage(null);
    try {
      setDebugImportStep(t("sidebar.flowImportingDebug"));
      const imported = await importFromDebug(debugPick);
      setDebugImportProgress(isAvi ? 0.18 : 1);
      let target = imported.filename;
      if (isAvi) {
        target = await transcodePoolAviAndReplace(imported.filename);
      } else {
        setDebugImportStep(t("sidebar.flowNoTranscode"));
      }
      await loadLists();
      setSelected(target);
      setView(isVideoAsset(target) ? "lab_video" : "lab_image");
      setDebugImportProgress(1);
      setDebugImportStep(t("sidebar.flowDone"));
      setDebugImportMessage(t("sidebar.flowDoneMsg", { name: compactFilename(target) }));
    } catch (e) {
      setErr(String(e));
      setDebugImportStep(t("sidebar.flowFailed"));
      setDebugImportMessage(String(e));
    } finally {
      setDebugImportBusy(false);
    }
  };

  const stopFileSolveLoop = () => {
    setFileSolveRunning(false);
    if (fileSolveTimerRef.current != null) {
      window.clearInterval(fileSolveTimerRef.current);
      fileSolveTimerRef.current = null;
    }
  };

  const startCameraSolveLoop = () => {
    if (cameraSolveRunning) return;
    if (isFrozen) return;
    setCameraSolveRunning(true);
    void onCameraSolve();
    cameraSolveTimerRef.current = window.setInterval(() => {
      void onCameraSolve();
    }, starAnalysisIntervalMs);
  };

  const stopCameraSolveLoop = () => {
    setCameraSolveRunning(false);
    if (cameraSolveTimerRef.current != null) {
      window.clearInterval(cameraSolveTimerRef.current);
      cameraSolveTimerRef.current = null;
    }
  };

  const resumeLivePreview = () => {
    setIsFrozen(false);
    setFrozenFrameId(null);
    setFrozenImageUrl(null);
  };

  const togglePreset = (id: string) => {
    setSelectedPresetIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  const tryDeleteUpload = async (filename: string) => {
    if (!window.confirm(t("delete.uploadFirst", { name: filename }))) return;
    let nexp = 0;
    try {
      const c = await fetchUploadExperimentCount(filename);
      nexp = c.count;
    } catch {
      nexp = 0;
    }
    if (nexp > 0) {
      const ok = window.confirm(t("delete.uploadCascade", { n: nexp }));
      if (!ok) return;
    } else if (!window.confirm(t("delete.uploadSecond"))) {
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await deletePoolUpload(filename, { deleteExperiments: nexp > 0 });
      await loadLists();
      if (selected === filename) setSelected(null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const tryDeleteExperiment = async (id: string) => {
    if (!window.confirm(t("delete.experimentFirst"))) return;
    if (!window.confirm(t("delete.experimentSecond"))) return;
    setBusy(true);
    setErr(null);
    try {
      await deleteExperimentRecord(id);
      if (historyExpandId === id) setHistoryExpandId(null);
      const data = await fetchExperiments(historyQ, historyPage, HISTORY_PAGE_SIZE);
      setHistoryData(data);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const setZoomClamped = (z: number) => setZoom(Math.min(4, Math.max(0.5, z)));

  const historyTotalPages = Math.max(
    1,
    Math.ceil((historyData?.total ?? 0) / HISTORY_PAGE_SIZE),
  );

  /** 按当前页面只列出对应类型调试素材 / Filter debug captures by lab view */
  const debugFilesForView = useMemo(() => {
    if (view === "lab_image") {
      return debugFiles.filter((f) => f.type === "image" || isImageAsset(f.name));
    }
    if (view === "lab_video") {
      return debugFiles.filter((f) => f.type === "video" || isVideoAsset(f.name));
    }
    return debugFiles;
  }, [debugFiles, view]);

  const debugTotalPages = Math.max(
    1,
    Math.ceil(debugFilesForView.length / DEBUG_PAGE_SIZE),
  );
  const debugPagedFiles = useMemo(() => {
    const start = (debugPage - 1) * DEBUG_PAGE_SIZE;
    return debugFilesForView.slice(start, start + DEBUG_PAGE_SIZE);
  }, [debugFilesForView, debugPage]);

  useEffect(() => {
    setDebugPage(1);
  }, [view]);

  useEffect(() => {
    setDebugPage((p) => Math.min(p, debugTotalPages));
  }, [debugTotalPages]);

  useEffect(() => {
    if (debugPick && !debugFilesForView.some((f) => f.name === debugPick)) {
      setDebugPick(null);
    }
  }, [debugFilesForView, debugPick]);

  const metaCaptionRows = useMemo(
    () => buildMetaCaptionRows(meta, locale),
    [meta, locale],
  );

  const sidebarUploads = useMemo(() => {
    if (view === "lab_image") return uploads.filter((u) => isImageAsset(u.filename));
    if (view === "lab_video") return uploads.filter((u) => isVideoAsset(u.filename));
    return uploads;
  }, [uploads, view]);

  const solveHud = useMemo(() => parseSolveResult(resultRow), [resultRow]);

  useEffect(() => {
    setSingleFooterRawOpen(false);
  }, [lastResult]);
  useEffect(() => {
    if (view !== "lab_video") return;
    let id: ReturnType<typeof setInterval> | undefined;
    const tick = () => {
      fetchSystemInfo().then(setSysOverview).catch(() => {});
    };
    tick();
    id = setInterval(tick, 1500);
    return () => {
      if (id) clearInterval(id);
    };
  }, [view]);

  useEffect(() => {
    if (view !== "lab_video" || videoPreviewMode !== "camera") {
      stopCameraSolveLoop();
      setIsFrozen(false);
      setFrozenFrameId(null);
      setFrozenImageUrl(null);
    }
    if (view !== "lab_video" || videoPreviewMode !== "file") {
      stopFileSolveLoop();
    }
  }, [view, videoPreviewMode]);

  useEffect(() => {
    if (!selected) {
      stopFileSolveLoop();
    }
  }, [selected]);

  useEffect(() => {
    return () => {
      stopCameraSolveLoop();
      stopFileSolveLoop();
    };
  }, []);


  return (
    <div className="flex min-h-full flex-col bg-surface text-on-surface">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-outline-variant/20 px-4">
        <div className="flex items-center gap-6">
          <span className="font-headline text-sm font-bold tracking-wide text-on-surface">
            {t("app.title")}
          </span>
          <nav className="flex flex-wrap gap-3 text-xs">
            <button
              type="button"
              className={view === "lab_image" ? "text-primary" : "text-on-surface-variant"}
              onClick={() => setView("lab_image")}
            >
              {t("nav.labImage")}
            </button>
            <button
              type="button"
              className={view === "lab_video" ? "text-primary" : "text-on-surface-variant"}
              onClick={() => setView("lab_video")}
            >
              {t("nav.labVideo")}
            </button>
            <button
              type="button"
              className={view === "pool" ? "text-primary" : "text-on-surface-variant"}
              onClick={() => setView("pool")}
            >
              {t("nav.pool")}
            </button>
            <button
              type="button"
              className={view === "history" ? "text-primary" : "text-on-surface-variant"}
              onClick={() => setView("history")}
            >
              {t("nav.history")}
            </button>
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <div className="mr-2 flex gap-1 text-[10px]">
            <button
              type="button"
              className={`rounded px-2 py-0.5 ${locale === "zh" ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant"}`}
              onClick={() => setLocale("zh")}
            >
              {t("lang.zh")}
            </button>
            <button
              type="button"
              className={`rounded px-2 py-0.5 ${locale === "en" ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant"}`}
              onClick={() => setLocale("en")}
            >
              {t("lang.en")}
            </button>
          </div>
          <a
            className="flex items-center gap-1 rounded border border-outline-variant/30 px-2 py-1 text-xs text-on-surface-variant hover:bg-surface-container"
            href="/debug"
          >
            <FlaskConical className="h-3.5 w-3.5" /> {t("nav.cameraDebug")}
          </a>
          <a
            className="flex items-center gap-1 rounded border border-outline-variant/30 px-2 py-1 text-xs text-on-surface-variant hover:bg-surface-container"
            href="/"
          >
            <Home className="h-3.5 w-3.5" /> {t("nav.home")}
          </a>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-64 shrink-0 border-r border-outline-variant/15 bg-surface-container-lowest p-3 text-xs">
          <div className="mb-3 font-semibold text-on-surface-variant">{t("sidebar.assets")}</div>
          <label className="mb-3 flex cursor-pointer items-center gap-2 rounded bg-primary-container/30 px-2 py-2 text-on-primary-container">
            <Upload className="h-4 w-4" />
            <span>{t("sidebar.upload")}</span>
            <input
              type="file"
              accept="image/*,video/*"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                setBusy(true);
                setErr(null);
                try {
                  const r = await uploadFile(f);
                  await loadLists();
                  setSelected(r.filename);
                } catch (ex) {
                  setErr(String(ex));
                } finally {
                  setBusy(false);
                  e.target.value = "";
                }
              }}
            />
          </label>
          <button
            type="button"
            className="mb-2 flex w-full items-center gap-1 text-left text-on-surface-variant hover:text-on-surface"
            onClick={() => {
              loadLists().catch((e) => setErr(String(e)));
              setDebugPage(1);
              loadDebugFiles();
            }}
          >
            <RefreshCw className="h-3 w-3" /> {t("sidebar.refresh")}
          </button>
          <div className="max-h-36 overflow-y-auto border-t border-outline-variant/10 pt-2">
            {sidebarUploads.map((u) => (
              <div
                key={u.filename}
                className={`mb-1 flex items-center gap-0.5 rounded px-1 ${
                  selected === u.filename ? "bg-surface-container" : ""
                }`}
              >
                <button
                  type="button"
                  className={`min-w-0 flex-1 truncate rounded px-1 py-1 text-left ${
                    selected === u.filename ? "text-primary" : ""
                  }`}
                  title={u.filename}
                  onClick={() => {
                    setSelected(u.filename);
                    setView(isVideoAsset(u.filename) ? "lab_video" : "lab_image");
                  }}
                >
                          <span className="block truncate">{compactFilename(u.filename)}</span>
                  <span className="block text-[9px] text-on-surface-variant/90">
                    {isVideoAsset(u.filename) ? t("sidebar.assetTypeVideo") : t("sidebar.assetTypeImage")}
                  </span>
                </button>
                <button
                  type="button"
                  className="shrink-0 rounded p-1 text-on-surface-variant hover:bg-surface-container-high hover:text-error"
                  title={t("pool.delete")}
                  aria-label={t("pool.delete")}
                  onClick={(e) => {
                    e.stopPropagation();
                    void tryDeleteUpload(u.filename);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
          <div className="mt-3 border-t border-outline-variant/10 pt-3">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div className="min-w-0 font-semibold leading-tight text-on-surface-variant">
                {t("sidebar.debugCaptures")}
              </div>
              <button
                type="button"
                className="shrink-0 rounded bg-primary px-2 py-1 text-[10px] font-medium text-on-primary disabled:opacity-40"
                disabled={!debugPick || debugImportBusy}
                title={debugPick ?? undefined}
                onClick={() => void runDebugImportFlow()}
              >
                {debugPick && /\.avi$/i.test(debugPick)
                  ? t("sidebar.importToPoolWithTranscode")
                  : t("sidebar.importToPoolDirect")}
              </button>
            </div>
            {debugImportProgress != null && (
              <div className="mb-2 rounded border border-outline-variant/25 bg-surface-container-low px-2 py-2">
                <div className="flex items-center justify-between gap-2 text-[10px]">
                  <span className="text-on-surface-variant">
                    {debugImportStep || t("sidebar.flowPreparing")}
                  </span>
                  <span className="font-mono text-on-surface">
                    {Math.round((debugImportProgress || 0) * 100)}%
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded bg-surface-container-highest">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${Math.round((debugImportProgress || 0) * 100)}%` }}
                  />
                </div>
                {debugImportMessage && (
                  <div className="mt-1 text-[10px] text-on-surface-variant" title={debugImportMessage}>
                    {debugImportMessage}
                  </div>
                )}
              </div>
            )}
            {debugFilesForView.length === 0 ? (
              <p className="text-[10px] text-on-surface-variant">{t("sidebar.debugEmpty")}</p>
            ) : (
              <>
                <div className="max-h-[min(22rem,55vh)] space-y-1.5 overflow-y-auto pr-0.5">
                  {debugPagedFiles.map((f) => (
                    <button
                      key={f.name}
                      type="button"
                      className={`flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left transition-colors ${
                        debugPick === f.name
                          ? "border-primary bg-primary-container/20"
                          : "border-outline-variant/25 hover:bg-surface-container"
                      }`}
                      onClick={() => setDebugPick(f.name)}
                    >
                      {f.type === "image" ? (
                        <img
                          src={debugCaptureFileUrl(f.name)}
                          alt=""
                          className="h-11 w-11 shrink-0 rounded object-cover"
                        />
                      ) : (
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded bg-surface-container-high text-[9px] text-on-surface-variant">
                          video
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-mono text-[10px] text-on-surface" title={f.name}>
                          {compactFilename(f.name)}
                        </div>
                        <div className="text-[9px] text-on-surface-variant">
                          {f.type === "video" || isVideoAsset(f.name)
                            ? t("sidebar.assetTypeVideo")
                            : t("sidebar.assetTypeImage")}{" "}
                          · {formatDateTime(f.modified, locale)} · {formatFileSize(f.size)}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
                <div className="mt-2 flex items-center justify-between gap-1 text-[10px] text-on-surface-variant">
                  <button
                    type="button"
                    className="rounded border border-outline-variant/30 px-2 py-0.5 disabled:opacity-40"
                    disabled={debugPage <= 1}
                    onClick={() => setDebugPage((p) => Math.max(1, p - 1))}
                  >
                    {t("history.prev")}
                  </button>
                  <span className="tabular-nums">
                    {t("sidebar.debugPage", { cur: debugPage, total: debugTotalPages })}
                  </span>
                  <button
                    type="button"
                    className="rounded border border-outline-variant/30 px-2 py-0.5 disabled:opacity-40"
                    disabled={debugPage >= debugTotalPages}
                    onClick={() => setDebugPage((p) => Math.min(debugTotalPages, p + 1))}
                  >
                    {t("history.next")}
                  </button>
                </div>
              </>
            )}
          </div>
        </aside>

        {(view === "lab_image" || view === "lab_video") && (
          <div className="flex min-h-0 min-w-0 flex-1">
            <main className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4">
              {err && (
                <div className="mb-2 rounded border border-error/40 bg-error-container/20 px-3 py-2 text-xs text-error">
                  {err}
                </div>
              )}
              {lastGateHint && (
                <div className="mb-2 rounded border border-outline-variant/35 bg-surface-container px-3 py-2 text-xs text-on-surface-variant">
                  {lastGateHint}
                </div>
              )}
              {view === "lab_video" && (
                <div className="mb-3 max-w-5xl rounded-lg border border-outline-variant/25 bg-surface-container-low/80 p-3 text-[11px] leading-relaxed text-on-surface">
                  <p className="text-[10px] text-on-surface-variant">{t("lab.videoLiveIntro")}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      className={`rounded px-3 py-1.5 text-[11px] font-medium ${
                        videoPreviewMode === "file"
                          ? "bg-primary text-on-primary-container"
                          : "border border-outline-variant/40 bg-surface-container text-on-surface"
                      }`}
                      onClick={() => setVideoPreviewMode("file")}
                    >
                      {t("lab.previewModeFile")}
                    </button>
                    <button
                      type="button"
                      className={`rounded px-3 py-1.5 text-[11px] font-medium ${
                        videoPreviewMode === "camera"
                          ? "bg-primary text-on-primary-container"
                          : "border border-outline-variant/40 bg-surface-container text-on-surface"
                      }`}
                      onClick={() => setVideoPreviewMode("camera")}
                    >
                      {t("lab.previewModeCamera")}
                    </button>
                  </div>
                </div>
              )}
              <div className="relative aspect-video w-full max-w-5xl overflow-hidden rounded-lg border border-outline-variant/20 bg-surface-container-lowest">
                {view === "lab_video" && videoPreviewMode === "camera" ? (
                  <div className="relative flex h-full min-h-[220px] flex-col items-center justify-center gap-3 bg-black p-2">
                    <div className="relative inline-block max-h-[70vh] max-w-full">
                      {((isFrozen && frozenImageUrl) || cameraPreviewUrl) ? (
                        <img
                          ref={cameraPreviewImgRef}
                          src={(isFrozen && frozenImageUrl) || cameraPreviewUrl || ""}
                          alt=""
                          className="max-h-[70vh] w-full min-h-[120px] object-contain"
                          onLoad={(e) =>
                            setCameraPreviewNatural({
                              w: e.currentTarget.naturalWidth,
                              h: e.currentTarget.naturalHeight,
                            })
                          }
                        />
                      ) : (
                        <div className="flex min-h-[200px] w-full min-w-[280px] flex-col items-center justify-center gap-2 text-[11px] text-on-surface-variant">
                          <Loader2 className="h-8 w-8 animate-spin text-primary" />
                          <span>{t("lab.cameraPreviewLoading")}</span>
                        </div>
                      )}
                      <canvas
                        ref={cvRef}
                        className="pointer-events-none absolute left-0 top-0"
                      />
                    </div>
                  </div>
                ) : selected ? (
                  <div className="relative h-full min-h-[200px] overflow-auto">
                    {view === "lab_video" ? (
                      <>
                        <div className="absolute left-2 top-2 z-20 flex flex-wrap gap-1">
                          <button
                            type="button"
                            title={t("lab.grid")}
                            className={`rounded border px-2 py-1 text-[10px] ${
                              gridOn
                                ? "border-primary bg-primary/20"
                                : "border-white/30 bg-black/40"
                            } text-white`}
                            onClick={() => setGridOn((g) => !g)}
                          >
                            <Grid3x3 className="mr-1 inline h-3 w-3" />
                            {t("lab.grid")}
                          </button>
                          <button
                            type="button"
                            title={t("lab.zoomOut")}
                            className="rounded border border-white/30 bg-black/40 px-2 py-1 text-[10px] text-white"
                            onClick={() => setZoomClamped(zoom - 0.25)}
                          >
                            <ZoomOut className="inline h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            title={t("lab.zoomIn")}
                            className="rounded border border-white/30 bg-black/40 px-2 py-1 text-[10px] text-white"
                            onClick={() => setZoomClamped(zoom + 0.25)}
                          >
                            <ZoomIn className="inline h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            title={t("lab.zoomReset")}
                            className="rounded border border-white/30 bg-black/40 px-2 py-1 text-[10px] text-white"
                            onClick={() => setZoom(1)}
                          >
                            <RotateCcw className="inline h-3 w-3" />
                          </button>
                        </div>
                        <div
                          className="flex min-h-[200px] flex-col items-center justify-center gap-2 bg-black py-2"
                        >
                          <div
                            className="inline-block origin-top-left transition-transform"
                            style={{ transform: `scale(${zoom})` }}
                          >
                            <div className="relative inline-block">
                              {gridOn && (
                                <div
                                  className="pointer-events-none absolute inset-0 z-[1]"
                                  style={{
                                    backgroundImage: [
                                      "linear-gradient(to right, rgba(255,255,255,0.12) 1px, transparent 1px)",
                                      "linear-gradient(to bottom, rgba(255,255,255,0.12) 1px, transparent 1px)",
                                    ].join(","),
                                    backgroundSize: "48px 48px",
                                  }}
                                />
                              )}
                              <video
                                ref={videoRef}
                                src={previewUrl}
                                loop
                                playsInline
                                autoPlay
                                muted
                                preload="metadata"
                                className="max-h-[70vh] w-full max-w-full object-contain"
                                onError={() => setVideoPreviewError(t("lab.videoPreviewFailed"))}
                                onLoadedData={() => {
                                  setVideoPreviewError(null);
                                  const v = videoRef.current;
                                  if (v) {
                                    void v.play().catch(() => {});
                                  }
                                }}
                              />
                              <canvas
                                ref={cvRef}
                                className="pointer-events-none absolute left-0 top-0"
                              />
                            </div>
                          </div>
                          {videoPreviewError && (
                            <div className="rounded border border-error/40 bg-error-container/20 px-3 py-1.5 text-[11px] text-error">
                              {videoPreviewError}
                            </div>
                          )}
                          {isSelectedAvi && (
                            <div className="max-w-3xl rounded border border-primary/40 bg-primary/10 px-3 py-2 text-[11px] text-on-surface">
                              <div className="font-semibold text-primary">{t("lab.transcode.title")}</div>
                              <div className="mt-1 text-on-surface-variant">{t("lab.transcode.desc")}</div>
                              {transcodeProgress != null && (
                                <div className="mt-2">
                                  <div className="mb-1 text-[10px] text-on-surface-variant">
                                    {transcodeHint || t("lab.transcode.running")}
                                  </div>
                                  <div className="h-1.5 w-full overflow-hidden rounded bg-surface-container-highest">
                                    <div
                                      className="h-full bg-primary transition-all"
                                      style={{ width: `${Math.round(transcodeProgress * 100)}%` }}
                                    />
                                  </div>
                                </div>
                              )}
                              <div className="mt-2">
                                <button
                                  type="button"
                                  className="rounded bg-primary px-3 py-1.5 text-[11px] font-medium text-on-primary disabled:opacity-50"
                                  disabled={transcodeBusy}
                                  onClick={() => void onTranscodeAndUploadAvi()}
                                >
                                  {t("lab.transcode.button")}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="absolute left-2 top-2 z-20 flex flex-wrap gap-1">
                          <button
                            type="button"
                            title={t("lab.grid")}
                            className={`rounded border px-2 py-1 text-[10px] ${
                              gridOn
                                ? "border-primary bg-primary/20"
                                : "border-white/30 bg-black/40"
                            } text-white`}
                            onClick={() => setGridOn((g) => !g)}
                          >
                            <Grid3x3 className="mr-1 inline h-3 w-3" />
                            {t("lab.grid")}
                          </button>
                          <button
                            type="button"
                            title={t("lab.zoomOut")}
                            className="rounded border border-white/30 bg-black/40 px-2 py-1 text-[10px] text-white"
                            onClick={() => setZoomClamped(zoom - 0.25)}
                          >
                            <ZoomOut className="inline h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            title={t("lab.zoomIn")}
                            className="rounded border border-white/30 bg-black/40 px-2 py-1 text-[10px] text-white"
                            onClick={() => setZoomClamped(zoom + 0.25)}
                          >
                            <ZoomIn className="inline h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            title={t("lab.zoomReset")}
                            className="rounded border border-white/30 bg-black/40 px-2 py-1 text-[10px] text-white"
                            onClick={() => setZoom(1)}
                          >
                            <RotateCcw className="inline h-3 w-3" />
                          </button>
                        </div>
                        <div
                          className="inline-block origin-top-left transition-transform"
                          style={{ transform: `scale(${zoom})` }}
                        >
                          <div className="relative inline-block">
                            {gridOn && (
                              <div
                                className="pointer-events-none absolute inset-0 z-[1]"
                                style={{
                                  backgroundImage: [
                                    "linear-gradient(to right, rgba(255,255,255,0.12) 1px, transparent 1px)",
                                    "linear-gradient(to bottom, rgba(255,255,255,0.12) 1px, transparent 1px)",
                                  ].join(","),
                                  backgroundSize: "48px 48px",
                                }}
                              />
                            )}
                            <img
                              ref={imgRef}
                              src={previewUrl}
                              alt="preview"
                              className="max-h-[70vh] w-full object-contain"
                            />
                            <canvas
                              ref={cvRef}
                              className="pointer-events-none absolute left-0 top-0"
                            />
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center px-4 text-center text-on-surface-variant">
                    {view === "lab_video" ? t("lab.selectOrUploadVideo") : t("lab.selectOrUpload")}
                  </div>
                )}
                {busy && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  </div>
                )}
              </div>
              {((selected && view === "lab_image") ||
                (view === "lab_video" &&
                  ((videoPreviewMode === "file" && selected) || videoPreviewMode === "camera"))) && (
                <div className="mt-2 flex flex-wrap items-center gap-3 rounded-lg border border-outline-variant/25 bg-surface-container-lowest/90 px-3 py-2 text-xs text-on-surface">
                  <span className="shrink-0 font-medium text-on-surface-variant">
                    {t("lab.layers")}
                  </span>
                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                    {(["matched", "pattern", "all"] as const).map((k) => (
                      <label key={k} className="flex cursor-pointer items-center gap-1">
                        <input
                          type="checkbox"
                          className="accent-primary"
                          checked={layers[k]}
                          onChange={(e) =>
                            setLayers((L) => ({ ...L, [k]: e.target.checked }))
                          }
                        />
                        <span>
                          {k === "matched"
                            ? t("lab.layer.matched")
                            : k === "pattern"
                              ? t("lab.layer.pattern")
                              : t("lab.layer.all")}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
              {(selected || (view === "lab_video" && videoPreviewMode === "camera")) && (
                <>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    <details
                      open
                      className="rounded-lg border border-outline-variant/25 bg-surface-container-lowest/90"
                    >
                      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-xs font-semibold text-on-surface [&::-webkit-details-marker]:hidden">
                        {t("lab.solveSection")}
                        <ChevronDown className="h-4 w-4 shrink-0 text-on-surface-variant" />
                      </summary>
                      <div className="border-t border-outline-variant/15 px-3 py-2 text-[10px]">
                        {resultRow ? (
                          <div className="space-y-1 text-on-surface">
                            {solveHud.tSolveMs != null && (
                              <div className="space-y-0.5">
                                <div className="flex justify-between gap-2">
                                  <span className="text-on-surface-variant">
                                    {t("lab.metric.solveComputeMs")}
                                  </span>
                                  <span className="font-mono tabular-nums">
                                    {solveHud.tSolveMs.toFixed(0)} ms
                                  </span>
                                </div>
                                <p className="text-[8px] leading-snug text-on-surface-variant/90">
                                  {t("lab.metric.solveComputeHelp")}
                                </p>
                              </div>
                            )}
                            {lastRoundTripMs != null && (
                              <div className="space-y-0.5 border-t border-outline-variant/10 pt-1">
                                <div className="flex justify-between gap-2">
                                  <span className="text-on-surface-variant">
                                    {t("lab.metric.solveRoundTripMs")}
                                  </span>
                                  <span className="font-mono tabular-nums">
                                    {lastRoundTripMs.toFixed(0)} ms
                                  </span>
                                </div>
                                <p className="text-[8px] leading-snug text-on-surface-variant/90">
                                  {t("lab.metric.solveRoundTripHelp")}
                                </p>
                              </div>
                            )}
                            {(solveHud.tBackendTotalMs != null ||
                              solveHud.tOpenDecodeMs != null ||
                              solveHud.tPreprocessMs != null ||
                              solveHud.tExtractMs != null ||
                              solveHud.tSolveMs != null) && (
                              <div className="space-y-0.5 border-t border-outline-variant/10 pt-1">
                                <div className="flex justify-between gap-2">
                                  <span className="text-on-surface-variant">
                                    {t("lab.metric.backendTotalMs")}
                                  </span>
                                  <span className="font-mono tabular-nums">
                                    {solveHud.tBackendTotalMs != null
                                      ? `${solveHud.tBackendTotalMs.toFixed(0)} ms`
                                      : t("common.placeholder")}
                                  </span>
                                </div>
                                <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-[8px] text-on-surface-variant/90">
                                  <span>
                                    {t("lab.metric.openDecodeMs")}:{" "}
                                    {solveHud.tOpenDecodeMs != null
                                      ? `${solveHud.tOpenDecodeMs.toFixed(0)} ms`
                                      : t("common.placeholder")}
                                  </span>
                                  <span>
                                    {t("lab.metric.preprocessMs")}:{" "}
                                    {solveHud.tPreprocessMs != null
                                      ? `${solveHud.tPreprocessMs.toFixed(0)} ms`
                                      : t("common.placeholder")}
                                  </span>
                                  <span>
                                    {t("lab.metric.extractMs")}:{" "}
                                    {solveHud.tExtractMs != null
                                      ? `${solveHud.tExtractMs.toFixed(0)} ms`
                                      : t("common.placeholder")}
                                  </span>
                                  <span>
                                    {t("lab.metric.solveOnlyMs")}:{" "}
                                    {solveHud.tSolveMs != null
                                      ? `${solveHud.tSolveMs.toFixed(0)} ms`
                                      : t("common.placeholder")}
                                  </span>
                                </div>
                              </div>
                            )}
                            {(solveHud.raDeg != null || solveHud.decDeg != null) && (
                              <div className="leading-tight">
                                <span className="text-on-surface-variant">
                                  {t("lab.metric.radec")}
                                </span>
                                <div className="mt-0.5 font-mono text-[9px]">
                                  α {formatAngleDeg(solveHud.raDeg)} · δ{" "}
                                  {formatAngleDeg(solveHud.decDeg)}
                                </div>
                              </div>
                            )}
                            <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-[9px]">
                              {solveHud.matches != null && (
                                <span>
                                  <span className="text-on-surface-variant">
                                    {t("lab.metric.matches")}
                                  </span>{" "}
                                  <span className="font-mono">{solveHud.matches}</span>
                                </span>
                              )}
                              {solveHud.rmseArcsec != null && (
                                <span>
                                  <span className="text-on-surface-variant">
                                    {t("lab.metric.rmse")}
                                  </span>{" "}
                                  <span className="font-mono">
                                    {solveHud.rmseArcsec.toFixed(2)}″
                                  </span>
                                </span>
                              )}
                              {solveHud.prob != null && (
                                <span className="inline-flex max-w-full flex-col gap-0.5">
                                  <span>
                                    <span className="text-on-surface-variant">
                                      {t("lab.metric.prob")}
                                    </span>{" "}
                                    <span className="font-mono">
                                      {formatProbLine(solveHud.prob, resultRow ?? undefined).line}
                                    </span>
                                  </span>
                                  <span className="text-[8px] leading-snug text-on-surface-variant/90">
                                    {t("lab.metric.probHelp")}
                                  </span>
                                  {formatProbLine(solveHud.prob, resultRow ?? undefined).rawLine && (
                                    <>
                                      <span className="text-[8px] text-on-surface-variant">
                                        {t("lab.metric.probRaw")}:{" "}
                                        {
                                          formatProbLine(solveHud.prob, resultRow ?? undefined)
                                            .rawLine
                                        }
                                      </span>
                                      <span className="text-[8px] leading-snug text-on-surface-variant/90">
                                        {t("lab.metric.probRawHelp")}
                                      </span>
                                    </>
                                  )}
                                </span>
                              )}
                            </div>
                            {solveHud.status && (
                              <div className="border-t border-outline-variant/15 pt-1 text-[9px]">
                                <span className="text-on-surface-variant">
                                  {t("lab.metric.status")}{" "}
                                </span>
                                <span className="font-mono text-secondary">{solveHud.status}</span>
                              </div>
                            )}
                          </div>
                        ) : (
                          <p className="text-on-surface-variant">{t("common.placeholder")}</p>
                        )}
                      </div>
                    </details>
                    <details
                      open
                      className="rounded-lg border border-outline-variant/25 bg-surface-container-lowest/90"
                    >
                      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-xs font-semibold text-on-surface [&::-webkit-details-marker]:hidden">
                        {t("lab.imageSection")}
                        <ChevronDown className="h-4 w-4 shrink-0 text-on-surface-variant" />
                      </summary>
                      <div className="space-y-0.5 border-t border-outline-variant/15 px-3 py-2 text-[10px]">
                        <div className="flex justify-between gap-2">
                          <span className="text-on-surface-variant">{t("lab.resolution")}</span>
                          <span className="font-mono tabular-nums">
                            {previewPixelDims.w > 0
                              ? `${previewPixelDims.w}×${previewPixelDims.h}`
                              : t("common.placeholder")}
                          </span>
                        </div>
                        <div className="flex justify-between gap-2">
                          <span className="text-on-surface-variant">{t("lab.starsDetected")}</span>
                          <span className="font-mono tabular-nums">
                            {starCount != null ? starCount : t("common.placeholder")}
                          </span>
                        </div>
                        <div className="flex justify-between gap-2">
                          <span className="text-on-surface-variant">{t("lab.fwhm")}</span>
                          <span>{t("common.placeholder")}</span>
                        </div>
                      </div>
                    </details>
                  </div>
                  {selected && (
                    <>
                      <div className="mt-2 flex flex-wrap gap-4 text-xs text-on-surface-variant">
                        <span>
                          {t("lab.file")}:{" "}
                          <span className="font-mono text-on-surface" title={selected}>
                            {compactFilename(selected, 22, 18)}
                          </span>
                        </span>
                        {uploads.find((u) => u.filename === selected)?.source && (
                          <span className="rounded bg-surface-container-high px-2 py-0.5">
                            {t("lab.source")}:{" "}
                            {uploads.find((u) => u.filename === selected)?.source}
                          </span>
                        )}
                      </div>
                      <details
                        open
                        className="mt-2 rounded-lg border border-outline-variant/25 bg-surface-container-lowest/90 text-xs shadow-sm"
                      >
                        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 font-semibold text-on-surface [&::-webkit-details-marker]:hidden">
                          {t("lab.meta.title")}
                          {metaLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                          <ChevronDown className="ml-auto h-4 w-4 shrink-0 text-on-surface-variant" />
                        </summary>
                        <div className="border-t border-outline-variant/15 p-3 pt-2">
                          {metaCaptionRows.length > 0 ? (
                            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                              {metaCaptionRows.map((row) => (
                                <div key={`${row.key}-${row.value}`}>
                                  <dt className="text-[10px] text-on-surface-variant">{t(row.key)}</dt>
                                  <dd className="text-[11px] font-medium text-on-surface">
                                    {row.value}
                                  </dd>
                                </div>
                              ))}
                            </dl>
                          ) : meta && !metaLoading ? (
                            <p className="text-[10px] leading-relaxed text-on-surface-variant">
                              {t("lab.meta.partial")}
                            </p>
                          ) : !metaLoading ? (
                            <p className="text-[10px] text-on-surface-variant">
                              {t("lab.meta.noSidecar")}
                            </p>
                          ) : null}
                        </div>
                      </details>
                    </>
                  )}
                </>
              )}
              {(selected || (view === "lab_video" && videoPreviewMode === "camera")) &&
                (lastResult || batchPack) && (
                <section className="mt-3 max-h-[min(50vh,28rem)] rounded-lg border border-outline-variant/25 bg-surface-container-lowest/95">
                  <div className="flex h-9 shrink-0 items-center justify-between border-b border-outline-variant/15 px-3 text-[10px] uppercase text-on-surface-variant">
                    <span>{t("results.title")}</span>
                    <div className="flex gap-3">
                      {batchPack?.results?.length ? (
                        <button
                          type="button"
                          className="rounded bg-surface-container px-2 py-0.5 normal-case"
                          onClick={async () => {
                            if (!selected || !batchPack) return;
                            for (const r of batchPack.results) {
                              if (!r.success) continue;
                              const row = r.result as Record<string, unknown> | undefined;
                              await saveExperiment({
                                input_name: selected,
                                preset_label: String(r.label),
                                result_json: r,
                                metrics: metricsFromResult(row ?? null),
                                replay: { layers, params },
                              });
                            }
                            setErr(null);
                          }}
                        >
                          {t("results.saveBatchAll")}
                        </button>
                      ) : null}
                      {lastResult && (
                        <button
                          type="button"
                          className="rounded bg-surface-container px-2 py-0.5 normal-case"
                          onClick={async () => {
                            if (!selected && lastSolveSource !== "camera") return;
                            const res = lastResult.result as Record<string, unknown> | undefined;
                            await saveExperiment({
                              input_name: selected ?? t("lab.cameraSnapshotName"),
                              preset_label: "manual",
                              result_json: lastResult,
                              metrics: metricsFromResult(res ?? null),
                              replay: { layers, params },
                            });
                            setErr(null);
                          }}
                        >
                          {t("results.saveCurrent")}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="min-h-0 overflow-y-auto p-3">
                    <div className="flex gap-3 overflow-x-auto text-xs">
                      {batchPack?.results.map((r, i) => {
                        const row = r.result as Record<string, unknown> | undefined;
                        const rawOpen = batchRawOpen[i] ?? false;
                        return (
                          <div
                            key={i}
                            className="min-w-[15rem] max-w-sm shrink-0 rounded-lg border border-outline-variant/25 bg-surface-container p-3 shadow-sm"
                          >
                            <div className="border-b border-outline-variant/15 pb-2 font-semibold text-secondary">
                              {String(r.label)}
                            </div>
                            {r.success ? (
                              <>
                                <SolveFooterSummary result={row} t={t} roundTripMs={null} />
                                <button
                                  type="button"
                                  className="mt-2 text-[10px] text-primary hover:underline"
                                  onClick={() =>
                                    setBatchRawOpen((prev) => ({
                                      ...prev,
                                      [i]: !rawOpen,
                                    }))
                                  }
                                >
                                  {rawOpen ? t("results.hideRaw") : t("results.viewRaw")}
                                </button>
                                {rawOpen && (
                                  <pre className="mt-1 max-h-40 overflow-auto rounded bg-surface-container-highest p-2 text-[9px] text-on-surface-variant">
                                    {JSON.stringify(r, null, 2)}
                                  </pre>
                                )}
                              </>
                            ) : (
                              <div className="mt-2 text-[10px] text-error">{String(r.error)}</div>
                            )}
                            {r.success && selected && (
                              <button
                                type="button"
                                className="mt-3 w-full rounded bg-surface-container-high py-1.5 text-[10px] font-medium"
                                onClick={() =>
                                  saveExperiment({
                                    input_name: selected,
                                    preset_label: String(r.label),
                                    result_json: r,
                                    metrics: metricsFromResult(row ?? null),
                                    replay: { layers, params },
                                  }).catch((e) => setErr(String(e)))
                                }
                              >
                                {t("results.saveRow")}
                              </button>
                            )}
                          </div>
                        );
                      })}
                      {lastResult && !batchPack && (
                        <div className="min-w-[16rem] max-w-md shrink-0 rounded-lg border border-outline-variant/25 bg-surface-container p-3 shadow-sm">
                          <div className="border-b border-outline-variant/15 pb-2 text-[10px] font-semibold uppercase text-on-surface-variant">
                            {t("results.title")}
                          </div>
                          <SolveFooterSummary
                            result={lastResult.result as Record<string, unknown> | undefined}
                            t={t}
                            roundTripMs={lastRoundTripMs}
                          />
                          <button
                            type="button"
                            className="mt-2 text-[10px] text-primary hover:underline"
                            onClick={() => setSingleFooterRawOpen((o) => !o)}
                          >
                            {singleFooterRawOpen ? t("results.hideRaw") : t("results.viewRaw")}
                          </button>
                          {singleFooterRawOpen && (
                            <pre className="mt-1 max-h-48 overflow-auto rounded bg-surface-container-highest p-2 text-[9px] text-on-surface-variant">
                              {JSON.stringify(lastResult, null, 2)}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </section>
              )}
            </main>

            <aside className="flex w-80 shrink-0 flex-col border-l border-outline-variant/15 bg-surface-container-low text-xs min-h-0">
              {view !== "lab_video" && (
                <div className="shrink-0 space-y-2 border-b border-outline-variant/20 p-4 pb-3">
                  <button
                    type="button"
                    className="w-full rounded bg-primary py-2.5 font-semibold text-on-primary-container"
                    onClick={onSingleSolve}
                    disabled={busy}
                  >
                    {t("btn.solveOne")}
                  </button>
                  <button
                    type="button"
                    className="w-full rounded bg-secondary/80 py-2.5 font-semibold text-on-secondary"
                    onClick={onBatch}
                    disabled={busy}
                  >
                    {t("btn.solveBatch")}
                  </button>
                </div>
              )}
              {view === "lab_video" && (
                <div className="shrink-0 space-y-2 border-b border-outline-variant/20 p-4 pb-3">
                  {videoPreviewMode === "file" ? (
                    <>
                      <button
                        type="button"
                        className="w-full rounded bg-primary py-2.5 font-semibold text-on-primary-container disabled:opacity-40"
                        onClick={() => startFileSolveLoop()}
                        disabled={busy || !canSolveVideoFile || fileSolveRunning}
                      >
                        {t("lab.solveFileStart")}
                      </button>
                      <button
                        type="button"
                        className="w-full rounded bg-error/80 py-2.5 font-semibold text-on-error disabled:opacity-40"
                        onClick={() => stopFileSolveLoop()}
                        disabled={!fileSolveRunning}
                      >
                        {t("lab.solveFileStop")}
                      </button>
                      <button
                        type="button"
                        className="w-full rounded bg-secondary/80 py-2.5 font-semibold text-on-secondary disabled:opacity-40"
                        onClick={() => void onVideoFileSolve()}
                        disabled={busy || !canSolveVideoFile || fileSolveRunning}
                      >
                        {t("lab.solveCurrentFrame")}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="w-full rounded bg-primary py-2.5 font-semibold text-on-primary-container disabled:opacity-40"
                        onClick={() => startCameraSolveLoop()}
                        disabled={busy || cameraSolveRunning || isFrozen}
                      >
                        {t("lab.solveCameraStart")}
                      </button>
                      <button
                        type="button"
                        className="w-full rounded bg-error/80 py-2.5 font-semibold text-on-error disabled:opacity-40"
                        onClick={() => stopCameraSolveLoop()}
                        disabled={!cameraSolveRunning}
                      >
                        {t("lab.solveCameraStop")}
                      </button>
                      <button
                        type="button"
                        className="w-full rounded bg-secondary/80 py-2.5 font-semibold text-on-secondary disabled:opacity-40"
                        onClick={() => void onCameraSolve()}
                        disabled={busy || isFrozen}
                      >
                        {t("lab.solveCameraFrame")}
                      </button>
                      <label className="flex items-center gap-2 rounded border border-outline-variant/25 px-2 py-1.5 text-[11px]">
                        <input
                          type="checkbox"
                          checked={autoHoldEnabled}
                          onChange={(e) => setAutoHoldEnabled(e.target.checked)}
                        />
                        <span>自动保持(解算成功后冻结) / Auto Hold</span>
                      </label>
                      {isFrozen && (
                        <button
                          type="button"
                          className="w-full rounded bg-tertiary/80 py-2.5 font-semibold text-on-tertiary disabled:opacity-40"
                          onClick={() => resumeLivePreview()}
                        >
                          继续实时 / Resume Live
                        </button>
                      )}
                      {isFrozen && (
                        <div className="text-[10px] text-on-surface-variant">
                          已冻结帧 / Frozen frame {frozenFrameId ?? "-"}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
              {view === "lab_video" && sysOverview && (
                <div className="shrink-0 border-b border-outline-variant/20 px-4 py-2 text-[10px] text-on-surface-variant">
                  <div className="font-medium text-on-surface">{t("lab.systemLoad")}</div>
                  <div>
                    CPU {sysOverview.cpu_usage}% · RAM {sysOverview.memory_usage}% ·{" "}
                    {sysOverview.temperature}°C
                  </div>
                </div>
              )}
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <details
                  open
                  className="rounded-lg border border-outline-variant/20 bg-surface-container-highest/30"
                >
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 font-semibold text-on-surface-variant [&::-webkit-details-marker]:hidden">
                    {t("params.title")}
                    <ChevronDown className="h-4 w-4 shrink-0" />
                  </summary>
                  <div className="border-t border-outline-variant/15 p-3 pt-2">
                    <p className="mb-3 text-[10px] leading-relaxed text-on-surface-variant/90">
                      {t("params.blockSolveIntro")}
                    </p>
                    <div className="space-y-2">
                      <label className="block">
                        <span className="text-[10px] font-medium text-on-surface-variant">
                          {t("params.solveProfile")}
                        </span>
                        <p className="mb-1 mt-0.5 text-[9px] leading-snug text-on-surface-variant/85">
                          {t("params.solveProfileHelp")}
                        </p>
                        <select
                          className="w-full rounded bg-surface-container-highest px-2 py-1"
                          value={params.solve_profile ?? "balanced"}
                          onChange={(e) =>
                            setParams((p) => ({
                              ...p,
                              solve_profile: e.target.value as
                                | "speed"
                                | "balanced"
                                | "robust",
                            }))
                          }
                        >
                          <option value="speed">{t("params.solveProfileSpeed")}</option>
                          <option value="balanced">{t("params.solveProfileBalanced")}</option>
                          <option value="robust">{t("params.solveProfileRobust")}</option>
                        </select>
                      </label>
                      <Field
                        label={t("params.fov")}
                        helpKey="params.fovHelp"
                        value={params.fov_estimate ?? ""}
                        onChange={(v) => setParams((p) => ({ ...p, fov_estimate: v }))}
                      />
                      <Field
                        label={t("params.fovErr")}
                        helpKey="params.fovErrHelp"
                        value={params.fov_max_error ?? ""}
                        onChange={(v) => setParams((p) => ({ ...p, fov_max_error: v }))}
                      />
                      <Field
                        label={t("params.timeout")}
                        helpKey="params.timeoutHelp"
                        value={params.solve_timeout_ms ?? ""}
                        onChange={(v) => setParams((p) => ({ ...p, solve_timeout_ms: v }))}
                      />
                      <Field
                        label={t("params.solveIntervalMs")}
                        helpKey="params.solveIntervalMsHelp"
                        value={desiredSolveIntervalMs ?? ""}
                        onChange={(v) =>
                          setDesiredSolveIntervalMs(
                            v == null ? defaultIntervalMs : Math.round(v),
                          )
                        }
                      />
                      <p className="text-[9px] leading-snug text-on-surface-variant/80">
                        {t("params.solveIntervalBound", {
                          min: intervalMinMs,
                          max: intervalMaxMs,
                          effective: starAnalysisIntervalMs,
                        })}
                      </p>
                      <Field
                        label={t("params.ra")}
                        helpKey="params.raHelp"
                        value={params.hint_ra_deg ?? ""}
                        onChange={(v) => setParams((p) => ({ ...p, hint_ra_deg: v }))}
                      />
                      <Field
                        label={t("params.dec")}
                        helpKey="params.decHelp"
                        value={params.hint_dec_deg ?? ""}
                        onChange={(v) => setParams((p) => ({ ...p, hint_dec_deg: v }))}
                      />
                      <Field
                        label={t("params.maxSide")}
                        helpKey="params.maxSideHelp"
                        value={params.max_image_side ?? ""}
                        onChange={(v) => setParams((p) => ({ ...p, max_image_side: v }))}
                      />
                      <label className="mt-1.5 flex cursor-pointer items-center gap-2">
                        <input
                          type="checkbox"
                          className="accent-primary"
                          checked={params.detail_level === "full"}
                          onChange={(e) =>
                            setParams((p) => ({
                              ...p,
                              detail_level: e.target.checked ? "full" : "summary",
                            }))
                          }
                        />
                        <span className="text-[10px] text-on-surface-variant">
                          {t("params.detailLevelFull")}
                        </span>
                      </label>
                      <label className="mt-1.5 flex cursor-pointer items-start gap-2">
                        <input
                          type="checkbox"
                          className="accent-primary mt-0.5"
                          checked={!!params.large_scale_bg_subtract}
                          onChange={(e) =>
                            setParams((p) => ({
                              ...p,
                              large_scale_bg_subtract: e.target.checked,
                            }))
                          }
                        />
                        <span>
                          <span className="text-[10px] text-on-surface-variant">
                            {t("params.largeScaleBg")}
                          </span>
                          <p className="mt-0.5 text-[9px] leading-snug text-on-surface-variant/85">
                            {t("params.largeScaleBgHelp")}
                          </p>
                        </span>
                      </label>
                    </div>
                  </div>
                </details>
                <details
                  open
                  className="mt-3 rounded-lg border border-outline-variant/20 bg-surface-container-highest/30"
                >
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 font-semibold text-on-surface-variant [&::-webkit-details-marker]:hidden">
                    {t("params.centroid")}
                    <ChevronDown className="h-4 w-4 shrink-0" />
                  </summary>
                  <div className="border-t border-outline-variant/15 p-3 pt-2">
                    <p className="mb-3 text-[10px] leading-relaxed text-on-surface-variant/90">
                      {t("params.blockCentroidIntro")}
                    </p>
                    <div className="space-y-2">
                      <Field
                        label={t("params.sigma")}
                        helpKey="params.sigmaHelp"
                        step={0.1}
                        value={params.centroid?.sigma ?? ""}
                        onChange={(v) =>
                          setParams((p) => ({
                            ...p,
                            centroid: { ...p.centroid, sigma: v },
                          }))
                        }
                      />
                      <Field
                        label={t("params.maxArea")}
                        helpKey="params.maxAreaHelp"
                        value={params.centroid?.max_area ?? ""}
                        onChange={(v) =>
                          setParams((p) => ({
                            ...p,
                            centroid: { ...p.centroid, max_area: v },
                          }))
                        }
                      />
                      <Field
                        label={t("params.minArea")}
                        helpKey="params.minAreaHelp"
                        value={params.centroid?.min_area ?? ""}
                        onChange={(v) =>
                          setParams((p) => ({
                            ...p,
                            centroid: { ...p.centroid, min_area: v },
                          }))
                        }
                      />
                      <Field
                        label={t("params.filtsize")}
                        helpKey="params.filtsizeHelp"
                        step={2}
                        value={params.centroid?.filtsize ?? ""}
                        onChange={(v) =>
                          setParams((p) => ({
                            ...p,
                            centroid: { ...p.centroid, filtsize: v },
                          }))
                        }
                      />
                    </div>
                  </div>
                </details>
                <div className="mt-4 rounded-md border border-outline-variant/20 bg-surface-container-highest/40 p-3">
                  <div className="mb-2 font-semibold text-on-surface-variant">
                    {t("sidebar.batchPresets")}
                  </div>
                  <p className="mb-2 text-[10px] leading-snug text-on-surface-variant">
                    {t("sidebar.batchHint")}
                  </p>
                  <div className="max-h-36 space-y-1.5 overflow-y-auto">
                    {[...official, ...userPresets].map((p) => (
                      <label key={p.id} className="flex cursor-pointer items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selectedPresetIds.has(p.id)}
                          onChange={() => togglePreset(p.id)}
                        />
                        <span className="truncate">{p.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="mt-6 border-t border-outline-variant/20 pt-4">
                  <div className="mb-2 font-semibold">{t("btn.applyPresets")}</div>
                  <div className="max-h-24 space-y-1 overflow-y-auto">
                    {[...official, ...userPresets].map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        className="block w-full truncate text-left text-primary hover:underline"
                        onClick={() => applyPreset(p.params)}
                      >
                        {p.name}
                      </button>
                    ))}
                  </div>
                  <div className="mt-3 flex gap-1">
                    <input
                      className="flex-1 rounded bg-surface-container-highest px-2 py-1"
                      placeholder={t("placeholder.newPreset")}
                      value={newPresetName}
                      onChange={(e) => setNewPresetName(e.target.value)}
                    />
                    <button
                      type="button"
                      className="rounded bg-surface-container-high px-2"
                      onClick={async () => {
                        if (!newPresetName.trim()) return;
                        setBusy(true);
                        try {
                          await saveUserPreset(newPresetName.trim(), params);
                          setNewPresetName("");
                          await loadLists();
                          const usr = await fetchPresets("user");
                          setUserPresets(usr.presets as typeof userPresets);
                        } catch (e) {
                          setErr(String(e));
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      {t("btn.savePreset")}
                    </button>
                  </div>
                </div>
              </div>
            </aside>
          </div>
        )}

        {view === "pool" && (
          <main className="flex-1 overflow-auto p-4">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <Database className="h-5 w-5" /> {t("pool.title")}
            </h2>
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-outline-variant/30 text-on-surface-variant">
                  <th className="py-2">{t("pool.col.name")}</th>
                  <th className="py-2">{t("pool.col.source")}</th>
                  <th className="py-2">{t("pool.col.size")}</th>
                  <th className="py-2">{t("pool.col.time")}</th>
                  <th className="w-16 py-2 text-center">{t("pool.delete")}</th>
                </tr>
              </thead>
              <tbody>
                {uploads.map((u) => (
                  <tr key={u.filename} className="border-b border-outline-variant/10">
                    <td className="py-2 font-mono">{u.filename}</td>
                    <td className="py-2">{u.source ?? t("common.placeholder")}</td>
                    <td className="py-2">{formatFileSize(u.size)}</td>
                    <td className="py-2">{formatDateTime(u.modified_at, locale)}</td>
                    <td className="py-2 text-center">
                      <button
                        type="button"
                        className="inline-flex rounded p-1 text-on-surface-variant hover:bg-error-container/30 hover:text-error"
                        title={t("pool.delete")}
                        aria-label={t("pool.delete")}
                        onClick={() => void tryDeleteUpload(u.filename)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </main>
        )}

        {view === "history" && (
          <main className="flex-1 overflow-auto p-4">
            <p className="mb-4 rounded-lg border border-outline-variant/25 bg-surface-container-lowest/90 p-3 text-xs leading-relaxed text-on-surface-variant">
              {t("history.intro")}
            </p>
            <div className="mb-4 flex flex-wrap items-center gap-4">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <History className="h-5 w-5" /> {t("history.title")}
              </h2>
              <input
                className="rounded bg-surface-container-highest px-2 py-1 text-xs"
                placeholder={t("history.search")}
                value={historyQ}
                onChange={(e) => setHistoryQ(e.target.value)}
              />
              <button
                type="button"
                className="rounded bg-surface-container px-2 py-1 text-xs"
                onClick={() =>
                  fetchExperiments(historyQ, 1, HISTORY_PAGE_SIZE).then((d) => {
                    setHistoryPage(1);
                    setHistoryData(d);
                  })
                }
              >
                {t("history.searchBtn")}
              </button>
              <button
                type="button"
                className="rounded bg-primary-container/50 px-2 py-1 text-xs"
                onClick={() =>
                  exportExperiments("json").then((text) => {
                    const blob = new Blob([text], { type: "application/json" });
                    const a = document.createElement("a");
                    a.href = URL.createObjectURL(blob);
                    a.download = "experiments.json";
                    a.click();
                  })
                }
              >
                {t("history.exportJson")}
              </button>
              <button
                type="button"
                className="rounded bg-primary-container/50 px-2 py-1 text-xs"
                onClick={() =>
                  exportExperiments("csv").then((text) => {
                    const blob = new Blob([text], { type: "text/csv" });
                    const a = document.createElement("a");
                    a.href = URL.createObjectURL(blob);
                    a.download = "experiments.csv";
                    a.click();
                  })
                }
              >
                {t("history.exportCsv")}
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-on-surface-variant">
              <span>{t("history.total", { n: historyData?.total ?? 0 })}</span>
              <button
                type="button"
                className="rounded border border-outline-variant/30 px-2 py-0.5 disabled:opacity-40"
                disabled={historyPage <= 1}
                onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
              >
                {t("history.prev")}
              </button>
              <span>
                {historyPage} / {historyTotalPages}
              </span>
              <button
                type="button"
                className="rounded border border-outline-variant/30 px-2 py-0.5 disabled:opacity-40"
                disabled={historyPage >= historyTotalPages}
                onClick={() => setHistoryPage((p) => p + 1)}
              >
                {t("history.next")}
              </button>
            </div>
            <ul className="mt-2 space-y-2">
              {(historyData?.items as Array<Record<string, unknown>>)?.map((row) => {
                const id = String(row.id ?? "");
                const metrics = row.metrics as Record<string, unknown> | undefined;
                const open = historyExpandId === id;
                return (
                  <li
                    key={id}
                    className="rounded border border-outline-variant/20 p-2 text-[11px]"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2 font-mono">
                      <div>
                        <div className="text-on-surface">
                          {formatDateTime(String(row.created_at ?? ""), locale)} —{" "}
                          {String(row.input_name)} — {String(row.preset_label)}
                        </div>
                        <div className="mt-1 text-on-surface-variant">
                          {t("history.preset")}: {String(row.preset_label)} · {t("history.metrics")}:{" "}
                          matches={String(metrics?.matches ?? "—")} rmse=
                          {String(metrics?.rmse_arcsec ?? "—")}
                        </div>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          className="rounded bg-surface-container px-2 py-0.5 text-[10px]"
                          onClick={() => setHistoryExpandId(open ? null : id)}
                        >
                          {open ? t("history.collapse") : t("history.detail")}
                        </button>
                        <button
                          type="button"
                          className="rounded px-2 py-0.5 text-[10px] text-error hover:bg-error-container/20"
                          title={t("history.delete")}
                          onClick={() => void tryDeleteExperiment(id)}
                        >
                          {t("history.delete")}
                        </button>
                      </div>
                    </div>
                    {open && (
                      <div className="mt-2 space-y-2">
                        {row.asset_snapshot_relpath ? (
                          <img
                            src={experimentAssetUrl(id)}
                            alt=""
                            className="max-h-48 max-w-full rounded border border-outline-variant/20 object-contain"
                          />
                        ) : null}
                        <pre className="max-h-64 overflow-auto rounded bg-surface-container p-2 text-[10px]">
                          {JSON.stringify(row.result_json, null, 2)}
                        </pre>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </main>
        )}
      </div>
    </div>
  );
}

function SolveFooterSummary({
  result,
  t,
  roundTripMs,
}: {
  result: Record<string, unknown> | null | undefined;
  t: (key: string, vars?: Record<string, string | number>) => string;
  roundTripMs: number | null;
}) {
  const s = parseSolveResult(result ?? undefined);
  if (!result) {
    return <p className="mt-2 text-[10px] text-on-surface-variant">—</p>;
  }
  return (
    <div className="mt-2 space-y-2 text-[10px]">
      <div className="grid grid-cols-2 gap-2">
        {s.tBackendTotalMs != null && (
          <div>
            <div className="text-on-surface-variant">{t("lab.metric.backendTotalMs")}</div>
            <div className="font-semibold tabular-nums text-on-surface">
              {s.tBackendTotalMs.toFixed(0)} ms
            </div>
          </div>
        )}
        {s.tSolveMs != null && (
          <div>
            <div className="text-on-surface-variant">{t("lab.metric.solveComputeMs")}</div>
            <div className="font-semibold tabular-nums text-on-surface">
              {s.tSolveMs.toFixed(0)} ms
            </div>
          </div>
        )}
        {s.tOpenDecodeMs != null && (
          <div>
            <div className="text-on-surface-variant">{t("lab.metric.openDecodeMs")}</div>
            <div className="font-semibold tabular-nums text-on-surface">
              {s.tOpenDecodeMs.toFixed(0)} ms
            </div>
          </div>
        )}
        {s.tPreprocessMs != null && (
          <div>
            <div className="text-on-surface-variant">{t("lab.metric.preprocessMs")}</div>
            <div className="font-semibold tabular-nums text-on-surface">
              {s.tPreprocessMs.toFixed(0)} ms
            </div>
          </div>
        )}
        {s.tExtractMs != null && (
          <div>
            <div className="text-on-surface-variant">{t("lab.metric.extractMs")}</div>
            <div className="font-semibold tabular-nums text-on-surface">
              {s.tExtractMs.toFixed(0)} ms
            </div>
          </div>
        )}
        {roundTripMs != null && (
          <div>
            <div className="text-on-surface-variant">{t("lab.metric.solveRoundTripMs")}</div>
            <div className="font-semibold tabular-nums text-on-surface">
              {roundTripMs.toFixed(0)} ms
            </div>
          </div>
        )}
        {s.matches != null && (
          <div>
            <div className="text-on-surface-variant">{t("lab.metric.matches")}</div>
            <div className="font-semibold tabular-nums text-on-surface">{s.matches}</div>
          </div>
        )}
        {s.rmseArcsec != null && (
          <div>
            <div className="text-on-surface-variant">{t("lab.metric.rmse")}</div>
            <div className="font-semibold tabular-nums text-on-surface">
              {s.rmseArcsec.toFixed(2)}″
            </div>
          </div>
        )}
        {s.prob != null && (
          <div className="col-span-2">
            <div className="text-on-surface-variant">{t("lab.metric.prob")}</div>
            <div className="font-semibold text-on-surface">
              {formatProbLine(s.prob, result).line}
            </div>
            <p className="mt-0.5 text-[9px] leading-snug text-on-surface-variant/90">
              {t("lab.metric.probHelp")}
            </p>
            {formatProbLine(s.prob, result).rawLine && (
              <div className="mt-1 text-[9px] text-on-surface-variant">
                {t("lab.metric.probRaw")}: {formatProbLine(s.prob, result).rawLine}
                <p className="mt-0.5 text-[8px] leading-snug opacity-90">
                  {t("lab.metric.probRawHelp")}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
      <div>
        <div className="text-on-surface-variant">{t("lab.metric.radec")}</div>
        <div className="font-mono text-[9px] text-on-surface">
          α {formatAngleDeg(s.raDeg)} · δ {formatAngleDeg(s.decDeg)}
        </div>
      </div>
      {s.status && (
        <div className="rounded bg-surface-container-high px-2 py-1 text-[9px] font-mono text-on-surface">
          {t("lab.metric.status")}: {s.status}
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  helpKey,
  value,
  onChange,
  type = "number",
  step,
}: {
  label: string;
  helpKey?: string;
  value: number | "";
  onChange: (v: number | undefined) => void;
  type?: string;
  step?: number;
}) {
  const { t } = useI18n();
  const help = helpKey ? t(helpKey) : undefined;
  return (
    <label className="block">
      <span className="text-[10px] font-medium text-on-surface-variant">{label}</span>
      {help && (
        <p className="mb-1 mt-0.5 text-[9px] leading-snug text-on-surface-variant/85">{help}</p>
      )}
      <input
        type={type}
        step={step}
        className="w-full rounded bg-surface-container-highest px-2 py-1"
        value={value === "" ? "" : value}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "") onChange(undefined);
          else onChange(type === "number" ? Number(v) : Number(v));
        }}
      />
    </label>
  );
}
