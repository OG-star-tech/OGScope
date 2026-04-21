import { useCallback, useEffect, useRef, useState } from "react";
import { Mpu6050Attitude3D } from "./Mpu6050Attitude3D";
import { useI18n } from "@shared/i18n/I18nProvider";
import { requestDevDebugJson } from "@shared/transport/http";

type Axis = { x: number; y: number; z: number };

type ImuSampleResponse = {
  success?: boolean;
  gyro_dps?: Axis;
  gyro_raw?: Axis;
  tilt_deg?: { roll: number; pitch: number };
  yaw_rate_dps?: number;
  accel_g?: Axis;
  error?: string;
  sample?: { error?: string };
};

const MAX_DPS = 250;

function SignedBar(props: { label: string; value: number; maxAbs: number; unit: string }) {
  const { label, value, maxAbs, unit } = props;
  const t = Math.max(-1, Math.min(1, value / maxAbs));
  const leftPct = t >= 0 ? 50 : 50 + t * 50;
  const widthPct = Math.abs(t) * 50;
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-medium text-on-surface">{label}</span>
        <span className="font-mono text-xs tabular-nums text-sky-100">
          {value.toFixed(2)}
          <span className="text-on-surface-variant"> {unit}</span>
        </span>
      </div>
      <div className="relative h-5 w-full overflow-hidden rounded-md bg-slate-900/80 ring-1 ring-slate-600/50">
        <div className="absolute left-1/2 top-0 z-10 h-full w-px -translate-x-px bg-slate-500/90" />
        <div
          className="absolute top-1 h-3 rounded-sm bg-gradient-to-r from-emerald-600 to-sky-500 shadow-sm"
          style={{
            left: `${leftPct}%`,
            width: `${Math.max(widthPct, t === 0 ? 0 : 0.8)}%`,
          }}
        />
      </div>
    </div>
  );
}

/**
 * MPU-6050：IMU 采样（陀螺仪 + 加速度计推算姿态）与 3D 板卡示意。
 * MPU-6050: IMU sample (gyro + accel-derived attitude) and 3D board hint.
 */
export function GyroscopeMpu6050Panel(props: { bus: number; addr: number }) {
  const { bus, addr } = props;
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dps, setDps] = useState<Axis | null>(null);
  const [raw, setRaw] = useState<Axis | null>(null);
  const [tilt, setTilt] = useState<{ roll: number; pitch: number } | null>(null);
  const [yawRate, setYawRate] = useState<number | null>(null);
  const [accelG, setAccelG] = useState<Axis | null>(null);
  const [live, setLive] = useState(false);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSample = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ bus: String(bus), addr: String(addr) });
      const data = await requestDevDebugJson<ImuSampleResponse>(
        `/api/debug/sensors/mpu6050/imu-sample?${qs.toString()}`,
      );
      if (!data.success) {
        setDps(null);
        setRaw(null);
        setTilt(null);
        setYawRate(null);
        setAccelG(null);
        setError(data.sample?.error || data.error || t("sys.sensors.gyro.errUnknown"));
        return;
      }
      setDps(data.gyro_dps ?? null);
      setRaw(data.gyro_raw ?? null);
      setTilt(data.tilt_deg ?? null);
      setYawRate(data.yaw_rate_dps ?? null);
      setAccelG(data.accel_g ?? null);
    } catch (e) {
      setDps(null);
      setRaw(null);
      setTilt(null);
      setYawRate(null);
      setAccelG(null);
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
    tickRef.current = setInterval(() => void fetchSample(), 500);
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, [live, fetchSample]);

  const showAttitude =
    tilt != null && yawRate != null && Number.isFinite(tilt.roll) && Number.isFinite(tilt.pitch);

  return (
    <div className="mt-6 rounded-xl border border-emerald-600/35 bg-gradient-to-br from-slate-900/40 to-surface-container/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-on-surface">{t("sys.sensors.gyro.title")}</p>
          <p className="mt-1 max-w-xl text-[11px] leading-snug text-on-surface-variant">{t("sys.sensors.gyro.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-on-surface-variant">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
            {t("sys.sensors.gyro.live")}
          </label>
          <button
            type="button"
            disabled={loading}
            className="rounded-lg bg-emerald-800/90 px-3 py-1.5 text-xs font-medium text-emerald-50 hover:bg-emerald-700 disabled:opacity-50"
            onClick={() => void fetchSample()}
          >
            {loading ? t("sys.sensors.gyro.loading") : t("sys.sensors.gyro.btn")}
          </button>
        </div>
      </div>

      {showAttitude && (
        <Mpu6050Attitude3D rollDeg={tilt.roll} pitchDeg={tilt.pitch} yawRateDps={yawRate} />
      )}

      {dps && (
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-emerald-500/20 bg-black/20 px-3 py-3 text-center md:col-span-1">
            <p className="text-[10px] text-on-surface-variant">ωx</p>
            <p className="font-mono text-3xl font-bold tabular-nums text-emerald-200">{dps.x.toFixed(2)}</p>
            <p className="text-[10px] text-on-surface-variant">°/s</p>
          </div>
          <div className="rounded-lg border border-emerald-500/20 bg-black/20 px-3 py-3 text-center md:col-span-1">
            <p className="text-[10px] text-on-surface-variant">ωy</p>
            <p className="font-mono text-3xl font-bold tabular-nums text-emerald-200">{dps.y.toFixed(2)}</p>
            <p className="text-[10px] text-on-surface-variant">°/s</p>
          </div>
          <div className="rounded-lg border border-emerald-500/20 bg-black/20 px-3 py-3 text-center md:col-span-1">
            <p className="text-[10px] text-on-surface-variant">ωz</p>
            <p className="font-mono text-3xl font-bold tabular-nums text-emerald-200">{dps.z.toFixed(2)}</p>
            <p className="text-[10px] text-on-surface-variant">°/s</p>
          </div>
        </div>
      )}

      {dps && (
        <div className="mt-5 space-y-4">
          <p className="text-[10px] font-medium uppercase tracking-wider text-on-surface-variant">
            {t("sys.sensors.gyro.barsTitle")}
          </p>
          <SignedBar label="X" value={dps.x} maxAbs={MAX_DPS} unit="°/s" />
          <SignedBar label="Y" value={dps.y} maxAbs={MAX_DPS} unit="°/s" />
          <SignedBar label="Z" value={dps.z} maxAbs={MAX_DPS} unit="°/s" />
        </div>
      )}

      {accelG && (
        <p className="mt-3 text-center font-mono text-[10px] text-on-surface-variant">
          g — X:{accelG.x.toFixed(3)} Y:{accelG.y.toFixed(3)} Z:{accelG.z.toFixed(3)}
        </p>
      )}

      {raw && (
        <div className="mt-4 rounded border border-outline-variant/25 bg-surface-container/50 px-3 py-2">
          <p className="text-[10px] text-on-surface-variant">{t("sys.sensors.gyro.rawBlock")}</p>
          <p className="mt-1 font-mono text-[11px] tabular-nums text-on-surface">
            raw X={raw.x} · Y={raw.y} · Z={raw.z}
          </p>
        </div>
      )}

      {!dps && !error && !loading && (
        <p className="mt-4 text-[11px] text-on-surface-variant">{t("sys.sensors.gyro.hint")}</p>
      )}

      {error && (
        <p className="mt-3 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 font-mono text-[11px] text-amber-100">
          {error}
        </p>
      )}
    </div>
  );
}
