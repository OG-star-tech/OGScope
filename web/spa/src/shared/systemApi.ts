import { requestJson } from "@shared/transport/http";

export type HardwarePlaneStatusResponse = {
  success: boolean;
  error?: { code?: string; message?: string } | null;
  data?: {
    started?: boolean;
    services?: Record<string, unknown>;
    capabilities?: unknown[];
    metrics?: Record<string, unknown>;
  };
};

export async function fetchHardwarePlaneStatus(): Promise<HardwarePlaneStatusResponse> {
  return await requestJson<HardwarePlaneStatusResponse>(
    "/api/dev/system/hardware-plane/status",
    { cache: "no-store" },
  );
}

export async function postHardwarePlaneCommand(body: {
  target: string;
  action: string;
  payload?: Record<string, unknown>;
  timeout_ms?: number;
}): Promise<Record<string, unknown>> {
  return await requestJson<Record<string, unknown>>("/api/dev/system/hardware-plane/command", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

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
