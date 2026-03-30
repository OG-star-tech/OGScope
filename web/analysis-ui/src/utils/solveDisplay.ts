/** 解算结果摘要（与后端 solve 行一致）/ Solve row summary for UI */

export type SolveSummary = {
  tSolveMs: number | null;
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

/** 置信度 0–1 转百分比 / Confidence to percent string */
export function formatProb(p: number | null): string {
  if (p == null) return "—";
  if (p >= 0 && p <= 1) return `${(p * 100).toFixed(1)}%`;
  return String(p);
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

/** 置信度展示：极小值与 0 更易读 / Human-readable confidence line */
export function formatProbLine(
  p: number | null,
  result: Record<string, unknown> | null | undefined,
): { line: string; rawLine: string | null } {
  const tetra = result?.tetra as Record<string, unknown> | undefined;
  const rawProb = tetra ? (tetra.Prob ?? tetra.prob) : undefined;
  let line = formatProb(p);
  if (p != null && p >= 0 && p <= 1 && p > 0 && p < 0.0001) {
    line = `${(p * 100).toExponential(2)}%`;
  }
  if (p === 0 && rawProb !== undefined && rawProb !== null) {
    line = "—";
  }
  const rawLine =
    rawProb !== undefined && rawProb !== null ? formatTetraProb(rawProb) : null;
  return { line, rawLine };
}
