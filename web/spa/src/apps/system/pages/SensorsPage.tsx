import { useCallback, useEffect, useMemo, useState } from "react";
import { GyroscopeMpu6050Panel } from "../components/GyroscopeMpu6050Panel";
import { MagnetometerCompassPanel } from "../components/MagnetometerCompassPanel";
import { useI18n } from "@shared/i18n/I18nProvider";
import { requestDevDebugJson } from "@shared/transport/http";

type JsonRecord = Record<string, unknown>;
type MagCalStatus = {
  success?: boolean;
  mode?: string;
  samples?: number;
  span_xyz?: { x?: number; y?: number; z?: number };
  locked?: {
    axes_pair?: string;
    sign?: number;
    samples?: number;
  } | null;
};

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
  const [magCalStatus, setMagCalStatus] = useState<MagCalStatus | null>(null);
  const [magCalHint, setMagCalHint] = useState<string | null>(null);

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

  const runMagCalStart = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ bus: String(bus), addr: String(addr) });
      const data = await requestDevDebugJson<JsonRecord>(
        `/api/debug/sensors/magnetometer/calibration/start?${qs.toString()}`,
        { method: "POST" },
      );
      setResult(data);
      setMagCalHint("已开始方向校准，请缓慢旋转设备 5-15 秒。");
      const status = await requestDevDebugJson<MagCalStatus>(
        `/api/debug/sensors/magnetometer/calibration/status?${qs.toString()}`,
      );
      setMagCalStatus(status);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [addr, bus]);

  const runMagCalCommit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ bus: String(bus), addr: String(addr) });
      const data = await requestDevDebugJson<JsonRecord>(
        `/api/debug/sensors/magnetometer/calibration/commit?${qs.toString()}`,
        { method: "POST" },
      );
      setResult(data);
      setMagCalHint("已保存并锁定方向校准。");
      const status = await requestDevDebugJson<MagCalStatus>(
        `/api/debug/sensors/magnetometer/calibration/status?${qs.toString()}`,
      );
      setMagCalStatus(status);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [addr, bus]);

  const runMagCalReset = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ bus: String(bus), addr: String(addr) });
      const data = await requestDevDebugJson<JsonRecord>(
        `/api/debug/sensors/magnetometer/calibration/reset?${qs.toString()}`,
        { method: "POST" },
      );
      setResult(data);
      setMagCalHint("已重置到自动模式。");
      const status = await requestDevDebugJson<MagCalStatus>(
        `/api/debug/sensors/magnetometer/calibration/status?${qs.toString()}`,
      );
      setMagCalStatus(status);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [addr, bus]);

  const runMagCalStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ bus: String(bus), addr: String(addr) });
      const data = await requestDevDebugJson<JsonRecord>(
        `/api/debug/sensors/magnetometer/calibration/status?${qs.toString()}`,
      );
      setResult(data);
      setMagCalStatus(data as MagCalStatus);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [addr, bus]);

  useEffect(() => {
    const qs = new URLSearchParams({ bus: String(bus), addr: String(addr) });
    void requestDevDebugJson<MagCalStatus>(
      `/api/debug/sensors/magnetometer/calibration/status?${qs.toString()}`,
    )
      .then((s) => setMagCalStatus(s))
      .catch(() => undefined);
  }, [addr, bus]);

  useEffect(() => {
    if (magCalStatus?.mode !== "recording") return;
    const t = setInterval(() => {
      const qs = new URLSearchParams({ bus: String(bus), addr: String(addr) });
      void requestDevDebugJson<MagCalStatus>(
        `/api/debug/sensors/magnetometer/calibration/status?${qs.toString()}`,
      )
        .then((s) => setMagCalStatus(s))
        .catch(() => undefined);
    }, 900);
    return () => clearInterval(t);
  }, [magCalStatus?.mode, bus, addr]);

  const calModeLabel = useMemo(() => {
    const m = magCalStatus?.mode ?? "auto";
    if (m === "recording") return t("sys.sensors.mag.calModeRecording");
    if (m === "locked") return t("sys.sensors.mag.calModeLocked");
    return t("sys.sensors.mag.calModeAuto");
  }, [magCalStatus?.mode, t]);

  const calSamples = Number(magCalStatus?.samples ?? 0);
  const calCanCommit = magCalStatus?.mode === "recording" && calSamples >= 10;

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

        <MagnetometerCompassPanel bus={bus} addr={addr} />

        <div className="mt-6 flex flex-wrap gap-2">
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

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading || magCalStatus?.mode === "recording"}
            className="rounded-lg border border-amber-400/40 px-3 py-1.5 text-xs text-on-surface hover:bg-amber-500/10 disabled:opacity-50"
            onClick={() => void runMagCalStart()}
          >
            {t("sys.sensors.mag.btnCalStart")}
          </button>
          <button
            type="button"
            disabled={loading || !calCanCommit}
            className="rounded-lg border border-emerald-400/40 px-3 py-1.5 text-xs text-on-surface hover:bg-emerald-500/10 disabled:opacity-50"
            onClick={() => void runMagCalCommit()}
          >
            {t("sys.sensors.mag.btnCalCommit")}
          </button>
          <button
            type="button"
            disabled={loading}
            className="rounded-lg border border-rose-400/40 px-3 py-1.5 text-xs text-on-surface hover:bg-rose-500/10 disabled:opacity-50"
            onClick={() => void runMagCalReset()}
          >
            {t("sys.sensors.mag.btnCalReset")}
          </button>
          <button
            type="button"
            disabled={loading}
            className="rounded-lg border border-outline-variant/40 px-3 py-1.5 text-xs text-on-surface hover:bg-surface-container/80 disabled:opacity-50"
            onClick={() => void runMagCalStatus()}
          >
            {t("sys.sensors.mag.btnCalStatus")}
          </button>
        </div>

        <div className="mt-3 rounded-lg border border-outline-variant/30 bg-surface-container/60 px-3 py-2 text-[11px] text-on-surface">
          <p className="font-medium">
            {t("sys.sensors.mag.calStatusPrefix")} {calModeLabel}
          </p>
          <p className="mt-1 text-on-surface-variant">
            {t("sys.sensors.mag.calSamplesPrefix")} {calSamples}
            {magCalStatus?.mode === "recording" ? ` / 10+` : ""}
          </p>
          {magCalStatus?.span_xyz && (
            <p className="mt-1 font-mono text-[10px] text-on-surface-variant">
              span xyz: {Number(magCalStatus.span_xyz.x ?? 0).toFixed(1)} /{" "}
              {Number(magCalStatus.span_xyz.y ?? 0).toFixed(1)} /{" "}
              {Number(magCalStatus.span_xyz.z ?? 0).toFixed(1)}
            </p>
          )}
          {magCalStatus?.mode === "recording" && (
            <p className="mt-1 text-amber-200">{t("sys.sensors.mag.calRecordingHint")}</p>
          )}
          {magCalStatus?.mode === "locked" && magCalStatus.locked && (
            <p className="mt-1 text-emerald-200">
              {t("sys.sensors.mag.calLockedHint")} axes={String(magCalStatus.locked.axes_pair ?? "xy")}
            </p>
          )}
          {magCalHint && <p className="mt-1 text-sky-200">{magCalHint}</p>}
        </div>

        {error && (
          <p className="mt-3 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 font-mono text-xs text-red-200">
            {error}
          </p>
        )}

        {result && (
          <details className="mt-4 rounded-lg border border-outline-variant/30 bg-surface-container/50">
            <summary className="cursor-pointer px-3 py-2 text-[11px] text-on-surface-variant">
              {t("sys.sensors.jsonToggle")}
            </summary>
            <pre className="max-h-[320px] overflow-auto border-t border-outline-variant/20 p-3 font-mono text-[11px] leading-relaxed text-on-surface">
              {formatJson(result)}
            </pre>
          </details>
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

        <GyroscopeMpu6050Panel bus={mpuBus} addr={mpuAddr} />

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
          <details className="mt-4 rounded-lg border border-outline-variant/30 bg-surface-container/50">
            <summary className="cursor-pointer px-3 py-2 text-[11px] text-on-surface-variant">
              {t("sys.sensors.jsonToggle")}
            </summary>
            <pre className="max-h-[320px] overflow-auto border-t border-outline-variant/20 p-3 font-mono text-[11px] leading-relaxed text-on-surface">
              {formatJson(mpuResult)}
            </pre>
          </details>
        )}
      </section>
    </div>
  );
}
