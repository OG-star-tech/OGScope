/* OGScope 系统调试控制台 / OGScope system debug console */

async function requestJson(url, options = {}) {
  const { cache, ...rest } = options;
  const fetchOpts = {
    headers: { "Content-Type": "application/json" },
    ...rest,
  };
  if (cache !== undefined) {
    fetchOpts.cache = cache;
  }
  const response = await fetch(url, fetchOpts);
  let data = {};
  try {
    data = await response.json();
  } catch (_e) {
    // ignore
  }
  if (!response.ok) {
    const detail = data.detail || `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return data;
}

function httpPort() {
  return typeof window.OGSCOPE_HTTP_PORT === "number" ? window.OGSCOPE_HTTP_PORT : 8000;
}

function renderStatus(data) {
  const box = document.getElementById("wifi-status");
  const apUrlHint = document.getElementById("ap-url-hint");
  const wizardAp = document.getElementById("wizard-ap-ssid");
  const wizardUrl = document.getElementById("wizard-ap-url");
  const mdnsLink = document.getElementById("mdns-hint-link");
  const mode = data.mode || "unknown";
  const active = data.active_connection || "-";
  const iface = data.wireless_interface || "wlan0";
  const apIpv4 = data.ap_ipv4 || "-";
  const configured = data.configured ? "是" : "否";
  const message = data.message ? `，消息: ${data.message}` : "";
  if (data.ap_url_hint) {
    apUrlHint.textContent = data.ap_url_hint;
  }
  if (wizardAp && data.ap_ssid) {
    wizardAp.textContent = data.ap_ssid;
  }
  if (wizardUrl) {
    wizardUrl.textContent = `http://192.168.4.1:${httpPort()}`;
  }
  if (mdnsLink && data.mdns_hostname_hint) {
    const host = data.mdns_hostname_hint;
    const href = `http://${host}:${httpPort()}/debug/system`;
    mdnsLink.href = href;
    mdnsLink.textContent = href;
  } else if (mdnsLink && data.device_id_suffix) {
    const host = `ogscope-${data.device_id_suffix}.local`;
    const href = `http://${host}:${httpPort()}/debug/system`;
    mdnsLink.href = href;
    mdnsLink.textContent = href;
  } else if (mdnsLink) {
    mdnsLink.textContent = "（未配置网络初始化）";
    mdnsLink.removeAttribute("href");
  }
  box.textContent =
    `模式: ${mode} | 活动连接: ${active} | 接口: ${iface} | AP地址: ${apIpv4} | 已配置: ${configured}${message}`;
}

async function refreshStatus() {
  const data = await requestJson("/api/network/wifi", { cache: "no-store" });
  renderStatus(data);
}

/** 手动/扫描连接期间禁用按钮 / Disable buttons during STA connect */
function setStaConnectBusy(busy) {
  const btn = document.getElementById("btn-manual-connect");
  if (btn) btn.disabled = busy;
  document.querySelectorAll("#scan-tbody .js-connect-scan").forEach((b) => {
    b.disabled = busy;
  });
}

