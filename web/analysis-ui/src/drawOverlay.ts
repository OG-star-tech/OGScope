/** 解算叠加绘制（与旧 debug-analysis 逻辑一致）/ Solve overlay drawing */

export type LayerToggles = {
  matched: boolean;
  pattern: boolean;
  all: boolean;
};

export type SolveOverlay = {
  stars_all_centroids?: Array<{ x: number; y: number }>;
  stars_pattern?: Array<{ x: number; y: number }>;
  stars_matched?: Array<{ x: number; y: number; mag?: number }>;
  overlay_ext?: {
    labels_topn?: Array<{
      x: number;
      y: number;
      name?: string;
      mag?: number | null;
      ra_deg?: number | null;
      dec_deg?: number | null;
    }>;
    polar_guide?: {
      target_kind?: string;
      frame_center?: { x: number; y: number };
      target?: { x: number; y: number };
      delta_px?: { dx: number; dy: number };
      angular_sep_deg?: number;
    } | null;
  };
};

function drawOverlayCore(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  overlay: SolveOverlay | null | undefined,
  layers: LayerToggles,
): void {
  if (!overlay) return;
  ctx.clearRect(0, 0, w, h);

  if (layers.all && Array.isArray(overlay.stars_all_centroids)) {
    ctx.fillStyle = "rgba(156, 163, 175, 0.85)";
    for (const s of overlay.stars_all_centroids) {
      ctx.beginPath();
      ctx.arc(s.x, s.y, 2.4, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  if (layers.pattern && Array.isArray(overlay.stars_pattern)) {
    ctx.strokeStyle = "rgba(251, 146, 60, 0.95)";
    ctx.lineWidth = 2;
    for (const s of overlay.stars_pattern) {
      ctx.beginPath();
      ctx.arc(s.x, s.y, 6, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
  if (layers.matched && Array.isArray(overlay.stars_matched)) {
    ctx.strokeStyle = "rgba(34, 197, 94, 0.95)";
    ctx.fillStyle = "rgba(34, 197, 94, 0.95)";
    ctx.lineWidth = 2;
    ctx.font = "11px system-ui, sans-serif";
    for (const s of overlay.stars_matched) {
      ctx.beginPath();
      ctx.arc(s.x, s.y, 7, 0, Math.PI * 2);
      ctx.stroke();
      if (s.mag != null) {
        ctx.fillText(`m${Number(s.mag).toFixed(1)}`, s.x + 4, s.y - 4);
      }
    }
  }
  const ext = overlay.overlay_ext;
  if (Array.isArray(ext?.labels_topn) && ext.labels_topn.length > 0) {
    ctx.fillStyle = "rgba(96, 165, 250, 0.95)";
    ctx.font = "12px system-ui, sans-serif";
    for (const s of ext.labels_topn) {
      if (typeof s?.x !== "number" || typeof s?.y !== "number") continue;
      const magText = typeof s.mag === "number" ? ` m${s.mag.toFixed(1)}` : "";
      const title = `${s.name ?? "Star"}${magText}`;
      ctx.fillText(title, s.x + 8, s.y + 14);
    }
  }
  const guide = ext?.polar_guide;
  if (
    guide &&
    typeof guide.frame_center?.x === "number" &&
    typeof guide.frame_center?.y === "number" &&
    typeof guide.target?.x === "number" &&
    typeof guide.target?.y === "number"
  ) {
    const cx = guide.frame_center.x;
    const cy = guide.frame_center.y;
    const tx = guide.target.x;
    const ty = guide.target.y;
    ctx.strokeStyle = "rgba(244, 63, 94, 0.95)";
    ctx.fillStyle = "rgba(244, 63, 94, 0.95)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(tx, ty);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(tx, ty, 6, 0, Math.PI * 2);
    ctx.stroke();
    const ang = typeof guide.angular_sep_deg === "number" ? guide.angular_sep_deg.toFixed(2) : "-";
    ctx.font = "12px system-ui, sans-serif";
    ctx.fillText(`Polar ${ang}deg`, tx + 10, ty - 6);
  }
}

export function drawSolveOverlay(
  canvas: HTMLCanvasElement,
  img: HTMLImageElement,
  overlay: SolveOverlay | null | undefined,
  layers: LayerToggles,
): void {
  if (!overlay) return;
  const w = img.naturalWidth || 1;
  const h = img.naturalHeight || 1;
  canvas.width = w;
  canvas.height = h;
  canvas.style.width = `${img.clientWidth}px`;
  canvas.style.height = `${img.clientHeight}px`;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  drawOverlayCore(ctx, w, h, overlay, layers);
}

/** 视频当前帧上的叠加（坐标与 videoWidth/Height 一致）/ Overlay on video frame pixels */
export function drawSolveOverlayVideo(
  canvas: HTMLCanvasElement,
  video: HTMLVideoElement,
  overlay: SolveOverlay | null | undefined,
  layers: LayerToggles,
): void {
  if (!overlay) return;
  const w = video.videoWidth || 1;
  const h = video.videoHeight || 1;
  if (w < 2 || h < 2) return;
  canvas.width = w;
  canvas.height = h;
  canvas.style.width = `${video.clientWidth}px`;
  canvas.style.height = `${video.clientHeight}px`;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  drawOverlayCore(ctx, w, h, overlay, layers);
}
