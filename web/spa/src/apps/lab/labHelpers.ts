/** 解算实验室纯函数 / Plate-solve lab pure helpers */

import type { SolveOverlay } from "@shared/drawOverlay";

export function metricsFromResult(result: Record<string, unknown> | null): Record<string, unknown> {
  if (!result) return {};
  return {
    matches: result.matches,
    rmse_arcsec: result.rmse_arcsec,
    status: result.status,
    prob: result.prob,
    t_solve_ms: result.t_solve_ms,
  };
}

export function countStarsFromOverlay(
  result: Record<string, unknown> | null,
): number | null {
  if (!result) return null;
  const ov = result.solve_overlay as SolveOverlay | undefined;
  if (ov?.stars_matched?.length) return ov.stars_matched.length;
  if (ov?.stars_all_centroids?.length) return ov.stars_all_centroids.length;
  if (typeof result.matches === "number") return result.matches;
  return null;
}

export function isImageAsset(name: string): boolean {
  return /\.(jpe?g|png|webp|bmp|gif|fits?)$/i.test(name);
}

export function isVideoAsset(name: string): boolean {
  return /\.(mp4|mov|webm|mkv|avi)$/i.test(name);
}

export function compactFilename(name: string, head = 16, tail = 14): string {
  if (name.length <= head + tail + 1) return name;
  return `${name.slice(0, head)}...${name.slice(-tail)}`;
}