async function switchMode(mode) {
  const box = document.getElementById("wifi-status");
  box.textContent = `正在切换到 ${mode.toUpperCase()}...`;
  const data = await requestJson("/api/network/wifi", {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
  renderStatus(data);
}

/** 格式化运行时长 / Format uptime */
function formatUptime(sec) {
  const s = Math.max(0, parseInt(String(sec), 10) || 0);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}天 ${h}小时`;
  if (h > 0) return `${h}小时 ${m}分`;
  return `${m}分`;
}

/** 渲染系统信息监控 / Render system info from /api/system/info */
function renderSystemInfo(info) {
  const grid = document.getElementById("system-info-grid");
  const statusEl = document.getElementById("system-info-status");
  if (!grid || !statusEl) return;
  statusEl.textContent = "";
  const wifiQ =
    info.wifi_quality != null && !Number.isNaN(Number(info.wifi_quality))
      ? `${Number(info.wifi_quality).toFixed(1)}%`
      : "—";
  const wifiSig =
    info.wifi_signal_dbm != null && !Number.isNaN(Number(info.wifi_signal_dbm))
      ? `${Number(info.wifi_signal_dbm).toFixed(0)} dBm (${info.wifi_interface || "?"})`
      : "—";
  const rows = [
    ["平台", info.platform || "—"],
    ["系统", info.os || "—"],
    ["CPU 占用", `${Number(info.cpu_usage ?? 0).toFixed(1)}%`],
    ["内存占用", `${Number(info.memory_usage ?? 0).toFixed(1)}%`],
    ["CPU 温度", `${Number(info.temperature ?? 0).toFixed(1)} °C`],
    ["运行时长", formatUptime(info.uptime_seconds)],
    ["1 分钟负载", String(info.load_average_1m ?? "—")],
    ["WiFi 质量", wifiQ],
    ["WiFi 信号", wifiSig],
  ];
  grid.innerHTML = rows
    .map(
      ([k, v]) =>
        `<div class="system-info-row"><span class="system-info-k">${escapeHtml(k)}</span><span class="system-info-v">${escapeHtml(String(v))}</span></div>`,
    )
    .join("");
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

let systemInfoTimer = null;

async function refreshSystemInfo() {
  const statusEl = document.getElementById("system-info-status");
  try {
    const info = await requestJson("/api/system/info", { cache: "no-store" });
    renderSystemInfo(info);
  } catch (err) {
    if (statusEl) statusEl.textContent = `加载失败: ${err.message}`;
  }
}

async function runScan() {
  const st = document.getElementById("scan-status");
  const tbody = document.getElementById("scan-tbody");
  const btnScan = document.getElementById("btn-scan");
  if (btnScan) btnScan.disabled = true;
  st.textContent = "扫描中（设备 nmcli，约需数秒）…";
  tbody.innerHTML = "";
  try {
    const res = await requestJson("/api/network/wifi/scan", { cache: "no-store" });
    const networks = res.networks || [];
    const hint = res.hint ? ` ${res.hint}` : "";
    st.textContent = `共 ${networks.length} 个。${hint}`.trim();
    networks.forEach((n) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(n.ssid)}</td><td>${n.signal ?? "—"}</td><td>${escapeHtml(n.security || "—")}</td><td><button type="button" class="btn btn-small js-connect-scan">连接</button></td>`;
      tr.querySelector(".js-connect-scan").addEventListener("click", () => {
        connectSsid(n.ssid);
      });
      tbody.appendChild(tr);
    });
  } catch (e) {
    st.textContent = `失败: ${e.message}`;
  } finally {
    if (btnScan) btnScan.disabled = false;
  }
}

async function connectSsid(ssid) {
  const pwd = window.prompt(`输入密码（开放网络可留空）: ${ssid}`, "");
  if (pwd === null) return;
  const box = document.getElementById("wifi-status");
  const hint = document.getElementById("manual-connect-hint");
  if (hint) hint.textContent = "";
  box.textContent = "正在连接…";
  setStaConnectBusy(true);
  try {
    const data = await requestJson("/api/network/wifi/sta/connect", {
      method: "POST",
      body: JSON.stringify({ ssid, password: pwd || null }),
    });
    renderStatus(data);
    if (hint) {
      const m = data.mode || "unknown";
      hint.textContent =
        m === "sta"
          ? `成功：当前为 STA，活动连接 ${data.active_connection || "—"}。若页面断开请用 mDNS 或局域网扫描。`
          : `已提交：当前模式 ${m}，活动连接 ${data.active_connection || "—"}。若仍为 unknown 请数秒后点「刷新状态」。`;
    }
    setTimeout(() => {
      refreshStatus().catch(() => {});
    }, 2500);
  } catch (e) {
    box.textContent = `连接失败: ${e.message}`;
    if (hint) hint.textContent = `错误详情: ${e.message}`;
  } finally {
    setStaConnectBusy(false);
  }
}

async function connectManual() {
  const ssid = document.getElementById("manual-ssid").value.trim();
  const pwd = document.getElementById("manual-pass").value;
  if (!ssid) {
    alert("请输入 SSID");
    return;
  }
  const box = document.getElementById("wifi-status");
  const hint = document.getElementById("manual-connect-hint");
  if (hint) hint.textContent = "";
  box.textContent = "正在连接…";
  setStaConnectBusy(true);
  try {
    const data = await requestJson("/api/network/wifi/sta/connect", {
      method: "POST",
      body: JSON.stringify({ ssid, password: pwd || null }),
    });
    renderStatus(data);
    if (hint) {
      const m = data.mode || "unknown";
      hint.textContent =
        m === "sta"
          ? `成功：当前为 STA，活动连接 ${data.active_connection || "—"}。若页面断开请用 mDNS 或局域网扫描。`
          : `已提交：当前模式 ${m}，活动连接 ${data.active_connection || "—"}。若仍为 unknown 请数秒后点「刷新状态」。`;
    }
    setTimeout(() => {
      refreshStatus().catch(() => {});
    }, 2500);
  } catch (e) {
    box.textContent = `连接失败: ${e.message}`;
    if (hint) hint.textContent = `错误详情: ${e.message}`;
  } finally {
    setStaConnectBusy(false);
  }
}

