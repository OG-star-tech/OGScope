/** 解算实验室路由与历史类型 / Plate-solve lab view types */

import type { SolveParams } from "@dev-api/analysis";

export type LabView = "lab_image" | "lab_video" | "pool" | "history";

/** 单次请求解算历史快照（最多 10 组）/ One request snapshot for solve history */
export type SolveHistoryGroup = {
  id: string;
  at: number;
  single?: Record<string, unknown> | null;
  batch?: { results: Array<Record<string, unknown>> } | null;
};

export const SOLVE_HISTORY_MAX = 10;
export const HISTORY_PAGE_SIZE = 30;
/** 调试控制台素材列表每页条数 / Items per page for debug media list */
export const DEBUG_PAGE_SIZE = 6;

export const defaultLabParams = (): SolveParams => ({
  hint_ra_deg: 45,
  hint_dec_deg: 80,
  fov_estimate: 11,
  fov_max_error: undefined,
  solve_timeout_ms: 1500,
  solve_profile: "balanced",
  max_image_side: 1280,
  large_scale_bg_subtract: false,
  detail_level: "summary",
  centroid_rejection_level: 3,
  centroid: {
    sigma: 2.5,
    max_area: 400,
    min_area: 5,
    filtsize: 25,
    binary_open: true,
    max_axis_ratio: undefined,
  },
});
