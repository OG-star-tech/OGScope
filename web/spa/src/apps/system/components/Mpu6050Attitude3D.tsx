import { useI18n } from "@shared/i18n/I18nProvider";

type Props = {
  rollDeg: number;
  pitchDeg: number;
  yawRateDps: number;
};

/**
 * MPU-6050：CSS 3D 板卡姿态（横滚/俯仰来自加速度计重力；ωz 为绕竖直轴角速度）。
 * CSS 3D board: roll/pitch from accel gravity; ωz is yaw-rate from gyro.
 */
export function Mpu6050Attitude3D(props: Props) {
  const { rollDeg, pitchDeg, yawRateDps } = props;
  const { t } = useI18n();

  return (
    <div className="mt-5 rounded-xl border border-teal-500/25 bg-black/25 p-4 ring-1 ring-teal-500/10">
      <p className="text-center text-[11px] font-semibold text-teal-200/95">{t("sys.sensors.gyro.att3dTitle")}</p>
      <p className="mx-auto mt-1 max-w-xl text-center text-[10px] leading-relaxed text-on-surface-variant">
        {t("sys.sensors.gyro.att3dDesc")}
      </p>

      <div className="mt-4 flex flex-col items-center gap-6 lg:flex-row lg:items-center lg:justify-between lg:gap-8">
        <div
          className="flex shrink-0 items-center justify-center py-2"
          style={{ perspective: "760px" }}
        >
          <div
            className="relative h-[152px] w-[200px] rounded-2xl border-2 border-teal-400/80 bg-gradient-to-br from-slate-600 via-slate-800 to-slate-950 shadow-[0_20px_50px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.08)] transition-transform duration-150 ease-out will-change-transform"
            style={{
              transformStyle: "preserve-3d",
              transform: `rotateX(${-pitchDeg}deg) rotateY(${rollDeg}deg)`,
            }}
          >
            <div className="pointer-events-none absolute inset-x-0 top-2 flex justify-center">
              <span className="rounded bg-black/35 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.2em] text-teal-100">
                TOP
              </span>
            </div>
            {/* +X 机头方向 / +X forward */}
            <div
              className="absolute bottom-5 left-1/2 h-2.5 w-[72px] -translate-x-1/2 rounded-sm bg-amber-400 shadow-md ring-1 ring-amber-200/40"
              title="+X"
            />
            {/* +Y 侧向 / +Y lateral */}
            <div
              className="absolute right-4 top-[42%] h-[52px] w-2 -translate-y-1/2 rounded-sm bg-sky-400/90 shadow-md ring-1 ring-sky-200/30"
              title="+Y"
            />
            <div className="absolute bottom-2 left-2 font-mono text-[9px] text-slate-400">MPU-6050</div>
          </div>
        </div>

        <div className="grid w-full max-w-md grid-cols-3 gap-3 font-mono text-[11px] lg:max-w-lg">
          <div className="rounded-lg border border-outline-variant/30 bg-surface-container/80 px-2 py-2 text-center">
            <p className="text-[9px] uppercase tracking-wider text-on-surface-variant">{t("sys.sensors.gyro.roll")}</p>
            <p className="mt-1 text-lg font-bold tabular-nums text-teal-200">{rollDeg.toFixed(1)}°</p>
          </div>
          <div className="rounded-lg border border-outline-variant/30 bg-surface-container/80 px-2 py-2 text-center">
            <p className="text-[9px] uppercase tracking-wider text-on-surface-variant">{t("sys.sensors.gyro.pitch")}</p>
            <p className="mt-1 text-lg font-bold tabular-nums text-teal-200">{pitchDeg.toFixed(1)}°</p>
          </div>
          <div className="rounded-lg border border-outline-variant/30 bg-surface-container/80 px-2 py-2 text-center">
            <p className="text-[9px] uppercase tracking-wider text-on-surface-variant">{t("sys.sensors.gyro.yawRate")}</p>
            <p className="mt-1 text-lg font-bold tabular-nums text-amber-200/95">{yawRateDps.toFixed(2)}</p>
            <p className="text-[9px] text-on-surface-variant">°/s</p>
          </div>
        </div>
      </div>
    </div>
  );
}