async function refreshProfiles() {
  const tbody = document.getElementById("profiles-tbody");
  const btnProf = document.getElementById("btn-profiles-refresh");
  if (btnProf) btnProf.disabled = true;
  tbody.innerHTML = "";
  try {
    const res = await requestJson("/api/network/wifi/profiles", { cache: "no-store" });
    (res.profiles || []).forEach((p) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(p.connection_name)}</td><td>${escapeHtml(p.ssid)}</td><td>${p.autoconnect ? "是" : "否"}</td><td><button type="button" class="btn btn-small js-act">激活</button></td>`;
      tr.querySelector(".js-act").addEventListener("click", async () => {
        try {
          await requestJson("/api/network/wifi/profile/activate", {
            method: "POST",
            body: JSON.stringify({ connection_name: p.connection_name }),
          });
          document.getElementById("wifi-status").textContent = "已激活 profile";
        } catch (e) {
          alert(e.message);
        }
      });
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4">加载失败: ${escapeHtml(e.message)}</td></tr>`;
  } finally {
    if (btnProf) btnProf.disabled = false;
  }
}

async function probeHealth(ip, port) {
  const url = `http://${ip}:${port}/health`;
  try {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 700);
    const r = await fetch(url, { signal: ac.signal, mode: "cors" });
    clearTimeout(t);
    if (!r.ok) return null;
    const j = await r.json();
    if (j && j.status === "healthy") return `http://${ip}:${port}`;
  } catch (_e) {
    // ignore
  }
  return null;
}

async function scanLan() {
  const port = httpPort();
  const statusEl = document.getElementById("lan-scan-status");
  statusEl.textContent = "扫描中（可能需 1–2 分钟）…";
  const bases = ["192.168.0", "192.168.1", "192.168.31", "10.0.0"];
  for (const base of bases) {
    const ips = [];
    for (let i = 1; i < 255; i++) ips.push(`${base}.${i}`);
    for (let i = 0; i < ips.length; i += 48) {
      const chunk = ips.slice(i, i + 48);
      const results = await Promise.all(chunk.map((ip) => probeHealth(ip, port)));
      const hit = results.find(Boolean);
      if (hit) {
        statusEl.textContent = `找到: ${hit}`;
        window.location.href = `${hit}/debug/system`;
        return;
      }
    }
  }
  statusEl.textContent = "未发现（请试 mDNS 或检查路由器网段）";
}

function boot() {
  document.getElementById("refresh").addEventListener("click", async () => {
    try {
      await refreshStatus();
    } catch (err) {
      document.getElementById("wifi-status").textContent = `刷新失败: ${err.message}`;
    }
  });
  document.getElementById("to-ap").addEventListener("click", async () => {
    try {
      await switchMode("ap");
    } catch (err) {
      document.getElementById("wifi-status").textContent = `切换失败: ${err.message}`;
    }
  });
  document.getElementById("to-sta").addEventListener("click", async () => {
    try {
      await switchMode("sta");
    } catch (err) {
      document.getElementById("wifi-status").textContent = `切换失败: ${err.message}`;
    }
  });
  const btnScan = document.getElementById("btn-scan");
  if (btnScan) btnScan.addEventListener("click", () => runScan());
  const btnMan = document.getElementById("btn-manual-connect");
  if (btnMan) btnMan.addEventListener("click", () => connectManual());
  const btnProf = document.getElementById("btn-profiles-refresh");
  if (btnProf) btnProf.addEventListener("click", () => refreshProfiles());
  const btnLan = document.getElementById("btn-lan-scan");
  if (btnLan) btnLan.addEventListener("click", () => scanLan());

  refreshStatus().catch((err) => {
    document.getElementById("wifi-status").textContent = `获取状态失败: ${err.message}`;
  });

  refreshSystemInfo();
  if (systemInfoTimer) clearInterval(systemInfoTimer);
  systemInfoTimer = setInterval(refreshSystemInfo, 8000);
}

window.addEventListener("DOMContentLoaded", boot);
