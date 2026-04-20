import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@shared/i18n/I18nProvider";
import { requestDevDebugJson } from "@shared/transport/http";

type SampleResponse = {
  success?: boolean;
  heading_deg?: number;
  field_ut?: { x: number; y: number; z: number };
  field_raw?: { x: number; y: number; z: number };
  error?: string;
};

/** 每度占用像素，越大磁带越“疏” / Pixels per degree — larger = more spread. */
const PX_PER_DEG = 3.4;
/** 重复 0–360° 的周期数，用于横向无限感 / Number of 360° cycles laid side by side. */
const TAPE_CYCLES = 7;
/** 中间周期索引，航向落在该段附近便于左右滚动 / Center cycle index for anchoring. */
const CENTER_CYCLE = 3;

function cardinalLabel(deg: number): string | null {
  const d = ((deg % 360) + 360) % 360;
  if (d < 1 || d > 359) return "N";
  if (Math.abs(d - 90) < 1) return "E";
  if (Math.abs(d - 180) < 1) return "S";
  if (Math.abs(d - 270) < 1) return "W";
  return null;
}

type TapeTick = { x: number; deg: number; h: "maj" | "mid" | "min"; label?: string };

function buildTapeTicks(): TapeTick[] {
  const ticks: TapeTick[] = [];
  const maxDeg = TAPE_CYCLES * 360;
  for (let g = 0; g <= maxDeg; g += 5) {
    const degMod = g % 360;
    const maj = g % 30 === 0;
    const mid = !maj && g % 10 === 0;
    const card = cardinalLabel(degMod);
    const label =
      card ??
      (maj && degMod % 90 !== 0 ? String(degMod) : undefined);
    ticks.push({
      x: g * PX_PER_DEG,
      deg: g,
      h: maj ? "maj" : mid ? "mid" : "min",
      label,
    });
  }
  return ticks;
}

const TAPE_TICKS = buildTapeTicks();
const TAPE_WIDTH = TAPE_CYCLES * 360 * PX_PER_DEG;

/** 按最短角路径累加，避免 359°→1° 时磁带反向扫一圈 / Unwrap heading for smooth tape motion. */
function addShortest(prevU: number, newHeading: number): number {
  const prevMod = ((prevU % 360) + 360) % 360;
  const h = ((newHeading % 360) + 360) % 360;
  let d = h - prevMod;
  d = ((d + 180) % 360) - 180;
  return prevU + d;
}

/**
 * AK09911 磁力计：水平磁带式电子罗盘（固定中心标线、刻度带平移）。
 * AK09911: horizontal heading tape (fixed index, scrolling scale).
 */
