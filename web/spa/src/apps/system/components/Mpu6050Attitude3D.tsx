import { useI18n } from "@shared/i18n/I18nProvider";

type Props = {
  rollDeg: number;
  pitchDeg: number;
  yawRateDps: number;
};

const AXIS_LEN = 62;
const AXIS_THICK = 4;

/**
 * MPU-6050：CSS 3D 板卡 + 机体系 XYZ 三轴（横滚/俯仰来自加速度计；ωz 为绕竖直轴角速度）。
 * CSS 3D board + body XYZ triad; roll/pitch from accel; ωz = yaw rate.
 */
export function Mpu6050Attitude3D(props: Props) {
  const { rollDeg, pitchDeg, yawRateDps } = props;
  const { t } = useI18n();

  const bodyTransform = `rotateX(${-pitchDeg}deg) rotateY(${rollDeg}deg)`;

  return (
    <div className="mt-5 rounded-xl border border-teal-500/25 bg-black/25 p-4 ring-1 ring-teal-500/10">
      <p className="text-center text-[11px] font-semibold text-teal-200/95">{t("sys.sensors.gyro.att3dTitle")}</p>
      <p className="mx-auto mt-1 max-w-xl text-center text-[10px] leading-relaxed text-on-surface-variant">
        {t("sys.sensors.gyro.att3dDesc")}
      </p>

      <div className="mt-4 flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between xl:gap-8">
        {/* 主 3D：板卡与机体系三轴共转 */}
        <div className="flex min-w-0 flex-1 flex-col items-center gap-4">
          <div className="flex shrink-0 items-center justify-center py-2" style={{ perspective: "820px" }}>
            <div
              className="relative h-[188px] w-[220px]"
              style={{ transformStyle: "preserve-3d", transform: bodyTransform }}
            >
              {/* 半透明板面，便于看到轴与板法向关系 */}
              <div
                className="absolute left-[10px] top-[18px] h-[152px] w-[200px] rounded-2xl border-2 border-teal-400/75 bg-gradient-to-br from-slate-600/90 via-slate-800/95 to-slate-950 shadow-[0_20px_50px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.08)] transition-transform duration-150 ease-out"
                style={{ transformStyle: "preserve-3d" }}
              >
                <div className="pointer-events-none absolute inset-x-0 top-2 flex justify-center">
                  <span className="rounded bg-black/35 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.2em] text-teal-100">
                    TOP
                  </span>
                </div>
                <div className="absolute bottom-2 left-2 font-mono text-[9px] text-slate-400">MPU-6050</div>
              </div>

              {/* 机体系原点：三轴交叉（+X 前向、+Y 侧向、+Z 法向） */}
              <div
                className="pointer-events-none absolute left-[110px] top-[94px] h-0 w-0"
                style={{ transformStyle: "preserve-3d" }}
              >
                <div
                  className="absolute rounded-full bg-white/90 shadow-[0_0_6px_rgba(255,255,255,0.6)]"
                  style={{
                    width: 7,
                    height: 7,
                    left: -3.5,
                    top: -3.5,
                    transform: "translateZ(0.5px)",
                  }}
                />
                {/* +X（板内，琥珀） */}
                <div
                  className="absolute bg-amber-400 shadow-md ring-1 ring-amber-200/35"
                  style={{
                    width: AXIS_LEN,
                    height: AXIS_THICK,
                    left: 0,
                    top: -AXIS_THICK / 2,
                    transformOrigin: "0 50%",
                  }}
                />
                <span
                  className="absolute whitespace-nowrap font-mono text-[10px] font-bold text-amber-200"
                  style={{ left: AXIS_LEN + 4, top: -8 }}
                >
                  {t("sys.sensors.gyro.axisXLabel")}
                </span>
                {/* +Y（板内，天蓝） */}
                <div
                  className="absolute bg-sky-400 shadow-md ring-1 ring-sky-200/30"
                  style={{
                    width: AXIS_LEN,
                    height: AXIS_THICK,
                    left: 0,
                    top: -AXIS_THICK / 2,
                    transformOrigin: "0 50%",
                    transform: "rotateZ(90deg)",
                  }}
                />
                <span
                  className="absolute whitespace-nowrap font-mono text-[10px] font-bold text-sky-200"
                  style={{ left: -6, top: -AXIS_LEN - 16 }}
                >
                  {t("sys.sensors.gyro.axisYLabel")}
                </span>
                {/* +Z（垂直板面，朝观察者一侧；rotateY(-90°) 使 +X 弯向 +Z） */}
                <div
                  className="absolute bg-violet-400 shadow-md ring-1 ring-violet-200/35"
                  style={{
                    width: AXIS_LEN,
                    height: AXIS_THICK,
                    left: 0,
                    top: -AXIS_THICK / 2,
                    transformOrigin: "0 50%",
                    transform: "rotateY(-90deg)",
                  }}
                />
                <span
                  className="absolute whitespace-nowrap font-mono text-[10px] font-bold text-violet-200"
                  style={{ left: AXIS_LEN * 0.35, top: -AXIS_LEN * 0.45, transform: "translateZ(28px)" }}
                >
                  {t("sys.sensors.gyro.axisZLabel")}
                </span>

                {/* 负向短划：形成“交叉”感，便于对齐三轴 */}
                <div
                  className="absolute bg-amber-900/55"
                  style={{
                    width: AXIS_LEN * 0.45,
                    height: 2,
                    left: -AXIS_LEN * 0.45,
                    top: -1,
                    transformOrigin: "100% 50%",
                  }}
                />
                <div
                  className="absolute bg-sky-900/50"
                  style={{
                    width: AXIS_LEN * 0.45,
                    height: 2,
                    left: 0,
                    top: -1,
                    transformOrigin: "0 50%",
                    transform: `rotateZ(90deg) translateX(${-AXIS_LEN * 0.45}px)`,
                  }}
                />
                <div
                  className="absolute bg-violet-900/45"
                  style={{
                    width: AXIS_LEN * 0.4,
                    height: 2,
                    left: 0,
                    top: -1,
                    transformOrigin: "0 50%",
                    transform: `rotateY(-90deg) translateX(${-AXIS_LEN * 0.4}px)`,
                  }}
                />
              </div>
            </div>
          </div>

          <p className="max-w-md text-center text-[10px] leading-snug text-on-surface-variant">{t("sys.sensors.gyro.att3dBodyAxes")}</p>
        </div>

        {/* 静态参考：世界系正交交叉（不随姿态转），帮助辨认 XYZ 空间关系 */}
        <div className="flex w-full max-w-[220px] shrink-0 flex-col items-center gap-2 self-center xl:self-start">
          <p className="text-center text-[10px] font-medium text-on-surface-variant">{t("sys.sensors.gyro.att3dRefTitle")}</p>
          <div className="flex items-center justify-center rounded-lg border border-outline-variant/30 bg-slate-950/50 px-4 py-5 ring-1 ring-white/5">
            <div style={{ perspective: "280px" }}>
              <div
                className="relative h-[100px] w-[100px]"
                style={{
                  transformStyle: "preserve-3d",
                  transform: "rotateX(58deg) rotateZ(-42deg)",
                }}
              >
                <div className="absolute left-1/2 top-1/2 h-0 w-0" style={{ transformStyle: "preserve-3d" }}>
                  <div
                    className="absolute bg-amber-400/95"
                    style={{
                      width: 44,
                      height: 3,
                      left: 0,
                      top: -1.5,
                      transformOrigin: "0 50%",
                    }}
                  />
                  <div
                    className="absolute bg-sky-400/95"
                    style={{
                      width: 44,
                      height: 3,
                      left: 0,
                      top: -1.5,
                      transformOrigin: "0 50%",
                      transform: "rotateZ(90deg)",
                    }}
                  />
                  <div
                    className="absolute bg-violet-400/95"
                    style={{
                      width: 44,
                      height: 3,
                      left: 0,
                      top: -1.5,
                      transformOrigin: "0 50%",
                      transform: "rotateY(-90deg)",
                    }}
                  />
                  <div
                    className="absolute rounded-full bg-white/80"
                    style={{ width: 5, height: 5, left: -2.5, top: -2.5 }}
                  />
                </div>
              </div>
            </div>
          </div>
          <p className="text-center text-[9px] leading-relaxed text-on-surface-variant/85">{t("sys.sensors.gyro.att3dRefDesc")}</p>
        </div>

        {/* 数值卡 */}
        <div className="grid w-full min-w-[200px] max-w-md grid-cols-3 gap-3 font-mono text-[11px] lg:max-w-lg xl:max-w-[340px]">
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
