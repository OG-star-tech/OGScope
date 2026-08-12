import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Search, Wifi } from "lucide-react";
import { useSystemInfo } from "@shared/context/SystemInfoContext";
import { useI18n } from "@shared/i18n/I18nProvider";
import { requestJson } from "@shared/transport/http";

function httpPort(): number {
  return typeof window.OGSCOPE_HTTP_PORT === "number" ? window.OGSCOPE_HTTP_PORT : 8000;
}

function formatUptime(sec: unknown, isZh: boolean): string {
  const s = Math.max(0, parseInt(String(sec ?? 0), 10) || 0);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return isZh ? `${d}天 ${h}小时` : `${d}d ${h}h`;
  if (h > 0) return isZh ? `${h}小时 ${m}分` : `${h}h ${m}m`;
  return isZh ? `${m}分` : `${m}m`;
}

type WifiPayload = {
  mode?: string;
  active_connection?: string;
  wireless_interface?: string;
  ap_ipv4?: string;
  configured?: boolean;
  message?: string;
  ap_url_hint?: string;
  ap_ssid?: string;
  mdns_hostname_hint?: string;
  device_id_suffix?: string;
};

type ScanNetwork = { ssid: string; signal?: string | number; security?: string };
type Profile = { connection_name: string; ssid: string; autoconnect?: boolean };