export function MagnetometerCompassPanel(props: { bus: number; addr: number }) {
  const { bus, addr } = props;
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** 连续角度（度），用于磁带平移与跨 0° 平滑 / Continuous degrees for tape & smooth wrap. */
  const [unwrappedDeg, setUnwrappedDeg] = useState<number | null>(null);
  const [fieldUt, setFieldUt] = useState<{ x: number; y: number; z: number } | null>(null);
  const [live, setLive] = useState(false);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const viewportRef = useRef<HTMLDivElement>(null);
  const [viewW, setViewW] = useState(320);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setViewW(Math.max(200, el.clientWidth));
    });
    ro.observe(el);
    setViewW(Math.max(200, el.clientWidth));
    return () => ro.disconnect();
  }, []);

  /** 总线/地址变更时重置连续角，避免错位 / Reset unwrap when I²C target changes. */
  useEffect(() => {
    setUnwrappedDeg(null);
    setFieldUt(null);
    setError(null);
  }, [bus, addr]);

  const fetchSample = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ bus: String(bus), addr: String(addr) });
      const data = await requestDevDebugJson<SampleResponse>(
        `/api/debug/sensors/magnetometer/sample?${qs.toString()}`,
      );
      if (!data.success) {
        setUnwrappedDeg(null);
        setFieldUt(null);
        setError(data.error || t("sys.sensors.compass.err"));
        return;
      }
      const h = data.heading_deg ?? null;
      if (h != null) {
        setUnwrappedDeg((u) => (u == null ? CENTER_CYCLE * 360 + h : addShortest(u, h)));
      }
      setFieldUt(data.field_ut ?? null);
    } catch (e) {
      setUnwrappedDeg(null);
      setFieldUt(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [addr, bus, t]);

  useEffect(() => {
    if (!live) {
      if (tickRef.current) {
        clearInterval(tickRef.current);
        tickRef.current = null;
      }
      return;
    }
    tickRef.current = setInterval(() => {
      void fetchSample();
    }, 550);
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, [live, fetchSample]);

  /** 磁带平移：使 unwrapped 航向对准视口中心 / Tape shift so current unwrapped heading is centered. */
  const tapeTranslateX = useMemo(() => {
    if (unwrappedDeg == null) return 0;
    const anchorPx = unwrappedDeg * PX_PER_DEG;
    return viewW / 2 - anchorPx;
  }, [unwrappedDeg, viewW]);

  const displayDeg =
    unwrappedDeg != null ? ((unwrappedDeg % 360) + 360) % 360 : null;

  return (
    <div className="rounded-xl border border-sky-500/30 bg-gradient-to-b from-slate-900/90 via-slate-900/70 to-surface-container/90 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-on-surface">{t("sys.sensors.compass.title")}</p>
          <p className="mt-1 max-w-xl text-[11px] leading-snug text-on-surface-variant">
            {t("sys.sensors.compass.desc")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-on-surface-variant">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
            {t("sys.sensors.compass.live")}
          </label>
          <button
            type="button"
            disabled={loading}
            className="rounded-lg bg-sky-700/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-600 disabled:opacity-50"
            onClick={() => void fetchSample()}
          >
            {loading ? t("sys.sensors.compass.loading") : t("sys.sensors.compass.btn")}
          </button>
        </div>
      </div>

      {/* 水平磁带罗盘 / Horizontal heading tape */}
      <div className="mt-5">
        <p className="mb-2 text-center text-[10px] uppercase tracking-[0.2em] text-sky-300/90">
          {t("sys.sensors.compass.tapeCaption")}
        </p>
        <div
          ref={viewportRef}
          className="relative mx-auto h-[112px] w-full max-w-3xl overflow-hidden rounded-lg ring-1 ring-sky-500/25"
          style={{
            maskImage: "linear-gradient(90deg, transparent 0%, black 10%, black 90%, transparent 100%)",
            WebkitMaskImage: "linear-gradient(90deg, transparent 0%, black 10%, black 90%, transparent 100%)",
          }}
        >
          {/* 中心固定参考（机头/读数线）/ Fixed datum */}
          <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex justify-center">
            <div className="flex flex-col items-center">
              <div className="h-0 w-0 border-x-[9px] border-x-transparent border-b-[12px] border-b-amber-400 drop-shadow" />
              <div className="h-[88px] w-0.5 rounded-full bg-gradient-to-b from-amber-300/95 to-sky-400/40" />
            </div>
          </div>

          <div
            className="absolute bottom-0 left-0 top-0 will-change-transform"
            style={{
              width: TAPE_WIDTH,
              transform: `translateX(${tapeTranslateX}px)`,
              transition: "transform 0.42s cubic-bezier(0.22, 0.95, 0.28, 1)",
            }}
          >
            <div
              className="relative h-full"
              style={{
                width: TAPE_WIDTH,
                background:
                  "linear-gradient(180deg, rgba(15,23,42,0.2) 0%, rgba(30,41,59,0.85) 40%, rgba(15,23,42,0.95) 100%)",
              }}
            >
              {/* 顶部分隔线 / Top rail */}
              <div className="absolute left-0 right-0 top-8 h-px bg-slate-600/60" />

              {TAPE_TICKS.map((tk) => {
                const hPx = tk.h === "maj" ? 22 : tk.h === "mid" ? 14 : 8;
                const top = 32;
                return (
                  <div
                    key={tk.deg}
                    className="absolute flex flex-col items-center"
                    style={{ left: tk.x, transform: "translateX(-50%)", top }}
                  >
                    {tk.label && (
                      <span
                        className={`mb-0.5 whitespace-nowrap font-mono ${
                          ["N", "E", "S", "W"].includes(tk.label)
                            ? "text-[13px] font-bold text-sky-200"
                            : "text-[10px] font-medium text-slate-400"
                        }`}
                        style={{ marginTop: -18 }}
                      >
                        {tk.label}
                      </span>
                    )}
                    <div
                      className={`w-px rounded-full ${
                        tk.h === "maj"
                          ? "bg-sky-300/90"
                          : tk.h === "mid"
                            ? "bg-slate-500/85"
                            : "bg-slate-600/50"
                      }`}
                      style={{ height: hPx }}
                    />
                  </div>
                );
              })}

              {/* 底部分隔线 / Bottom rail */}
              <div className="absolute bottom-6 left-0 right-0 h-px bg-slate-600/40" />
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-4 md:flex-row md:items-start md:justify-center md:gap-8">
        <div className="rounded-lg border border-outline-variant/30 bg-surface-container/90 px-6 py-4 text-center md:min-w-[200px]">
          <p className="text-[10px] uppercase tracking-widest text-on-surface-variant">
            {t("sys.sensors.compass.headingLabel")}
          </p>
          <p className="font-mono text-4xl font-bold tabular-nums text-sky-200">
            {displayDeg != null ? `${displayDeg.toFixed(1)}°` : "—"}
          </p>
          <p className="mt-1 text-[10px] text-on-surface-variant">{t("sys.sensors.compass.headingHint")}</p>
        </div>

        {fieldUt && (
          <div className="rounded-lg border border-outline-variant/20 px-4 py-3 font-mono text-[11px] text-on-surface md:max-w-md">
            <p className="mb-1 text-[10px] text-on-surface-variant">µT (X / Y / Z)</p>
            <p className="tabular-nums">
              {fieldUt.x.toFixed(2)} · {fieldUt.y.toFixed(2)} · {fieldUt.z.toFixed(2)}
            </p>
          </div>
        )}
      </div>

      {error && (
        <p className="mt-3 rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 font-mono text-[11px] text-amber-100">
          {error}
        </p>
      )}

      <p className="mt-3 text-[10px] leading-relaxed text-on-surface-variant/90">{t("sys.sensors.compass.footnote")}</p>
    </div>
  );
}
