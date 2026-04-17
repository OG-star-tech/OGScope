export type SystemLogLevel = "INFO" | "WARN" | "ERROR";

export type SystemLogItem = {
  ts: string | null;
  level: SystemLogLevel;
  message: string;
  source: string;
  priority: number | null;
};

export type SystemLogsPayload = {
  service: string;
  since_seconds: number;
  limit: number;
  levels: SystemLogLevel[];
  items: SystemLogItem[];
  count: number;
};

export async function requestJson<T>(
  url: string,
  options: RequestInit & { cache?: RequestCache } = {},
): Promise<T> {
  const { cache, ...rest } = options;
  const fetchOpts: RequestInit = {
    headers: { "Content-Type": "application/json" },
    ...rest,
  };
  if (cache !== undefined) Object.assign(fetchOpts, { cache });
  const response = await fetch(url, fetchOpts);
  let data: unknown = {};
  try {
    data = await response.json();
  } catch {
    // ignore parse failure
  }
  if (!response.ok) {
    const d = data as { detail?: string };
    throw new Error(d.detail || `HTTP ${response.status}`);
  }
  return data as T;
}

export async function fetchSystemdLogs(params?: {
  service?: string;
  sinceSeconds?: number;
  limit?: number;
  levels?: SystemLogLevel[];
}): Promise<SystemLogsPayload> {
  const q = new URLSearchParams();
  if (params?.service) q.set("service", params.service);
  if (params?.sinceSeconds != null) q.set("since_seconds", String(params.sinceSeconds));
  if (params?.limit != null) q.set("limit", String(params.limit));
  if (params?.levels?.length) q.set("levels", params.levels.join(","));
  const qs = q.toString();
  return await requestJson<SystemLogsPayload>(
    `/api/dev/debug/logs/systemd${qs ? `?${qs}` : ""}`,
    { cache: "no-store" },
  );
}
