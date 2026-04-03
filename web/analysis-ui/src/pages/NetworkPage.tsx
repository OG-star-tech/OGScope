import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Search, Wifi } from "lucide-react";
import { useSystemInfo } from "../context/SystemInfoContext";

async function requestJson<T>(url: string, options: RequestInit & { cache?: RequestCache } = {}): Promise<T> {
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
    // ignore
  }
  if (!response.ok) {
    const d = data as { detail?: string };
    throw new Error(d.detail || `HTTP ${response.status}`);
  }
  return data as T;
}

function httpPort(): number {
  return typeof window.OGSCOPE_HTTP_PORT === "number" ? window.OGSCOPE_HTTP_PORT : 8000;
}

function formatUptime(sec: unknown): string {
  const s = Math.max(0, parseInt(String(sec ?? 0), 10) || 0);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}天 ${h}小时`;
  if (h > 0) return `${h}小时 ${m}分`;
  return `${m}分`;
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
  const { info, error: sysErr } = useSystemInfo();
  const [wifiText, setWifiText] = useState("加载中...");
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

  const renderWifi = useCallback((data: WifiPayload) => {
    const mode = data.mode || "unknown";
    const active = data.active_connection || "-";
    const iface = data.wireless_interface || "wlan0";
    const apIpv4 = data.ap_ipv4 || "-";
    const configured = data.configured ? "是" : "否";
    const message = data.message ? `，消息: ${data.message}` : "";
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
      setMdnsLabel("未提供");
    }
    setWifiText(
      `模式: ${mode} | 活动连接: ${active} | 接口: ${iface} | AP地址: ${apIpv4} | 已配置: ${configured}${message}`,
    );
  }, []);

  const refreshStatus = useCallback(async () => {
    const data = await requestJson<WifiPayload>("/api/network/wifi", { cache: "no-store" });
    renderWifi(data);
  }, [renderWifi]);

  useEffect(() => {
    refreshStatus().catch((err: Error) => setWifiText(`获取状态失败: ${err.message}`));
  }, [refreshStatus]);

  const switchMode = async (mode: string) => {
    setWifiText(`正在切换到 ${mode.toUpperCase()}...`);
    const data = await requestJson<WifiPayload>("/api/network/wifi", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    renderWifi(data);
  };

  const runScan = async () => {
    setScanBusy(true);
    setScanStatus("扫描中...");
    setNetworks([]);
    try {
      const res = await requestJson<{ networks?: ScanNetwork[]; hint?: string }>(
        "/api/network/wifi/scan",
        { cache: "no-store" },
      );
      const list = res.networks || [];
      const hint = res.hint ? ` ${res.hint}` : "";
      setNetworks(list);
      setScanStatus(`扫描到 ${list.length} 个网络${hint}`.trim());
    } catch (e) {
      setScanStatus(`扫描失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setScanBusy(false);
    }
  };

  const connectSsid = async (ssid: string) => {
    const pwd = window.prompt(`输入密码: ${ssid}`, "");
    if (pwd === null) return;
    setManualHint("");
    setWifiText("正在连接...");
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
          ? `连接成功，当前连接: ${data.active_connection || "—"}`
          : `连接请求已提交，当前模式: ${m}，连接: ${data.active_connection || "—"}`,
      );
      window.setTimeout(() => void refreshStatus().catch(() => {}), 2500);
    } catch (e) {
      setWifiText(`连接失败: ${e instanceof Error ? e.message : String(e)}`);
      setManualHint(`错误详情: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setStaBusy(false);
    }
  };

  const connectManual = async () => {
    const ssid = manualSsid.trim();
    if (!ssid) {
      window.alert("请输入 SSID");
      return;
    }
    setManualHint("");
    setWifiText("正在连接...");
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
          ? `连接成功，当前连接: ${data.active_connection || "—"}`
          : `连接请求已提交，当前模式: ${m}，连接: ${data.active_connection || "—"}`,
      );
      window.setTimeout(() => void refreshStatus().catch(() => {}), 2500);
    } catch (e) {
      setWifiText(`连接失败: ${e instanceof Error ? e.message : String(e)}`);
      setManualHint(`错误详情: ${e instanceof Error ? e.message : String(e)}`);
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
      setWifiText("已发送激活请求");
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
    setLanStatus("扫描中...");
    const bases = ["192.168.0", "192.168.1", "192.168.31", "10.0.0"];
    for (const base of bases) {
      const ips: string[] = [];
      for (let i = 1; i < 255; i++) ips.push(`${base}.${i}`);
      for (let i = 0; i < ips.length; i += 48) {
        const chunk = ips.slice(i, i + 48);
        const results = await Promise.all(chunk.map((ip) => probeHealth(ip, port)));
        const hit = results.find(Boolean);
        if (hit) {
          setLanStatus(`已找到设备: ${hit}`);
          window.location.href = `${hit}/debug`;
          return;
        }
      }
    }
    setLanStatus("未找到设备");
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
      ["平台", String(info.platform ?? "—")],
      ["系统", String(info.os ?? "—")],
      ["CPU 占用", `${Number(info.cpu_usage ?? 0).toFixed(1)}%`],
      ["内存占用", `${Number(info.memory_usage ?? 0).toFixed(1)}%`],
      ["CPU 温度", `${Number(info.temperature ?? 0).toFixed(1)} °C`],
      ["运行时长", formatUptime(info.uptime_seconds)],
      ["1 分钟负载", String(info.load_average_1m ?? "—")],
      ["WiFi 质量", wifiQ],
      ["WiFi 信号", wifiSig],
    ] as [string, string][];
  }, [info]);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <header>
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-on-surface-variant">
          <span>Console</span>
          <span>/</span>
          <span className="text-primary">System_Network_Debug</span>
        </div>
        <h2 className="mt-1 font-headline text-3xl font-black tracking-tight">NETWORK TERMINAL</h2>
        <p className="text-sm text-on-surface-variant">WiFi 管理、模式切换、发现与恢复工具</p>
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
                  AP 地址：<span className="font-mono text-on-surface">{apHint}</span>
                </p>
                <p>
                  mDNS：{" "}
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
                  <Search className="h-3.5 w-3.5" /> 扫描 WiFi
                </span>
              </button>
            </div>
            <p className="mb-3 text-xs text-on-surface-variant">{scanStatus || "由设备端 NetworkManager 执行扫描"}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-outline-variant/30 text-xs uppercase tracking-wider text-on-surface-variant">
                    <th className="p-2">SSID</th>
                    <th className="p-2">信号</th>
                    <th className="p-2">安全</th>
                    <th className="p-2 text-right">操作</th>
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
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider">Known Networks</h3>
            <button
              type="button"
              disabled={profBusy}
              className="rounded border border-outline-variant/40 px-3 py-1.5 text-xs disabled:opacity-50"
              onClick={() => void refreshProfiles()}
            >
              刷新已保存网络
            </button>
            <table className="mt-3 w-full text-left text-sm">
              <thead>
                <tr className="border-b border-outline-variant/30 text-xs uppercase tracking-wider text-on-surface-variant">
                  <th className="p-2">连接名</th>
                  <th className="p-2">SSID</th>
                  <th className="p-2">自动连接</th>
                  <th className="p-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.connection_name} className="border-b border-outline-variant/10">
                    <td className="p-2">{p.connection_name}</td>
                    <td className="p-2">{p.ssid}</td>
                    <td className="p-2">{p.autoconnect ? "是" : "否"}</td>
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
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider">System Monitor</h3>
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
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider">Manual Connect</h3>
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
                连接并切换 STA
              </button>
            </div>
            <p className="mt-2 text-xs text-on-surface-variant">{manualHint}</p>
          </div>

          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider">WiFi 引导</h3>
            <ol className="list-decimal space-y-1 pl-4 text-xs text-on-surface-variant">
              <li>连接热点 <strong>{wizardSsid}</strong>，密码 <code>ogscopeadmin</code></li>
              <li>浏览器打开 <span className="font-mono">http://192.168.4.1:{httpPort()}</span></li>
              <li>扫描 WiFi 或手动填写 SSID 连接</li>
            </ol>
          </div>

          <div className="rounded-xl border border-outline-variant/20 bg-surface-container p-4">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider">Find Device</h3>
            <p className="mb-3 text-xs text-on-surface-variant">扫描常见网段并探测 /health</p>
            <button
              type="button"
              className="w-full rounded border border-outline-variant/40 px-3 py-2 text-sm hover:border-primary"
              onClick={() => void scanLan()}
            >
              扫描局域网
            </button>
            <p className="mt-2 text-xs text-on-surface-variant">{lanStatus}</p>
          </div>
        </aside>
      </section>
    </div>
  );
}
