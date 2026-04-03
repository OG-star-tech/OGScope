import { FFmpeg } from "@ffmpeg/ffmpeg";
import { fetchFile, toBlobURL } from "@ffmpeg/util";

type TranscodeProgress = (ratio: number, message?: string) => void;

let ffmpegSingleton: FFmpeg | null = null;
let ffmpegLoading: Promise<FFmpeg> | null = null;

/** 当前一次转码的进度回调（单例 FFmpeg 只注册一次 progress，需用可变引用）/ Mutable ref so each run gets correct progress. */
let currentTranscodeProgress: TranscodeProgress | undefined;

async function ensureFfmpeg(): Promise<FFmpeg> {
  if (ffmpegSingleton) return ffmpegSingleton;
  if (ffmpegLoading) return ffmpegLoading;
  ffmpegLoading = (async () => {
    const ffmpeg = new FFmpeg();
    ffmpeg.on("progress", ({ progress }) => {
      currentTranscodeProgress?.(progress, "transcoding");
    });
    // 在拉取 wasm 之前即上报，避免界面长时间停在导入后的百分比 / Report before CDN fetch (can be slow).
    currentTranscodeProgress?.(0.01, "loading_ffmpeg");
    const base = "https://unpkg.com/@ffmpeg/core@0.12.6/dist/esm";
    const coreURL = await toBlobURL(`${base}/ffmpeg-core.js`, "text/javascript");
    currentTranscodeProgress?.(0.04, "loading_ffmpeg");
    const wasmURL = await toBlobURL(
      `${base}/ffmpeg-core.wasm`,
      "application/wasm",
    );
    currentTranscodeProgress?.(0.07, "loading_ffmpeg");
    await ffmpeg.load({ coreURL, wasmURL });
    ffmpegSingleton = ffmpeg;
    return ffmpeg;
  })();
  try {
    return await ffmpegLoading;
  } finally {
    ffmpegLoading = null;
  }
}

async function probeDurationSeconds(file: File): Promise<number | null> {
  const url = URL.createObjectURL(file);
  try {
    const duration = await new Promise<number | null>((resolve) => {
      const v = document.createElement("video");
      v.preload = "metadata";
      v.onloadedmetadata = () => {
        const d = Number(v.duration);
        resolve(Number.isFinite(d) && d > 0 ? d : null);
      };
      v.onerror = () => resolve(null);
      v.src = url;
    });
    return duration;
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function transcodeAviToMp4(
  input: File,
  onProgress?: TranscodeProgress,
): Promise<{ file: File; duration_s: number | null }> {
  const prev = currentTranscodeProgress;
  currentTranscodeProgress = onProgress;
  try {
    const ffmpeg = await ensureFfmpeg();
    const srcName = "input.avi";
    const outName = "output.mp4";
    onProgress?.(0.1, "writing_input");
    await ffmpeg.writeFile(srcName, await fetchFile(input));
    // 低复杂度参数，优先速度与兼容性 / Favor speed and compatibility.
    await ffmpeg.exec([
      "-i",
      srcName,
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "24",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      "-an",
      outName,
    ]);
    const output = await ffmpeg.readFile(outName);
    onProgress?.(0.98, "packing_output");
    const blob = new Blob([output], { type: "video/mp4" });
    const outFile = new File([blob], input.name.replace(/\.avi$/i, ".mp4"), {
      type: "video/mp4",
    });
    // 清理虚拟文件，避免 wasm 内存堆积 / Cleanup in-memory FS.
    await ffmpeg.deleteFile(srcName);
    await ffmpeg.deleteFile(outName);
    const duration_s = await probeDurationSeconds(outFile);
    onProgress?.(1, "done");
    return { file: outFile, duration_s };
  } finally {
    currentTranscodeProgress = prev;
  }
}
