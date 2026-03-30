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
};

export function drawSolveOverlay(
  canvas: HTMLCanvasElement,
  img: HTMLImageElement,
  overlay: SolveOverlay | null | undefined,
  layers: LayerToggles
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
}
