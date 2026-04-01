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
}

window.addEventListener("DOMContentLoaded", boot);