export function NetworkPage() {
  const { locale } = useI18n();
  const isZh = locale === "zh";
  const tr = useCallback((zh: string, en: string) => (isZh ? zh : en), [isZh]);
  const { info, error: sysErr } = useSystemInfo();
  const [wifiText, setWifiText] = useState(() => tr("加载中...", "Loading..."));
  const [manualHint, setManualHint] = useState("");
  const [scanStatus, setScanStatus] = useState("");
  const [networks, setNetworks] = useState<ScanNetwork[]>([]);
  const [scanBusy, setScanBusy] = useState(false);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profBusy, setProfBusy] = useState(false);
  const [manualSsid, setManualSsid] = useState("");
  const [manualPass, setManualPass] = useState("");
  const [staBusy, setStaBusy] = useState(false);
  const [lanStatus, setLanStatus] = useState("");
  const [apHint, setApHint] = useState(`http://192.168.4.1:${httpPort()}`);
  const [wizardSsid, setWizardSsid] = useState("OGScope_xxxx");
  const [mdnsHref, setMdnsHref] = useState<string | null>(null);
  const [mdnsLabel, setMdnsLabel] = useState("—");
  const [showWizardPassword, setShowWizardPassword] = useState(false);

  const renderWifi = useCallback((data: WifiPayload) => {
    const mode = data.mode || "unknown";
    const active = data.active_connection || "-";
    const iface = data.wireless_interface || "wlan0";
    const apIpv4 = data.ap_ipv4 || "-";
    const configured = data.configured ? tr("是", "Yes") : tr("否", "No");
    const message = data.message ? `${tr("，消息: ", ", message: ")}${data.message}` : "";
    if (data.ap_url_hint) setApHint(data.ap_url_hint);
    if (data.ap_ssid) setWizardSsid(data.ap_ssid);
    const port = httpPort();
    if (data.mdns_hostname_hint) {
      const host = data.mdns_hostname_hint;
      const href = `http://${host}:${port}/debug`;
      setMdnsHref(href);
      setMdnsLabel(href);
    } else if (data.device_id_suffix) {
      const host = `ogscope-${data.device_id_suffix}.local`;
      const href = `http://${host}:${port}/debug`;
      setMdnsHref(href);
      setMdnsLabel(href);
    } else {
      setMdnsHref(null);
      setMdnsLabel(tr("未提供", "Not provided"));
    }
    setWifiText(
      `${tr("模式", "Mode")}: ${mode} | ${tr("活动连接", "Active")}: ${active} | ${tr("接口", "Interface")}: ${iface} | ${tr("AP地址", "AP address")}: ${apIpv4} | ${tr("已配置", "Configured")}: ${configured}${message}`,
    );
  }, [tr]);

  const refreshStatus = useCallback(async () => {
    const data = await requestJson<WifiPayload>("/api/network/wifi", { cache: "no-store" });
    renderWifi(data);
  }, [renderWifi]);

  useEffect(() => {
    refreshStatus().catch((err: Error) => setWifiText(`${tr("获取状态失败", "Status request failed")}: ${err.message}`));
  }, [refreshStatus, tr]);

  useEffect(() => {
    setScanStatus("");
    setManualHint("");
    setLanStatus("");
  }, [locale]);

  const switchMode = async (mode: string) => {
    if (!window.confirm(tr(
      `切换到 ${mode.toUpperCase()} 可能中断当前连接。确认继续？`,
      `Switching to ${mode.toUpperCase()} may disconnect this session. Continue?`,
    ))) return;
    setWifiText(`${tr("正在切换到", "Switching to")} ${mode.toUpperCase()}...`);
    const data = await requestJson<WifiPayload>("/api/network/wifi", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    renderWifi(data);
  };

  const runScan = async () => {
    setScanBusy(true);
    setScanStatus(tr("扫描中...", "Scanning..."));
    setNetworks([]);
    try {
      const res = await requestJson<{ networks?: ScanNetwork[]; hint?: string }>(
        "/api/network/wifi/scan",
        { cache: "no-store" },
      );
      const list = res.networks || [];
      const hint = res.hint ? ` ${res.hint}` : "";
      setNetworks(list);
      setScanStatus(`${tr("扫描到", "Found")} ${list.length} ${tr("个网络", "network(s)")}${hint}`.trim());
    } catch (e) {
      setScanStatus(`${tr("扫描失败", "Scan failed")}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setScanBusy(false);
    }
  };

  const connectSsid = async (ssid: string) => {
    const pwd = window.prompt(`${tr("输入密码", "Enter password")}: ${ssid}`, "");
    if (pwd === null) return;
    setManualHint("");
    setWifiText(tr("正在连接...", "Connecting..."));
    setStaBusy(true);
    try {
      const data = await requestJson<WifiPayload>("/api/network/wifi/sta/connect", {
        method: "POST",
        body: JSON.stringify({ ssid, password: pwd || null }),
      });
      renderWifi(data);
      const m = data.mode || "unknown";
      setManualHint(
        m === "sta"
          ? `${tr("连接成功，当前连接", "Connected")}: ${data.active_connection || "—"}`
          : `${tr("连接请求已提交，当前模式", "Connection submitted; mode")}: ${m}, ${tr("连接", "connection")}: ${data.active_connection || "—"}`,
      );
      window.setTimeout(() => void refreshStatus().catch(() => {}), 2500);
    } catch (e) {
      setWifiText(`${tr("连接失败", "Connection failed")}: ${e instanceof Error ? e.message : String(e)}`);
      setManualHint(`${tr("错误详情", "Details")}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setStaBusy(false);
    }
  };

  const connectManual = async () => {
    const ssid = manualSsid.trim();
    if (!ssid) {
      window.alert(tr("请输入 SSID", "Enter an SSID"));
      return;
    }
    setManualHint("");
    setWifiText(tr("正在连接...", "Connecting..."));
    setStaBusy(true);
    try {
      const data = await requestJson<WifiPayload>("/api/network/wifi/sta/connect", {
        method: "POST",
        body: JSON.stringify({ ssid, password: manualPass || null }),
      });
      renderWifi(data);
      const m = data.mode || "unknown";
      setManualHint(
        m === "sta"
          ? `${tr("连接成功，当前连接", "Connected")}: ${data.active_connection || "—"}`
          : `${tr("连接请求已提交，当前模式", "Connection submitted; mode")}: ${m}, ${tr("连接", "connection")}: ${data.active_connection || "—"}`,
      );
      window.setTimeout(() => void refreshStatus().catch(() => {}), 2500);
    } catch (e) {
      setWifiText(`${tr("连接失败", "Connection failed")}: ${e instanceof Error ? e.message : String(e)}`);
      setManualHint(`${tr("错误详情", "Details")}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setStaBusy(false);
    }
  };

  const refreshProfiles = async () => {
    setProfBusy(true);
    try {
      const res = await requestJson<{ profiles?: Profile[] }>("/api/network/wifi/profiles", {
        cache: "no-store",
      });
      setProfiles(res.profiles || []);
    } catch (e) {
      setProfiles([]);
      window.alert(e instanceof Error ? e.message : String(e));
    } finally {
      setProfBusy(false);
    }
  };

  const activateProfile = async (connection_name: string) => {
    try {
      await requestJson("/api/network/wifi/profile/activate", {
        method: "POST",
        body: JSON.stringify({ connection_name }),
      });
      setWifiText(tr("已发送激活请求", "Activation requested"));
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  };

  async function probeHealth(ip: string, port: number): Promise<string | null> {
    const url = `http://${ip}:${port}/health`;
    try {
      const ac = new AbortController();
      const tmr = window.setTimeout(() => ac.abort(), 700);
      const r = await fetch(url, { signal: ac.signal, mode: "cors" });
      window.clearTimeout(tmr);
      if (!r.ok) return null;
      const j = (await r.json()) as { status?: string };
      if (j && j.status === "healthy") return `http://${ip}:${port}`;
    } catch {
      // ignore
    }
    return null;
  }

  const scanLan = async () => {
    const port = httpPort();
    setLanStatus(tr("扫描中...", "Scanning..."));
    const bases = ["192.168.0", "192.168.1", "192.168.31", "10.0.0"];
    for (const base of bases) {
      const ips: string[] = [];
      for (let i = 1; i < 255; i++) ips.push(`${base}.${i}`);
      for (let i = 0; i < ips.length; i += 48) {
        const chunk = ips.slice(i, i + 48);
        const results = await Promise.all(chunk.map((ip) => probeHealth(ip, port)));
        const hit = results.find(Boolean);
        if (hit) {
          setLanStatus(`${tr("已找到设备", "Device found")}: ${hit}`);
          window.location.href = `${hit}/debug`;
          return;
        }
      }
    }
    setLanStatus(tr("未找到设备", "No device found"));
  };

  const sysRows = useMemo(() => {
    if (!info) return [];
    const wifiQ =
      info.wifi_quality != null && !Number.isNaN(Number(info.wifi_quality))
        ? `${Number(info.wifi_quality).toFixed(1)}%`
        : "—";
    const wifiSig =
      info.wifi_signal_dbm != null && !Number.isNaN(Number(info.wifi_signal_dbm))
        ? `${Number(info.wifi_signal_dbm).toFixed(0)} dBm (${String(info.wifi_interface ?? "?")})`
        : "—";
    return [
      [tr("平台", "Platform"), String(info.platform ?? "—")],
      [tr("系统", "System"), String(info.os ?? "—")],
      [tr("CPU 占用", "CPU usage"), info.cpu_usage == null ? "—" : `${Number(info.cpu_usage).toFixed(1)}%`],
      [tr("内存占用", "Memory usage"), info.memory_usage == null ? "—" : `${Number(info.memory_usage).toFixed(1)}%`],
      [tr("CPU 温度", "CPU temperature"), info.temperature == null ? "—" : `${Number(info.temperature).toFixed(1)} °C`],
      [tr("运行时长", "Uptime"), formatUptime(info.uptime_seconds, isZh)],
      [tr("1 分钟负载", "Load (1m)"), String(info.load_average_1m ?? "—")],
      [tr("WiFi 质量", "WiFi quality"), wifiQ],
      [tr("WiFi 信号", "WiFi signal"), wifiSig],
    ] as [string, string][];
  }, [info, isZh, tr]);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <header>
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-on-surface-variant">
          <span>Console</span>
          <span>/</span>
          <span className="text-primary">System_Network_Debug</span>
        </div>
        <h2 className="mt-1 font-headline text-3xl font-black tracking-tight">NETWORK TERMINAL</h2>
        <p className="text-sm text-on-surface-variant">
          {tr("WiFi 管理、模式切换、发现与恢复工具", "WiFi management, mode switching, discovery, and recovery tools")}
        </p>
      </header>

      {sysErr && (
        <div className="rounded-lg border border-error/40 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
          {sysErr}
        </div>
      )}

      <section className="grid grid-cols-12 gap-6">
        <div className="col-span-12 space-y-6 lg:col-span-8">
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container">
            <div className="flex items-center justify-between border-b border-outline-variant/20 bg-surface-container-high px-4 py-3">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
                <Wifi className="h-4 w-4" />
                WiFi Control
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="rounded border border-outline-variant/40 px-2 py-1 text-xs hover:border-primary"
                  onClick={() => void switchMode("sta").catch((e) => setWifiText(String(e)))}
                >
                  STA
                </button>
                <button
                  type="button"
                  className="rounded border border-outline-variant/40 px-2 py-1 text-xs hover:border-primary"
                  onClick={() => void switchMode("ap").catch((e) => setWifiText(String(e)))}
                >
                  AP
                </button>
                <button
                  type="button"
                  className="rounded border border-outline-variant/40 p-1.5 hover:border-primary"
                  onClick={() => void refreshStatus().catch((e) => setWifiText(String(e)))}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <div className="space-y-3 p-4">
              <p className="rounded border border-outline-variant/20 bg-surface-container-low p-3 font-mono text-xs text-on-surface">
                {wifiText}
              </p>
              <div className="grid gap-2 text-xs text-on-surface-variant md:grid-cols-2">
                <p>
                  {tr("AP 地址：", "AP address: ")}<span className="break-all font-mono text-on-surface">{apHint}</span>
                </p>
                <p>
                  {tr("mDNS：", "mDNS: ")}
                  {mdnsHref ? (
                    <a className="font-mono text-primary underline" href={mdnsHref}>
                      {mdnsLabel}
                    </a>
                  ) : (
                    <span className="font-mono text-on-surface">{mdnsLabel}</span>
                  )}
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wider">Scan Results</h3>
              <button
                type="button"
                disabled={scanBusy}
                className="rounded bg-primary-container px-3 py-1.5 text-xs font-medium text-on-primary-container disabled:opacity-50"
                onClick={() => void runScan()}
              >
                <span className="inline-flex items-center gap-1">
                  <Search className="h-3.5 w-3.5" /> {tr("扫描 WiFi", "Scan WiFi")}
                </span>
              </button>
            </div>
            <p className="mb-3 text-xs text-on-surface-variant">
              {scanStatus || tr("由设备端 NetworkManager 执行扫描", "Scanning is performed by NetworkManager on the device")}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-outline-variant/30 text-xs uppercase tracking-wider text-on-surface-variant">
                    <th className="p-2">SSID</th>
                    <th className="p-2">{tr("信号", "Signal")}</th>
                    <th className="p-2">{tr("安全", "Security")}</th>
                    <th className="p-2 text-right">{tr("操作", "Action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {networks.map((n) => (
                    <tr key={n.ssid} className="border-b border-outline-variant/10">
                      <td className="p-2 font-mono">{n.ssid}</td>
                      <td className="p-2">{n.signal ?? "—"}</td>
                      <td className="p-2">{n.security ?? "—"}</td>
                      <td className="p-2 text-right">
                        <button
                          type="button"
                          disabled={staBusy}
                          className="rounded border border-primary/40 px-2 py-1 text-xs text-primary disabled:opacity-50"
                          onClick={() => void connectSsid(n.ssid)}
                        >
                          Connect
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider">{tr("已保存网络", "Known Networks")}</h3>
            <button
              type="button"
              disabled={profBusy}
              className="rounded border border-outline-variant/40 px-3 py-1.5 text-xs disabled:opacity-50"
              onClick={() => void refreshProfiles()}
            >
              {tr("刷新已保存网络", "Refresh saved networks")}
            </button>
            <table className="mt-3 w-full text-left text-sm">
              <thead>
                <tr className="border-b border-outline-variant/30 text-xs uppercase tracking-wider text-on-surface-variant">
                  <th className="p-2">{tr("连接名", "Connection")}</th>
                  <th className="p-2">SSID</th>
                  <th className="p-2">{tr("自动连接", "Auto-connect")}</th>
                  <th className="p-2 text-right">{tr("操作", "Action")}</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.connection_name} className="border-b border-outline-variant/10">
                    <td className="p-2">{p.connection_name}</td>
                    <td className="p-2">{p.ssid}</td>
                    <td className="p-2">{p.autoconnect ? tr("是", "Yes") : tr("否", "No")}</td>
                    <td className="p-2 text-right">
                      <button
                        type="button"
                        className="rounded border border-outline-variant/40 px-2 py-1 text-xs hover:border-primary"
                        onClick={() => void activateProfile(p.connection_name)}
                      >
                        Activate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="col-span-12 space-y-6 lg:col-span-4">
          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider">{tr("系统监控", "System Monitor")}</h3>
            <div className="grid gap-2">
              {sysRows.map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-outline-variant/10 pb-1 text-xs">
                  <span className="text-on-surface-variant">{k}</span>
                  <span className="font-mono text-on-surface">{v}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider">{tr("手动连接", "Manual Connect")}</h3>
            <div className="space-y-2">
              <label className="block text-xs text-on-surface-variant">
                SSID
                <input
                  className="mt-1 w-full rounded border border-outline-variant/40 bg-surface-container-low px-2 py-1.5 text-sm"
                  value={manualSsid}
                  onChange={(e) => setManualSsid(e.target.value)}
                />
              </label>
              <label className="block text-xs text-on-surface-variant">
                Password
                <input
                  type="password"
                  className="mt-1 w-full rounded border border-outline-variant/40 bg-surface-container-low px-2 py-1.5 text-sm"
                  value={manualPass}
                  onChange={(e) => setManualPass(e.target.value)}
                />
              </label>
              <button
                type="button"
                disabled={staBusy}
                className="w-full rounded bg-primary-container px-4 py-2 text-sm font-medium text-on-primary-container disabled:opacity-50"
                onClick={() => void connectManual()}
              >
                {tr("连接并切换 STA", "Connect and switch to STA")}
              </button>
            </div>
            <p className="mt-2 text-xs text-on-surface-variant">{manualHint}</p>
          </div>

          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider">{tr("WiFi 引导", "WiFi Setup Guide")}</h3>
            <ol className="list-decimal space-y-1 pl-4 text-xs text-on-surface-variant">
              <li>
                {tr("连接热点", "Join hotspot")} <strong>{wizardSsid}</strong>{tr("，密码", ", password")} {" "}
                <code>{showWizardPassword ? "ogscopeadmin" : "••••••••"}</code>{" "}
                <button
                  type="button"
                  className="rounded border border-outline-variant/30 px-1.5 py-0.5 text-[10px]"
                  onClick={() => setShowWizardPassword((shown) => !shown)}
                >
                  {showWizardPassword ? tr("隐藏", "Hide") : tr("显示", "Show")}
                </button>
              </li>
              <li>{tr("浏览器打开", "Open in a browser")} <span className="break-all font-mono">http://192.168.4.1:{httpPort()}</span></li>
              <li>{tr("扫描 WiFi 或手动填写 SSID 连接", "Scan WiFi or enter an SSID manually")}</li>
            </ol>
          </div>

          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider">Find Device</h3>
            <p className="mb-3 text-xs text-on-surface-variant">
              {tr("扫描常见网段并探测 /health", "Scan common subnets and probe /health")}
            </p>
            <button
              type="button"
              className="w-full rounded border border-outline-variant/40 px-3 py-2 text-sm hover:border-primary"
              onClick={() => void scanLan()}
            >
              {tr("扫描局域网", "Scan LAN")}
            </button>
            <p className="mt-2 text-xs text-on-surface-variant">{lanStatus}</p>
          </div>
        </aside>
      </section>
    </div>
  );
}
