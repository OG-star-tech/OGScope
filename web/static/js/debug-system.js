/* OGScope 系统调试控制台 / OGScope system debug console */

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
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

function renderStatus(data) {
  const box = document.getElementById("wifi-status");
  const apUrlHint = document.getElementById("ap-url-hint");
  const mode = data.mode || "unknown";
  const active = data.active_connection || "-";
  const iface = data.wireless_interface || "wlan0";
  const apIpv4 = data.ap_ipv4 || "-";
  const configured = data.configured ? "是" : "否";
  const message = data.message ? `，消息: ${data.message}` : "";
  if (data.ap_url_hint) {
    apUrlHint.textContent = data.ap_url_hint;
  }
  box.textContent =
    `模式: ${mode} | 活动连接: ${active} | 接口: ${iface} | AP地址: ${apIpv4} | 已配置: ${configured}${message}`;
}

async function refreshStatus() {
  const data = await requestJson("/api/network/wifi");
  renderStatus(data);
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
    const info = await requestJson("/api/system/info");
    renderSystemInfo(info);
  } catch (err) {
    if (statusEl) statusEl.textContent = `加载失败: ${err.message}`;
  }
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
  refreshStatus().catch((err) => {
    document.getElementById("wifi-status").textContent = `获取状态失败: ${err.message}`;
  });

  refreshSystemInfo();
  if (systemInfoTimer) clearInterval(systemInfoTimer);
  systemInfoTimer = setInterval(refreshSystemInfo, 8000);
}

window.addEventListener("DOMContentLoaded", boot);
