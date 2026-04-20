import { useCallback, useState } from "react";
import { useI18n } from "@shared/i18n/I18nProvider";
import { requestDevDebugJson } from "@shared/transport/http";

type Axis = { x: number; y: number; z: number };

type GyroSampleResponse = {
  success?: boolean;
  gyro_dps?: Axis;
  gyro_raw?: Axis;
  error?: string;
  sample?: { error?: string };
};

function axisTable(title: string, v: Axis | null | undefined, unitHint: string) {
  if (!v) return null;
  return (
    <div>
      <p className="text-[11px] font-medium text-on-surface">
        {title}{" "}
        <span className="font-normal text-on-surface-variant">({unitHint})</span>
      </p>
      <table className="mt-1 w-full max-w-md border-collapse font-mono text-xs text-on-surface">
        <thead>
          <tr className="text-on-surface-variant">
            <th className="px-2 py-1 text-right">X</th>
            <th className="px-2 py-1 text-right">Y</th>
            <th className="px-2 py-1 text-right">Z</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="px-2 py-1 text-right tabular-nums">{v.x}</td>
            <td className="px-2 py-1 text-right tabular-nums">{v.y}</td>
            <td className="px-2 py-1 text-right tabular-nums">{v.z}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/**
 * MPU-6050 陀螺仪调试：读取角速度（依赖 /api/dev/debug/sensors/mpu6050/gyro-sample）。
 * MPU-6050 gyroscope debug: angular rate via gyro-sample API.
 */
export function GyroscopeMpu6050Panel(props: { bus: number; addr: number }) {
  const { bus, addr } = props;
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dps, setDps] = useState<Axis | null>(null);
  const [raw, setRaw] = useState<Axis | null>(null);

  const fetchSample = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ bus: String(bus), addr: String(addr) });
      const data = await requestDevDebugJson<GyroSampleResponse>(
        `/api/debug/sensors/mpu6050/gyro-sample?${qs.toString()}`,
      );
      if (!data.success) {
        setDps(null);
        setRaw(null);
        setError(data.sample?.error || data.error || t("sys.sensors.gyro.errUnknown"));
        return;
      }
      setDps(data.gyro_dps ?? null);
      setRaw(data.gyro_raw ?? null);
    } catch (e) {
      setDps(null);
      setRaw(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [addr, bus, t]);

  return (
    <div className="mt-6 rounded-lg border border-primary/25 bg-surface-container/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-on-surface">{t("sys.sensors.gyro.title")}</p>
          <p className="mt-0.5 text-[11px] text-on-surface-variant">{t("sys.sensors.gyro.subtitle")}</p>
        </div>
        <button
          type="button"
          disabled={loading}
          className="rounded-lg bg-secondary-container px-3 py-1.5 text-xs font-medium text-on-secondary-container hover:opacity-90 disabled:opacity-50"
          onClick={() => void fetchSample()}
        >
          {loading ? t("sys.sensors.gyro.loading") : t("sys.sensors.gyro.btn")}
        </button>
      </div>

      <div className="mt-3 space-y-4">
        {axisTable(t("sys.sensors.gyro.dps"), dps, t("sys.sensors.gyro.unitDps"))}
        {axisTable(t("sys.sensors.gyro.raw"), raw, t("sys.sensors.gyro.unitRaw"))}
      </div>

      {!dps && !error && !loading && (
        <p className="mt-2 text-[11px] text-on-surface-variant">{t("sys.sensors.gyro.hint")}</p>
      )}

      {error && (
        <p className="mt-3 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 font-mono text-[11px] text-amber-100">
          {error}
        </p>
      )}
    </div>
  );
}
