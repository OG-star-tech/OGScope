import { useCallback, useEffect, useState } from "react";
import {
  fetchHardwarePlaneStatus,
  postHardwarePlaneCommand,
  type HardwarePlaneStatusResponse,
} from "@shared/systemApi";
import { useI18n } from "@shared/i18n/I18nProvider";

type DisplayStatus = {
  enabled?: boolean;
  type?: string;
  width?: number;
  height?: number;
  dc_pin?: number;
  spidev_present?: boolean;
  driver_open?: boolean;
  last_error?: string | null;
  last_pattern?: string | null;
};

function pickDisplay(st: HardwarePlaneStatusResponse | null): DisplayStatus | null {
  const hmi = st?.data?.services?.hmi as Record<string, unknown> | undefined;
  if (!hmi || typeof hmi !== "object") return null;
  const d = hmi.display;
  if (!d || typeof d !== "object") return null;
  return d as DisplayStatus;
}

function formatJson(data: unknown): string {
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

export function HmiPage() {
  const { t } = useI18n();
  const [plane, setPlane] = useState<HardwarePlaneStatusResponse | null>(null);
  const [planeErr, setPlaneErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastCmd, setLastCmd] = useState<unknown>(null);
  const [cmdErr, setCmdErr] = useState<string | null>(null);
  const [fillR, setFillR] = useState(40);
  const [fillG, setFillG] = useState(80);
  const [fillB, setFillB] = useState(200);

  const refresh = useCallback(async () => {
    try {
      setPlaneErr(null);
      const s = await fetchHardwarePlaneStatus();
      setPlane(s);
    } catch (e) {
      setPlane(null);
      setPlaneErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const runCmd = useCallback(
    async (action: string, payload: Record<string, unknown> = {}) => {
      setBusy(true);
      setCmdErr(null);
      try {
        const raw = await postHardwarePlaneCommand({
          target: "hmi",
          action,
          payload,
          timeout_ms: 8000,
        });
        setLastCmd(raw);
        if (!raw.success) {
          const msg = (raw.error as { message?: string } | undefined)?.message ?? "RPC failed";
          setCmdErr(msg);
          return;
        }
        const data = raw.data as { result?: { accepted?: boolean; message?: string } } | undefined;
        const res = data?.result;
        if (res && res.accepted === false && res.message) {
          setCmdErr(res.message);
        } else {
          setCmdErr(null);
        }
        await refresh();
      } catch (e) {
        setLastCmd(null);
        setCmdErr(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const disp = pickDisplay(plane);
  const hmiRoot = plane?.data?.services?.hmi as Record<string, unknown> | undefined;
  const screenOn = typeof hmiRoot?.screen_on === "boolean" ? hmiRoot.screen_on : undefined;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <div className="text-[10px] uppercase tracking-[0.14em] text-on-surface-variant">
          {t("sys.placeholder.breadcrumb")}
        </div>
        <h2 className="mt-1 font-headline text-3xl font-black tracking-tight">{t("sys.hmi.title")}</h2>
        <p className="text-sm text-on-surface-variant">{t("sys.hmi.desc")}</p>
      </header>

      <section className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs font-medium text-on-surface">{t("sys.hmi.status.section")}</p>
          <button
            type="button"
            className="rounded-lg border border-outline-variant/40 bg-surface-container px-3 py-1.5 text-xs font-medium text-on-surface hover:bg-surface-container-high"
            onClick={() => void refresh()}
            disabled={busy}
          >
            {t("sys.hmi.status.refresh")}
          </button>
        </div>
        {planeErr ? (
          <p className="mt-2 text-sm text-error">{planeErr}</p>
        ) : (
          <dl className="mt-3 grid gap-2 font-mono text-[11px] text-on-surface-variant sm:grid-cols-2">
            <div>
              <dt className="text-on-surface-variant">{t("sys.hmi.status.displayEnabled")}</dt>
              <dd className="text-on-surface">{disp?.enabled === true ? "true" : "false"}</dd>
            </div>
            <div>
              <dt>{t("sys.hmi.status.spidev")}</dt>
              <dd className={disp?.spidev_present ? "text-primary" : "text-error"}>
                {disp?.spidev_present ? t("sys.hmi.status.yes") : t("sys.hmi.status.no")}
              </dd>
            </div>
            <div>
              <dt>{t("sys.hmi.status.resolution")}</dt>
              <dd>
                {disp?.width ?? "—"} × {disp?.height ?? "—"} · DC GPIO {disp?.dc_pin ?? "—"}
              </dd>
            </div>
            <div>
              <dt>{t("sys.hmi.status.driver")}</dt>
              <dd>{disp?.driver_open ? t("sys.hmi.status.open") : t("sys.hmi.status.closed")}</dd>
            </div>
            <div>
              <dt>{t("sys.hmi.status.screenOutput")}</dt>
              <dd>{screenOn === undefined ? "—" : screenOn ? t("sys.hmi.status.on") : t("sys.hmi.status.off")}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt>{t("sys.hmi.status.lastPattern")}</dt>
              <dd>{disp?.last_pattern ?? "—"}</dd>
            </div>
            {disp?.last_error ? (
              <div className="sm:col-span-2">
                <dt>{t("sys.hmi.status.lastError")}</dt>
                <dd className="text-error">{disp.last_error}</dd>
              </div>
            ) : null}
          </dl>
        )}
      </section>

      <section className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
        <p className="text-xs font-medium text-on-surface">{t("sys.hmi.actions.section")}</p>
        <p className="mt-1 text-[11px] text-on-surface-variant">{t("sys.hmi.actions.hint")}</p>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-on-primary hover:opacity-90 disabled:opacity-50"
            disabled={busy}
            onClick={() => void runCmd("display.test_pattern", { pattern: "smoke" })}
          >
            {t("sys.hmi.actions.smoke")}
          </button>
          <button
            type="button"
            className="rounded-lg border border-outline-variant/40 bg-surface-container px-3 py-2 text-xs font-medium text-on-surface hover:bg-surface-container-high disabled:opacity-50"
            disabled={busy}
            onClick={() => void runCmd("display.test_pattern", { pattern: "colorbars" })}
          >
            {t("sys.hmi.actions.colorbars")}
          </button>
        </div>

        <div className="mt-6 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[11px] text-on-surface-variant">
            R
            <input
              type="number"
              min={0}
              max={255}
              className="w-20 rounded border border-outline-variant/40 bg-surface-container px-2 py-1 font-mono text-sm text-on-surface"
              value={fillR}
              onChange={(e) => setFillR(Number(e.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-on-surface-variant">
            G
            <input
              type="number"
              min={0}
              max={255}
              className="w-20 rounded border border-outline-variant/40 bg-surface-container px-2 py-1 font-mono text-sm text-on-surface"
              value={fillG}
              onChange={(e) => setFillG(Number(e.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-on-surface-variant">
            B
            <input
              type="number"
              min={0}
              max={255}
              className="w-20 rounded border border-outline-variant/40 bg-surface-container px-2 py-1 font-mono text-sm text-on-surface"
              value={fillB}
              onChange={(e) => setFillB(Number(e.target.value))}
            />
          </label>
          <button
            type="button"
            className="rounded-lg border border-outline-variant/40 bg-surface-container px-3 py-2 text-xs font-medium text-on-surface hover:bg-surface-container-high disabled:opacity-50"
            disabled={busy}
            onClick={() =>
              void runCmd("display.test_pattern", {
                pattern: "fill",
                r: fillR,
                g: fillG,
                b: fillB,
              })
            }
          >
            {t("sys.hmi.actions.fill")}
          </button>
        </div>

        <div className="mt-6 flex flex-wrap gap-2 border-t border-outline-variant/20 pt-4">
          <button
            type="button"
            className="rounded-lg border border-outline-variant/40 px-3 py-2 text-xs text-on-surface hover:bg-surface-container-high disabled:opacity-50"
            disabled={busy}
            onClick={() => void runCmd("screen.set", { on: true })}
          >
            {t("sys.hmi.actions.screenOn")}
          </button>
          <button
            type="button"
            className="rounded-lg border border-outline-variant/40 px-3 py-2 text-xs text-on-surface hover:bg-surface-container-high disabled:opacity-50"
            disabled={busy}
            onClick={() => void runCmd("screen.set", { on: false })}
          >
            {t("sys.hmi.actions.screenOff")}
          </button>
          <button
            type="button"
            className="rounded-lg border border-outline-variant/40 px-3 py-2 text-xs text-on-surface hover:bg-surface-container-high disabled:opacity-50"
            disabled={busy}
            onClick={() => void runCmd("display.release")}
          >
            {t("sys.hmi.actions.release")}
          </button>
        </div>

        {cmdErr ? <p className="mt-3 text-sm text-error">{cmdErr}</p> : null}

        <details className="mt-4">
          <summary className="cursor-pointer text-[11px] text-on-surface-variant">
            {t("sys.hmi.rawJson")}
          </summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded border border-outline-variant/30 bg-surface-container p-2 font-mono text-[10px] text-on-surface">
            {lastCmd ? formatJson(lastCmd) : "—"}
          </pre>
        </details>
      </section>
    </div>
  );
}
