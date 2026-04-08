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
 *
 * 当 fp 极小时，`(1-fp)*100` 在 IEEE 双精度下会舍入为 100，导致界面恒为 100%。
 * 此时用 `-log10(fp)` 在 70–100% 之间插值，仅用于区分不同极小假阳性（与线性段语义一致：fp 越小越高）。
 * When fp is tiny, `(1-fp)*100` rounds to 100 in IEEE double; use `-log10(fp)` to spread 70–100%.
 */
export function tetraFalsePositiveProbToConfidencePercent(
  fp: number | null | undefined,
): number | null {
  if (fp == null || typeof fp !== "number" || Number.isNaN(fp) || fp < 0) return null;
  if (fp >= 1) return 0;
  if (fp === 0) return 100;

  const raw = (1 - fp) * 100;
  // 与 100 的差仍可在 float 中表示时，直接用线性换算 / Linear when 100 - fp*100 is representable
  if (raw <= 100 - 1e-12) {
    return Math.min(100, Math.max(0, raw));
  }

  const L = -Math.log10(Math.max(fp, Number.MIN_VALUE));
  const L0 = 14;
  const L1 = 50;
  const t = Math.min(1, Math.max(0, (L - L0) / (L1 - L0)));
  return Math.min(100, Math.max(0, 70 + 30 * t));
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
