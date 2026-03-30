/** OGScope Analysis Lab API client / 星图解算实验室 API */

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

export async function fetchExperiments(
  q: string,
  page: number
): Promise<{ items: unknown[]; total: number }> {
  const qs = new URLSearchParams({ page: String(page), page_size: "30" });
  if (q) qs.set("q", q);
  const r = await fetch(`${API}/analysis/experiments?${qs}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function uploadFileUrl(filename: string): string {
  return `${API}/analysis/uploads/file?filename=${encodeURIComponent(filename)}`;
}

export async function exportExperiments(fmt: "json" | "csv"): Promise<string> {
  const r = await fetch(`${API}/analysis/experiments/export?format=${fmt}`);
  if (!r.ok) throw new Error(await r.text());
  return r.text();
}
