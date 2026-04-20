import { useCallback, useState } from "react";
import { GyroscopeMpu6050Panel } from "../components/GyroscopeMpu6050Panel";
import { useI18n } from "@shared/i18n/I18nProvider";
import { requestDevDebugJson } from "@shared/transport/http";

type JsonRecord = Record<string, unknown>;

function formatJson(data: unknown): string {
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

export function SensorsPage() {
  const { t } = useI18n();
  const [bus, setBus] = useState(1);
  const [addr, setAddr] = useState(12);
  const [runI2cdetect, setRunI2cdetect] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<JsonRecord | null>(null);

  const [mpuBus, setMpuBus] = useState(1);
  const [mpuAddr, setMpuAddr] = useState(104);
  const [mpuI2cdetect, setMpuI2cdetect] = useState(true);
  const [mpuLoading, setMpuLoading] = useState(false);
  const [mpuError, setMpuError] = useState<string | null>(null);
  const [mpuResult, setMpuResult] = useState<JsonRecord | null>(null);

  const runSelftest = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({
        bus: String(bus),
        addr: String(addr),
        i2cdetect: runI2cdetect ? "true" : "false",
      });
      const data = await requestDevDebugJson<JsonRecord>(
        `/api/debug/sensors/magnetometer/selftest?${qs.toString()}`,
      );
      setResult(data);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [addr, bus, runI2cdetect]);

  const runProbeBuses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ addr: String(addr) });
      const data = await requestDevDebugJson<JsonRecord>(
        `/api/debug/sensors/magnetometer/probe-buses?${qs.toString()}`,
      );
      setResult(data);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [addr]);

  const runMpuSelftest = useCallback(async () => {
    setMpuLoading(true);
    setMpuError(null);
    try {
      const qs = new URLSearchParams({
        bus: String(mpuBus),
        addr: String(mpuAddr),
        i2cdetect: mpuI2cdetect ? "true" : "false",
      });
      const data = await requestDevDebugJson<JsonRecord>(
        `/api/debug/sensors/mpu6050/selftest?${qs.toString()}`,
      );
      setMpuResult(data);
    } catch (e) {
      setMpuResult(null);
      setMpuError(e instanceof Error ? e.message : String(e));
    } finally {
      setMpuLoading(false);
    }
  }, [mpuAddr, mpuBus, mpuI2cdetect]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <div className="text-[10px] uppercase tracking-[0.14em] text-on-surface-variant">
          {t("sys.placeholder.breadcrumb")}
        </div>
        <h2 className="mt-1 font-headline text-3xl font-black tracking-tight">{t("sys.sensors.title")}</h2>
        <p className="text-sm text-on-surface-variant">{t("sys.sensors.desc")}</p>
      </header>

      <section className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
        <p className="text-xs font-medium text-on-surface">{t("sys.sensors.mag.section")}</p>
        <p className="mt-1 text-[11px] text-on-surface-variant">{t("sys.sensors.mag.note")}</p>

        <div className="mt-4 flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-[11px] text-on-surface-variant">
            {t("sys.sensors.mag.bus")}
            <input
              type="number"
              min={0}
              max={32}
              className="w-24 rounded border border-outline-variant/40 bg-surface-container px-2 py-1 font-mono text-sm text-on-surface"
              value={bus}
              onChange={(e) => setBus(Number(e.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-on-surface-variant">
            {t("sys.sensors.mag.addr")}
            <input
              type="number"
              min={1}
              max={127}
              className="w-24 rounded border border-outline-variant/40 bg-surface-container px-2 py-1 font-mono text-sm text-on-surface"
              value={addr}
              onChange={(e) => setAddr(Number(e.target.value))}
            />
          </label>
          <label className="flex items-center gap-2 text-[11px] text-on-surface-variant">
            <input
              type="checkbox"
              checked={runI2cdetect}
              onChange={(e) => setRunI2cdetect(e.target.checked)}
            />
            {t("sys.sensors.mag.i2cdetect")}
          </label>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
            onClick={() => void runSelftest()}
          >
            {loading ? t("sys.sensors.mag.running") : t("sys.sensors.mag.btnSelftest")}
          </button>
          <button
            type="button"
            disabled={loading}
            className="rounded-lg border border-outline-variant/40 px-4 py-2 text-sm text-on-surface hover:bg-surface-container/80 disabled:opacity-50"
            onClick={() => void runProbeBuses()}
          >
            {t("sys.sensors.mag.btnProbe")}
          </button>
        </div>

        {error && (
          <p className="mt-3 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 font-mono text-xs text-red-200">
            {error}
          </p>
        )}

        {result && (
          <pre className="mt-4 max-h-[480px] overflow-auto rounded border border-outline-variant/30 bg-surface-container/80 p-3 font-mono text-[11px] leading-relaxed text-on-surface">
            {formatJson(result)}
          </pre>
        )}
      </section>

      <section className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
        <p className="text-xs font-medium text-on-surface">{t("sys.sensors.mpu.section")}</p>
        <p className="mt-1 text-[11px] text-on-surface-variant">{t("sys.sensors.mpu.note")}</p>

        <div className="mt-4 flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-[11px] text-on-surface-variant">
            {t("sys.sensors.mag.bus")}
            <input
              type="number"
              min={0}
              max={32}
              className="w-24 rounded border border-outline-variant/40 bg-surface-container px-2 py-1 font-mono text-sm text-on-surface"
              value={mpuBus}
              onChange={(e) => setMpuBus(Number(e.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-on-surface-variant">
            {t("sys.sensors.mpu.addr")}
            <input
              type="number"
              min={1}
              max={127}
              className="w-24 rounded border border-outline-variant/40 bg-surface-container px-2 py-1 font-mono text-sm text-on-surface"
              value={mpuAddr}
              onChange={(e) => setMpuAddr(Number(e.target.value))}
            />
          </label>
          <label className="flex items-center gap-2 text-[11px] text-on-surface-variant">
            <input
              type="checkbox"
              checked={mpuI2cdetect}
              onChange={(e) => setMpuI2cdetect(e.target.checked)}
            />
            {t("sys.sensors.mag.i2cdetect")}
          </label>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={mpuLoading}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
            onClick={() => void runMpuSelftest()}
          >
            {mpuLoading ? t("sys.sensors.mpu.running") : t("sys.sensors.mpu.btnSelftest")}
          </button>
        </div>

        {mpuError && (
          <p className="mt-3 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 font-mono text-xs text-red-200">
            {mpuError}
          </p>
        )}

        {mpuResult && (
          <pre className="mt-4 max-h-[480px] overflow-auto rounded border border-outline-variant/30 bg-surface-container/80 p-3 font-mono text-[11px] leading-relaxed text-on-surface">
            {formatJson(mpuResult)}
          </pre>
        )}

        <GyroscopeMpu6050Panel bus={mpuBus} addr={mpuAddr} />
      </section>
    </div>
  );
}
