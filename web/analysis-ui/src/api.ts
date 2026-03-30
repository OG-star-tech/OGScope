/** OGScope Analysis Lab API client / 星空解算控制台 API */

const API = "/api";

export type UploadFileRow = {
  filename: string;
  size: number;
  modified_at: string;
  source?: string;
  last_solve?: Record<string, unknown>;
};

export type CentroidParams = {
  sigma?: number;
  max_area?: number;
  min_area?: number;
  filtsize?: number;
  binary_open?: boolean;
  max_axis_ratio?: number;
};

export type SolveParams = {
  hint_ra_deg?: number | null;
  hint_dec_deg?: number | null;
  fov_estimate?: number | null;
  fov_max_error?: number | null;
  solve_timeout_ms?: number | null;
  centroid?: CentroidParams | null;
  max_image_side?: number | null;
};

async function parseJson(resp: Response): Promise<unknown> {
  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return resp.json();
  }
  const t = await resp.text();
  throw new Error(t || `HTTP ${resp.status}`);
}

export async function fetchUploads(): Promise<{ files: UploadFileRow[] }> {
  const r = await fetch(`${API}/analysis/uploads`);
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ files: UploadFileRow[] }>;
}

export async function deletePoolUpload(
  filename: string,
  options?: { deleteExperiments?: boolean },
): Promise<{ deleted_experiments?: number }> {
  const qs = new URLSearchParams();
  if (options?.deleteExperiments) qs.set("delete_experiments", "true");
  const q = qs.toString();
  const r = await fetch(
    `${API}/analysis/uploads/${encodeURIComponent(filename)}${q ? `?${q}` : ""}`,
    { method: "DELETE" },
  );
  if (!r.ok) throw new Error(await r.text());
  return (await r.json().catch(() => ({}))) as { deleted_experiments?: number };
}

export async function uploadFile(
  file: File,
  source = "analysis_upload"
): Promise<{ filename: string }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("source", source);
  const r = await fetch(`${API}/analysis/upload`, { method: "POST", body: fd });
  const data = await parseJson(r);
  if (!r.ok) throw new Error(String((data as { detail?: string }).detail || r.status));
  return data as { filename: string };
}

export async function importFromDebug(filename: string): Promise<{ filename: string }> {
  const r = await fetch(`${API}/analysis/uploads/import_from_debug`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename }),
  });
  const data = await parseJson(r);
  if (!r.ok) throw new Error(String((data as { detail?: string }).detail || r.status));
  return data as { filename: string };
}

export async function solveImage(
  input_name: string,
  params: SolveParams
): Promise<unknown> {
  const r = await fetch(`${API}/analysis/solve/image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input_name, ...params }),
  });
  const data = await parseJson(r);
  if (!r.ok) throw new Error(String((data as { detail?: string }).detail || r.status));
  return data;
}

export type BatchRun = { label: string; params: SolveParams };

export async function solveBatch(
  input_name: string,
  runs: BatchRun[]
): Promise<unknown> {
  const r = await fetch(`${API}/analysis/solve/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input_name, runs }),
  });
  const data = await parseJson(r);
  if (!r.ok) throw new Error(String((data as { detail?: string }).detail || r.status));
  return data;
}

export async function fetchPresets(scope: "official" | "user"): Promise<{
  presets: Array<{ id: string; name: string; params: SolveParams; scope: string }>;
}> {
  const r = await fetch(`${API}/analysis/presets?scope=${scope}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function saveUserPreset(
  name: string,
  params: SolveParams
): Promise<unknown> {
  const r = await fetch(`${API}/analysis/presets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, params }),
  });
  const data = await parseJson(r);
  if (!r.ok) throw new Error(String((data as { detail?: string }).detail || r.status));
  return data;
}

