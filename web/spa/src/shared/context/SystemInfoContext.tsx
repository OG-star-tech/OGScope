import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/** 与 /api/dev/system/info 对齐的宽松类型 / Loose shape aligned with dev system info API */
export type SystemInfoRecord = Record<string, unknown>;

type Ctx = {
  info: SystemInfoRecord | null;
  error: string | null;
  refresh: () => Promise<void>;
};

const SystemInfoContext = createContext<Ctx | null>(null);

const POLL_MS = 8000;

async function fetchInfo(): Promise<SystemInfoRecord> {
  const r = await fetch("/api/dev/system/info", { cache: "no-store" });
  let data: unknown = {};
  try {
    data = await r.json();
  } catch {
    // ignore
  }
  if (!r.ok) {
    const d = data as { detail?: string };
    throw new Error(d.detail || `HTTP ${r.status}`);
  }
  return data as SystemInfoRecord;
}

export function SystemInfoProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<SystemInfoRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const j = await fetchInfo();
      setInfo(j);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const value = useMemo<Ctx>(() => ({ info, error, refresh }), [info, error, refresh]);

  return (
    <SystemInfoContext.Provider value={value}>{children}</SystemInfoContext.Provider>
  );
}

export function useSystemInfo(): Ctx {
  const c = useContext(SystemInfoContext);
  if (!c) throw new Error("useSystemInfo must be used within SystemInfoProvider");
  return c;
}
