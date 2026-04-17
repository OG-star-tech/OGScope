import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Cpu,
  HardDrive,
  RefreshCw,
  Thermometer,
  Wifi,
} from "lucide-react";
import { useSystemInfo } from "@shared/context/SystemInfoContext";
import { fetchSystemdLogs, type SystemLogItem, type SystemLogLevel } from "@dev-api/system";
import { useI18n } from "@shared/i18n/I18nProvider";

function formatUptime(sec: unknown): string {
  const s = Math.max(0, parseInt(String(sec ?? 0), 10) || 0);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function asNum(v: unknown, digits = 1): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(digits);
}

function levelClass(level: SystemLogLevel): string {
  if (level === "ERROR") return "text-error";
  if (level === "WARN") return "text-amber-300";
  return "text-primary";
}

function formatTs(ts: string | null): string {
  if (!ts) return "--:--:--";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "--:--:--";
  return d.toLocaleTimeString();
}

export function OverviewPage() {
  const MAX_LOG_ITEMS = 300;
  const AUTO_SCROLL_THRESHOLD = 24;
  const { t } = useI18n();
  const { info, error } = useSystemInfo();
  const [logsEnabled, setLogsEnabled] = useState(false);
  const [logLevels, setLogLevels] = useState<SystemLogLevel[]>(["INFO", "WARN", "ERROR"]);
  const [logs, setLogs] = useState<SystemLogItem[]>([]);
  const [logsErr, setLogsErr] = useState<string | null>(null);
  const [logsBusy, setLogsBusy] = useState(false);
  const [followLogs, setFollowLogs] = useState(true);
  const logScrollRef = useRef<HTMLDivElement | null>(null);
  const prevLogKeysRef = useRef<Set<string>>(new Set());

  const cpu = asNum(info?.cpu_usage);
  const mem = asNum(info?.memory_usage);
  const temp = asNum(info?.temperature);
  const load = info?.load_average_1m != null ? String(info.load_average_1m) : "—";
  const wifiQ =
    info?.wifi_quality != null && !Number.isNaN(Number(info.wifi_quality))
      ? `${Number(info.wifi_quality).toFixed(0)}%`
      : "—";
  const wifiSig =
    info?.wifi_signal_dbm != null && !Number.isNaN(Number(info.wifi_signal_dbm))
      ? `${Number(info.wifi_signal_dbm).toFixed(0)} dBm`
      : "—";

  const loadLogs = async () => {
    if (logLevels.length === 0) {
      setLogs([]);
      return;
    }
    setLogsBusy(true);
    try {
      setLogsErr(null);
      const data = await fetchSystemdLogs({
        service: "ogscope",
        sinceSeconds: 1200,
        limit: 240,
        levels: logLevels,
      });
      setLogs((prev) => {
        const known = new Set(
          prev.map((item) => `${item.ts ?? ""}::${item.level}::${item.source}::${item.message}`),
        );
        const merged = [...prev];
        for (const item of data.items) {
          const key = `${item.ts ?? ""}::${item.level}::${item.source}::${item.message}`;
          if (known.has(key)) continue;
          known.add(key);
          merged.push(item);
        }
        if (merged.length <= MAX_LOG_ITEMS) return merged;
        return merged.slice(merged.length - MAX_LOG_ITEMS);
      });
    } catch (e) {
      setLogsErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLogsBusy(false);
    }
  };

  useEffect(() => {
    if (!logsEnabled) return;
    void loadLogs();
    const id = window.setInterval(() => {
      if (!document.hidden) void loadLogs();
    }, 4000);
    return () => window.clearInterval(id);
  }, [logsEnabled, logLevels.join(",")]);

  useEffect(() => {
    const el = logScrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setFollowLogs(distanceToBottom <= AUTO_SCROLL_THRESHOLD);
    };
    onScroll();
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const el = logScrollRef.current;
    if (!el || logs.length === 0) return;
    const nextKeys = new Set(
      logs.map((item) => `${item.ts ?? ""}::${item.level}::${item.source}::${item.message}`),
    );
    let hasNewItem = false;
    nextKeys.forEach((key) => {
      if (!prevLogKeysRef.current.has(key)) hasNewItem = true;
    });
    prevLogKeysRef.current = nextKeys;
    if (followLogs && hasNewItem) {
      requestAnimationFrame(() => {
        if (!logScrollRef.current) return;
        logScrollRef.current.scrollTop = logScrollRef.current.scrollHeight;
      });
    }
  }, [logs, followLogs]);

  const selectedLevels = useMemo(() => new Set(logLevels), [logLevels]);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <header className="mb-1">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-on-surface-variant">
          <span>{t("sys.overview.breadcrumb.console")}</span>
          <span>/</span>
          <span className="text-primary">{t("sys.overview.breadcrumb.module")}</span>
        </div>
        <h2 className="mt-1 font-headline text-3xl font-black tracking-tight">{t("sys.overview.title")}</h2>
        <p className="text-sm text-on-surface-variant">{t("sys.overview.subtitle")}</p>
      </header>

      {error && (
        <div className="rounded-lg border border-error/40 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
          {error}
        </div>
      )}

      <section className="grid grid-cols-12 gap-4">
        <article className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4 md:col-span-3">
          <div className="mb-3 flex items-center justify-between text-[10px] uppercase tracking-wider text-on-surface-variant">
            <span>{t("sys.overview.metric.cpu")}</span>
            <Cpu className="h-4 w-4 text-primary" />
          </div>
          <div className="text-3xl font-bold text-on-surface">{cpu}%</div>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded bg-surface-container-high">
            <div className="h-full bg-primary" style={{ width: `${Math.min(Number(cpu) || 0, 100)}%` }} />
          </div>
        </article>

        <article className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4 md:col-span-3">
          <div className="mb-3 flex items-center justify-between text-[10px] uppercase tracking-wider text-on-surface-variant">
            <span>{t("sys.overview.metric.mem")}</span>
            <Activity className="h-4 w-4 text-secondary" />
          </div>
          <div className="text-3xl font-bold text-on-surface">{mem}%</div>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded bg-surface-container-high">
            <div className="h-full bg-secondary" style={{ width: `${Math.min(Number(mem) || 0, 100)}%` }} />
          </div>
        </article>

        <article className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4 md:col-span-3">
          <div className="mb-3 flex items-center justify-between text-[10px] uppercase tracking-wider text-on-surface-variant">
            <span>{t("sys.overview.metric.temp")}</span>
            <Thermometer className="h-4 w-4 text-primary" />
          </div>
          <div className="text-3xl font-bold text-on-surface">{temp}°C</div>
          <div className="mt-3 text-xs text-on-surface-variant">{t("sys.overview.tempState")}</div>
        </article>

        <article className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4 md:col-span-3">
          <div className="mb-3 flex items-center justify-between text-[10px] uppercase tracking-wider text-on-surface-variant">
            <span>{t("sys.overview.metric.wifi")}</span>
            <Wifi className="h-4 w-4 text-primary" />
          </div>
          <div className="text-3xl font-bold text-on-surface">{wifiQ}</div>
          <div className="mt-3 text-xs text-on-surface-variant">{wifiSig}</div>
        </article>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <article className="col-span-12 rounded-xl border border-white/5 bg-surface-container-low p-6 lg:col-span-8">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <h3 className="font-headline text-lg font-bold">{t("sys.overview.wifiSummary")}</h3>
              <p className="text-xs text-on-surface-variant">
                {t("sys.overview.iface")}: {String(info?.wifi_interface ?? "wlan0")}
              </p>
            </div>
            <span className="rounded border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] uppercase tracking-widest text-primary">
              {t("sys.overview.linkActive")}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-lg border border-outline-variant/20 bg-surface-container p-4">
              <p className="text-[10px] uppercase tracking-widest text-on-surface-variant">{t("sys.overview.signal")}</p>
              <p className="mt-1 font-mono text-2xl font-bold">{wifiSig}</p>
            </div>
            <div className="rounded-lg border border-outline-variant/20 bg-surface-container p-4">
              <p className="text-[10px] uppercase tracking-widest text-on-surface-variant">{t("sys.overview.quality")}</p>
              <p className="mt-1 font-mono text-2xl font-bold">{wifiQ}</p>
            </div>
          </div>
        </article>

        <aside className="col-span-12 space-y-4 lg:col-span-4">
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <p className="text-[10px] uppercase tracking-widest text-on-surface-variant">
              {t("sys.overview.metric.uptime")}
            </p>
            <p className="mt-1 text-xl font-bold">{formatUptime(info?.uptime_seconds)}</p>
          </div>
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <p className="text-[10px] uppercase tracking-widest text-on-surface-variant">
              {t("sys.overview.metric.load")}
            </p>
            <p className="mt-1 text-xl font-bold">{load}</p>
          </div>
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <div className="flex items-center justify-between">
              <p className="text-[10px] uppercase tracking-widest text-on-surface-variant">
                {t("sys.overview.metric.storage")}
              </p>
              <HardDrive className="h-4 w-4 text-on-surface-variant" />
            </div>
            <p className="mt-2 text-sm text-on-surface-variant">{t("sys.overview.storageComingSoon")}</p>
          </div>
        </aside>
      </section>

      <section className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant/20 pb-2">
          <div className="flex items-center gap-3">
            <span className="text-[10px] uppercase tracking-widest text-primary">{t("sys.logs.title")}</span>
            <span className="text-[10px] text-on-surface-variant">
              {t("sys.logs.kernel")}: {String(info?.os ?? "—")}
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <label className="inline-flex items-center gap-2 text-on-surface-variant">
              <input
                type="checkbox"
                checked={logsEnabled}
                onChange={(e) => setLogsEnabled(e.target.checked)}
              />
              {t("sys.logs.liveToggle")}
            </label>
            <button
              type="button"
              className="rounded border border-outline-variant/40 px-2 py-1 text-on-surface-variant hover:border-primary hover:text-on-surface"
              onClick={() => void loadLogs()}
            >
              <span className="inline-flex items-center gap-1">
                <RefreshCw className="h-3.5 w-3.5" /> {t("sys.logs.refresh")}
              </span>
            </button>
          </div>
        </div>

        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
          {(["INFO", "WARN", "ERROR"] as SystemLogLevel[]).map((lv) => (
            <label key={lv} className="inline-flex items-center gap-1.5 text-on-surface-variant">
              <input
                type="checkbox"
                checked={selectedLevels.has(lv)}
                onChange={(e) => {
                  setLogLevels((prev) => {
                    if (e.target.checked) return Array.from(new Set([...prev, lv]));
                    return prev.filter((x) => x !== lv);
                  });
                }}
              />
              <span className={levelClass(lv)}>{lv}</span>
            </label>
          ))}
          {!logsEnabled && (
            <span className="inline-flex items-center gap-1 rounded border border-outline-variant/30 px-2 py-0.5 text-[11px] text-on-surface-variant">
              <AlertTriangle className="h-3.5 w-3.5" /> {t("sys.logs.liveOffHint")}
            </span>
          )}
        </div>

        {logsErr && (
          <div className="mb-2 rounded border border-error/40 bg-error-container/20 px-2 py-1 text-xs text-on-error-container">
            {logsErr}
          </div>
        )}

        <div
          ref={logScrollRef}
          className="og-scrollbar max-h-72 space-y-1 overflow-auto font-mono text-[11px] text-on-surface-variant"
        >
          {logsBusy && logs.length === 0 && <div>{t("sys.logs.loading")}</div>}
          {!logsBusy && logs.length === 0 && <div>{t("sys.logs.empty")}</div>}
          {logs.map((item, idx) => (
            <div key={`${item.ts || "ts"}-${idx}`} className="flex items-start gap-2">
              <span className="shrink-0 text-primary">[{formatTs(item.ts)}]</span>
              <span className={`shrink-0 ${levelClass(item.level)}`}>{item.level}</span>
              <span className="shrink-0 text-on-surface/80">{item.source}</span>
              <span className="min-w-0 break-words text-on-surface">{item.message}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
