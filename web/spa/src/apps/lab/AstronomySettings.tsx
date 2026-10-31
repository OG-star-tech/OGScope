import type { SolveParams } from "@shared/api";

export function AstronomySettings({ value, onChange, zh }: { value: SolveParams; onChange: (next: SolveParams) => void; zh: boolean }) {
  const astronomy = value.astronomy ?? { policy: "current_pole_v1", refraction: { mode: "off" } };
  const refraction = astronomy.refraction ?? { mode: "off" };
  const observer = value.solve_context?.observer ?? {};
  const legacy = astronomy.policy === "catalog_visual_v1";
  const numeric = (label: string, current: number | undefined, update: (next: number | undefined) => void, min: number, max: number) => (
    <label className="block text-xs">{label}<input className="mt-1 w-full rounded border border-outline-variant/30 bg-surface-container px-2 py-1" type="number" step="any" min={min} max={max} value={current ?? ""} onChange={(event) => update(Number.isFinite(event.target.valueAsNumber) ? event.target.valueAsNumber : undefined)} /></label>
  );
  return <details className="mb-3 rounded border border-outline-variant/25 p-3">
    <summary className="cursor-pointer text-xs font-semibold">{zh ? "极轴目标与天文修正" : "Polar target and astronomy"}</summary>
    <div className="mt-3 space-y-3">
      <label className="block text-xs">{zh ? "目标策略" : "Target policy"}<select className="mt-1 w-full rounded bg-surface-container" value={astronomy.policy ?? "current_pole_v1"} onChange={(event) => onChange({ ...value, astronomy: { policy: event.target.value as "current_pole_v1" | "catalog_visual_v1", refraction: { mode: "off" } } })}>
        <option value="current_pole_v1">{zh ? "当前极轴（岁差、章动及观测方向修正）" : "Current pole (precession, nutation, observed directions)"}</option>
        <option value="catalog_visual_v1">{zh ? "J2000 极点（仅供历史对照）" : "J2000 pole (historical comparison only)"}</option>
      </select></label>
      <label className="block text-xs">{zh ? "目标极点" : "Target pole"}<select className="mt-1 w-full rounded bg-surface-container" value={value.target_pole ?? "north"} onChange={(event) => onChange({ ...value, target_pole: event.target.value as "north" | "south" })}>
        <option value="north">{zh ? "北天极" : "North celestial pole"}</option><option value="south">{zh ? "南天极" : "South celestial pole"}</option>
      </select></label>
      {!legacy && <>
        <label className="block text-xs">{zh ? "文件拍摄时间（ISO 8601，带时区）" : "File exposure time (ISO 8601 with timezone)"}<input className="mt-1 w-full rounded bg-surface-container px-2 py-1" type="text" placeholder="2026-10-31T00:00:00Z" value={value.observation_time_utc ?? ""} onChange={(event) => onChange({ ...value, observation_time_utc: event.target.value || undefined })} /></label>
        <p className="text-[10px] text-on-surface-variant">{zh ? "设备相机使用实际曝光时间。位置用于当地姿态和折射；缺少位置时仅提供天球图像引导。" : "The device camera uses its exposure time. Location enables local attitude and refraction; otherwise only celestial image guidance is available."}</p>
        <div className="grid grid-cols-2 gap-2">
          {numeric(zh ? "纬度 / °" : "Latitude / °", observer.latitude_deg, (next) => onChange({ ...value, solve_context: { observer: { ...observer, latitude_deg: next, source: "manual" } } }), -90, 90)}
          {numeric(zh ? "经度 / °" : "Longitude / °", observer.longitude_deg, (next) => onChange({ ...value, solve_context: { observer: { ...observer, longitude_deg: next, source: "manual" } } }), -180, 180)}
          {numeric(zh ? "海拔 / m" : "Elevation / m", observer.altitude_m, (next) => onChange({ ...value, solve_context: { observer: { ...observer, altitude_m: next, source: "manual" } } }), -500, 10000)}
        </div>
        <label className="block text-xs">{zh ? "大气折射" : "Atmospheric refraction"}<select className="mt-1 w-full rounded bg-surface-container" value={refraction.mode} onChange={(event) => onChange({ ...value, astronomy: { ...astronomy, refraction: { mode: event.target.value as "off" | "standard" | "measured" } } })}>
          <option value="off">{zh ? "关闭" : "Off"}</option><option value="standard">{zh ? "标准大气估计" : "Standard atmosphere estimate"}</option><option value="measured">{zh ? "实测气象参数" : "Measured weather"}</option>
        </select></label>
        {refraction.mode === "measured" && <div className="grid grid-cols-2 gap-2">
          {numeric(zh ? "气压 / hPa" : "Pressure / hPa", refraction.pressure_hpa, (next) => onChange({ ...value, astronomy: { ...astronomy, refraction: { ...refraction, pressure_hpa: next } } }), 1, 1100)}
          {numeric(zh ? "温度 / °C" : "Temperature / °C", refraction.temperature_c, (next) => onChange({ ...value, astronomy: { ...astronomy, refraction: { ...refraction, temperature_c: next } } }), -80, 60)}
        </div>}
        {refraction.mode !== "off" && <p className="text-[10px] text-on-surface-variant">{zh ? "需要观测位置；高度低于 5° 时不提供折射目标。默认湿度 50%、波长 0.55 μm；标准模式温度 10°C，按海拔估算气压。" : "Location required; refraction targets below 5° are unavailable. Defaults: 50% humidity, 0.55 μm; standard mode uses 10°C and elevation-based pressure."}</p>}
      </>}
    </div>
  </details>;
}
