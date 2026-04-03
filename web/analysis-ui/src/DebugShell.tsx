import type { ReactNode } from "react";
import {
  Activity,
  Bolt,
  Camera,
  Cpu,
  LayoutDashboard,
  Network,
  Sparkles,
  Touchpad,
  Wifi,
} from "lucide-react";
import { useSystemInfo } from "./context/SystemInfoContext";
import { useI18n } from "./i18n/I18nProvider";

type SystemRoute = "overview" | "network" | "sensors" | "hmi" | "power";

const navClass = (active: boolean) =>
  `flex items-center gap-3 rounded-lg px-3 py-2.5 font-headline text-sm tracking-tight transition-colors ${
    active
      ? "border-r-2 border-primary bg-white/5 font-semibold text-primary"
      : "text-on-surface-variant hover:bg-white/5 hover:text-on-surface"
  }`;

export function DebugShell({
  route,
  onRouteChange,
  children,
}: {
  route: SystemRoute;
  onRouteChange: (route: SystemRoute) => void;
  children: ReactNode;
}) {
  const { t, locale, setLocale } = useI18n();
  const { info } = useSystemInfo();

  const cpu = info?.cpu_usage != null ? Number(info.cpu_usage).toFixed(1) : "—";
  const mem = info?.memory_usage != null ? Number(info.memory_usage).toFixed(1) : "—";
  const temp = info?.temperature != null ? Number(info.temperature).toFixed(1) : "—";
  const wifiQ =
    info?.wifi_quality != null && !Number.isNaN(Number(info.wifi_quality))
      ? `${Number(info.wifi_quality).toFixed(0)}%`
      : "—";

  const routeTitle: Record<SystemRoute, string> = {
    overview: t("sys.shell.top.overview"),
    network: t("sys.shell.top.network"),
    sensors: t("sys.shell.top.sensors"),
    hmi: t("sys.shell.top.hmi"),
    power: t("sys.shell.top.power"),
  };
  const externalLinkClass = navClass(false);
  const openNamedWindow = (url: string, name: string) => {
    const win = window.open(url, name);
    if (win) win.focus();
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-background text-on-surface md:flex-row">
      <aside className="glass-panel z-50 flex w-full shrink-0 flex-col border-b border-outline-variant/20 bg-surface-container-low/80 backdrop-blur-xl md:fixed md:left-0 md:top-0 md:h-full md:w-64 md:border-b-0 md:border-r md:border-white/5">
        <div className="p-5">
          <div className="mb-8 flex items-center gap-3">
            <div className="primary-gradient flex h-10 w-10 items-center justify-center rounded-lg shadow-lg">
              <Sparkles className="h-5 w-5 text-on-primary-container" />
            </div>
            <div>
              <h1 className="font-headline text-lg font-bold tracking-widest text-primary">OGScope</h1>
              <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                {t("sys.shell.subtitle")}
              </p>
            </div>
          </div>
          <nav className="flex flex-col gap-0.5">
            <button type="button" className={navClass(route === "overview")} onClick={() => onRouteChange("overview")}>
              <LayoutDashboard className="h-4 w-4 shrink-0" />
              <span>{t("sys.shell.nav.overview")}</span>
            </button>
            <button type="button" className={navClass(route === "network")} onClick={() => onRouteChange("network")}>
              <Network className="h-4 w-4 shrink-0" />
              <span>{t("sys.shell.nav.network")}</span>
            </button>
            <a
              href="/debug/camera"
              className={externalLinkClass}
              onClick={(e) => {
                e.preventDefault();
                openNamedWindow("/debug/camera", "ogscopeCameraConsole");
              }}
            >
              <Camera className="h-4 w-4 shrink-0" />
              <span>{t("sys.shell.nav.camera")}</span>
            </a>
            <a
              href="/debug/analysis"
              className={externalLinkClass}
              onClick={(e) => {
                e.preventDefault();
                openNamedWindow("/debug/analysis", "ogscopeAnalysisConsole");
              }}
            >
              <Sparkles className="h-4 w-4 shrink-0" />
              <span>{t("sys.shell.nav.analysis")}</span>
            </a>
            <button type="button" className={navClass(route === "sensors")} onClick={() => onRouteChange("sensors")}>
              <Activity className="h-4 w-4 shrink-0" />
              <span>{t("sys.shell.nav.sensors")}</span>
            </button>
            <button type="button" className={navClass(route === "power")} onClick={() => onRouteChange("power")}>
              <Bolt className="h-4 w-4 shrink-0" />
              <span>{t("sys.shell.nav.power")}</span>
            </button>
            <button type="button" className={navClass(route === "hmi")} onClick={() => onRouteChange("hmi")}>
              <Touchpad className="h-4 w-4 shrink-0" />
              <span>{t("sys.shell.nav.hmi")}</span>
            </button>
          </nav>
        </div>
        <div className="mt-auto hidden p-5 md:block">
          <div className="rounded-xl border border-white/5 bg-surface-container-low p-3">
            <p className="truncate text-xs font-semibold text-on-surface">{t("sys.shell.workbench")}</p>
            <p className="font-mono text-[10px] text-on-surface-variant">
              {t("sys.shell.node")}: OGSCOPE_PI_ZERO_2W
            </p>
          </div>
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col md:ml-64">
        <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center justify-between border-b border-white/5 bg-neutral-950/80 px-4 backdrop-blur-md md:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span className="hidden truncate border-b-2 border-primary pb-0.5 font-mono text-xs uppercase tracking-wider text-primary sm:inline">
              {routeTitle[route]}
            </span>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-3 sm:gap-4">
            <div className="mr-2 flex gap-1 text-[10px]">
              <button
                type="button"
                className={`rounded px-2 py-0.5 ${
                  locale === "zh" ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant"
                }`}
                onClick={() => setLocale("zh")}
              >
                {t("lang.zh")}
              </button>
              <button
                type="button"
                className={`rounded px-2 py-0.5 ${
                  locale === "en" ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant"
                }`}
                onClick={() => setLocale("en")}
              >
                {t("lang.en")}
              </button>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-3 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant sm:gap-4">
            <span className="flex items-center gap-1 text-primary">
              <Cpu className="h-3.5 w-3.5" /> CPU {cpu}%
            </span>
            <span className="flex items-center gap-1">
              <Activity className="h-3.5 w-3.5" /> MEM {mem}%
            </span>
            <span className="flex items-center gap-1">
              <span className="text-xs">°C</span> {temp}
            </span>
            <span className="flex items-center gap-1 text-secondary">
              <Wifi className="h-3.5 w-3.5" /> {wifiQ}
            </span>
            </div>
          </div>
        </header>

        <main className="og-scrollbar min-h-0 flex-1 overflow-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