export async function deleteUserPreset(id: string): Promise<void> {
  const r = await fetch(`${API}/analysis/presets/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function saveExperiment(payload: {
  input_name: string;
  preset_label: string;
  result_json: unknown;
  metrics: Record<string, unknown>;
  thumbnail_png_base64?: string | null;
  replay?: Record<string, unknown> | null;
  save_asset_snapshot?: boolean;
}): Promise<unknown> {
  const r = await fetch(`${API}/analysis/experiments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await parseJson(r);
  if (!r.ok) throw new Error(String((data as { detail?: string }).detail || r.status));
  return data;
}

export async function deleteExperimentRecord(experimentId: string): Promise<void> {
  const r = await fetch(
    `${API}/analysis/experiments/${encodeURIComponent(experimentId)}`,
    { method: "DELETE" },
  );
  if (!r.ok) throw new Error(await r.text());
}

export async function fetchExperiments(
  q: string,
  page: number,
  pageSize = 30,
): Promise<{ items: unknown[]; total: number; page_size?: number }> {
  const qs = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (q) qs.set("q", q);
  const r = await fetch(`${API}/analysis/experiments?${qs}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export type DebugFileRow = {
  name: string;
  size: number;
  modified: string;
  type: string;
};

export async function fetchDebugFiles(): Promise<{ files: DebugFileRow[] }> {
  const r = await fetch(`${API}/debug/files`);
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ files: DebugFileRow[] }>;
}

export function debugCaptureFileUrl(filename: string): string {
  return `${API}/debug/files/${encodeURIComponent(filename)}`;
}

export async function fetchDebugFileInfo(
  filename: string,
): Promise<Record<string, unknown>> {
  const r = await fetch(
    `${API}/debug/files/${encodeURIComponent(filename)}/info`,
  );
  const data = await parseJson(r);
  if (!r.ok) throw new Error(String((data as { detail?: string }).detail || r.status));
  return data as Record<string, unknown>;
}

export async function fetchUploadFileInfo(
  filename: string,
): Promise<Record<string, unknown>> {
  const r = await fetch(
    `${API}/analysis/uploads/${encodeURIComponent(filename)}/info`,
  );
  const data = await parseJson(r);
  if (!r.ok) throw new Error(String((data as { detail?: string }).detail || r.status));
  return data as Record<string, unknown>;
}

export function uploadFileUrl(filename: string): string {
  return `${API}/analysis/uploads/file?filename=${encodeURIComponent(filename)}`;
}

export async function exportExperiments(fmt: "json" | "csv"): Promise<string> {
  const r = await fetch(`${API}/analysis/experiments/export?format=${fmt}`);
  if (!r.ok) throw new Error(await r.text());
  return r.text();
}


export async function fetchUploadExperimentCount(
  filename: string,
): Promise<{ count: number }> {
  const r = await fetch(
    `${API}/analysis/uploads/${encodeURIComponent(filename)}/experiment_count`,
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ count: number }>;
}

export type LabPublicSettings = {
  solver_timeout_ms: number;
  star_analysis_target_fps: number;
  camera_width: number;
  camera_height: number;
  camera_fps: number;
  solver_fov_deg: number;
  solver_max_image_side: number;
};

export async function fetchLabSettings(): Promise<LabPublicSettings> {
  const r = await fetch(`${API}/analysis/settings`);
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<LabPublicSettings>;
}

export type SolveVideoFrameSource = "camera" | "file";

export async function solveVideoFrame(payload: {
  source: SolveVideoFrameSource;
  input_name?: string | null;
  frame_index?: number;
  time_sec?: number | null;
} & SolveParams): Promise<{ success: boolean; result?: Record<string, unknown> }> {
  const r = await fetch(`${API}/analysis/solve/frame`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await parseJson(r);
  if (!r.ok) throw new Error(String((data as { detail?: string }).detail || r.status));
  return data as { success: boolean; result?: Record<string, unknown> };
}

export function experimentAssetUrl(experimentId: string): string {
  return `${API}/analysis/experiments/${encodeURIComponent(experimentId)}/asset`;
}

export type SystemInfo = {
  platform: string;
  os: string;
  cpu_usage: number;
  memory_usage: number;
  temperature: number;
  uptime_seconds?: number;
  load_average_1m?: number;
};

export async function fetchSystemInfo(): Promise<SystemInfo> {
  const r = await fetch(`${API}/system/info`);
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<SystemInfo>;
}
