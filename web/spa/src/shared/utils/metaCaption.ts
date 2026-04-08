/**
 * 画面角标与下方说明分工：角标只放分辨率/星点/FWHM 与解算摘要；
 * 此处放拍摄侧车与文件属性，避免与角标重复。
 * Corner HUD: resolution/stars/FWHM + solve; caption: exposure/gain/file time/size.
 */

import { formatDateTime, formatFileSize } from "./format";

export type MetaCaptionRow = { key: string; value: string };

function str(x: unknown): string | null {
  if (x == null) return null;
  if (typeof x === "string" && x.trim()) return x.trim();
  if (typeof x === "number" && !Number.isNaN(x)) return String(x);
  return null;
}

/** 曝光微秒转可读 / exposure_us to readable */
function formatExposureUs(us: unknown): string | null {
  if (typeof us !== "number" || us <= 0) return null;
  if (us >= 1_000_000) return `${(us / 1_000_000).toFixed(2)} s`;
  if (us >= 1000) return `${(us / 1000).toFixed(0)} ms`;
  return `${us} µs`;
}

export function buildMetaCaptionRows(
  meta: Record<string, unknown> | null,
  locale: string,
): MetaCaptionRow[] {
  if (!meta) return [];
  const rows: MetaCaptionRow[] = [];

  const ex = formatExposureUs(meta.exposure_us);
  if (ex) rows.push({ key: "meta.exposure", value: ex });

  const ag = str(meta.analogue_gain);
  const dg = str(meta.digital_gain);
  if (ag || dg) {
    const parts = [ag ? `A ${ag}` : "", dg ? `D ${dg}` : ""].filter(Boolean);
    rows.push({ key: "meta.gain", value: parts.join(" · ") });
  }

  const fps = str(meta.fps);
  if (fps) rows.push({ key: "meta.fps", value: fps });

  const sensor = str(meta.sensor);
  if (sensor) rows.push({ key: "meta.sensor", value: sensor });

  const cm = str(meta.color_mode);
  if (cm) rows.push({ key: "meta.colorMode", value: cm });

  const outRes = str(meta.resolution);
  if (outRes) rows.push({ key: "meta.outputResolution", value: outRes });

  const mod = str(meta.modified);
  if (mod) {
    rows.push({
      key: "meta.fileTime",
      value: formatDateTime(mod, locale),
    });
  }

  const sz = meta.size;
  if (typeof sz === "number" && sz > 0) {
    rows.push({ key: "meta.fileSize", value: formatFileSize(sz) });
  }

  return rows;
}
