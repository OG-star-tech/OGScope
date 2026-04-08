import {
  formatAngleDeg,
  formatProbLine,
  parseSolveResult,
} from "@shared/utils/solveDisplay";
import { useI18n } from "@shared/i18n/I18nProvider";

export function SolveFooterSummary({
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
      {result.centroid_quality != null &&
        typeof result.centroid_quality === "object" && (
          <div className="rounded border border-outline-variant/25 bg-surface-container-high/40 p-2">
            <div className="text-[9px] font-medium text-on-surface-variant">
              {t("lab.centroidQualityTitle")}
              {typeof (result.centroid_quality as { level?: number }).level === "number"
                ? ` · L${(result.centroid_quality as { level: number }).level}`
                : ""}
            </div>
            {Array.isArray((result.centroid_quality as { hints?: unknown }).hints) &&
            (result.centroid_quality as { hints: string[] }).hints.length > 0 ? (
              <ul className="mt-1 list-inside list-disc text-[9px] leading-snug text-on-surface-variant">
                {(result.centroid_quality as { hints: string[] }).hints.map((h, i) => (
                  <li key={i}>{h}</li>
                ))}
              </ul>
            ) : null}
            {(() => {
              const m = (result.centroid_quality as { metrics?: Record<string, unknown> })
                .metrics;
              if (!m) return null;
              const inn = m.input_count;
              const outc = m.output_count;
              const rd = m.removed_dense;
              const rl = m.removed_line;
              if (
                typeof inn !== "number" ||
                typeof outc !== "number" ||
                typeof rd !== "number" ||
                typeof rl !== "number"
              ) {
                return null;
              }
              return (
                <p className="mt-1 font-mono text-[9px] text-on-surface-variant/95">
                  {t("lab.centroidQualityMetrics", {
                    in: inn,
                    out: outc,
                    dense: rd,
                    line: rl,
                  })}
                </p>
              );
            })()}
          </div>
        )}
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

export function Field({
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
