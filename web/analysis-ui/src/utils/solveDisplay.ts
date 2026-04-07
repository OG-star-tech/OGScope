/** 解算结果摘要（与后端 solve 行一致）/ Solve row summary for UI */

export type SolveSummary = {
  tSolveMs: number | null;
  tExtractMs: number | null;
  tPreprocessMs: number | null;
  tOpenDecodeMs: number | null;
  tBackendTotalMs: number | null;
  raDeg: number | null;
  decDeg: number | null;
  matches: number | null;
  rmseArcsec: number | null;
  prob: number | null;
  status: string | null;
};

export function parseSolveResult(
  r: Record<string, unknown> | null | undefined,
): SolveSummary {
  const num = (x: unknown): number | null =>
    typeof x === "number" && !Number.isNaN(x) ? x : null;
  if (!r) {
    return {
      tSolveMs: null,
      tExtractMs: null,
      tPreprocessMs: null,
      tOpenDecodeMs: null,
      tBackendTotalMs: null,
      raDeg: null,
      decDeg: null,
      matches: null,
      rmseArcsec: null,
      prob: null,
      status: null,
    };
  }
  return {
    tSolveMs: num(r.t_solve_ms),
    tExtractMs: num(r.t_extract_ms),
    tPreprocessMs: num(r.t_preprocess_ms),
    tOpenDecodeMs: num(r.t_open_decode_ms),
    tBackendTotalMs: num(r.t_backend_total_ms),
    raDeg: num(r.ra_deg),
    decDeg: num(r.dec_deg),
    matches: num(r.matches),
    rmseArcsec: num(r.rmse_arcsec),
    prob: num(r.prob),
    status: typeof r.status === "string" ? r.status : null,
  };
}

export function formatAngleDeg(v: number | null): string {
  if (v == null) return "—";
  return `${v.toFixed(4)}°`;
}

/**
 * Tetra3 `Prob`：假阳性概率（越低越可信）/ Tetra3 Prob = false-positive probability (lower is better).
 * 界面匹配置信度：0–100% / Display match confidence in 0–100%.
 */
export function tetraFalsePositiveProbToConfidencePercent(
  fp: number | null | undefined,
): number | null {
  if (fp == null || typeof fp !== "number" || Number.isNaN(fp) || fp < 0) return null;
  const capped = Math.min(1, fp);
  return Math.min(100, Math.max(0, (1 - capped) * 100));
}

/** 匹配置信度百分比字符串 / Match confidence percent string */
export function formatProb(p: number | null): string {
  const pct = tetraFalsePositiveProbToConfidencePercent(p);
  if (pct == null) return "—";
  return `${pct.toFixed(1)}%`;
}

/** 原始 Tetra3 Prob 字段（可能为对数等）/ Raw Prob from tetra block */
export function formatTetraProb(raw: unknown): string {
  if (raw === null || raw === undefined) return "—";
  if (typeof raw === "number" && !Number.isNaN(raw)) {
    const a = Math.abs(raw);
    if (a > 0 && a < 1e-3) return raw.toExponential(4);
    if (a >= 0 && a <= 1) return `${(raw * 100).toFixed(4)}%`;
    return String(raw);
  }
  return String(raw);
}

/** 置信度展示：与预览角标同一换算 / Same conversion as preview badge */
export function formatProbLine(
  p: number | null,
  result: Record<string, unknown> | null | undefined,
): { line: string; rawLine: string | null } {
  const tetra = result?.tetra as Record<string, unknown> | undefined;
  const rawProb = tetra ? (tetra.Prob ?? tetra.prob) : undefined;
  const line = formatProb(p);
  const rawLine =
    rawProb !== undefined && rawProb !== null ? formatTetraProb(rawProb) : null;
  return { line, rawLine };
}
