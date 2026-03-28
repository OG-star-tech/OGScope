(function () {
  const state = {
    uploadedFileName: null,
    lastJobId: null,
    pollTimer: null,
    previewObjectUrl: null,
    lastSolveOverlay: null,
    lastSolveResult: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function setOutput(id, payload) {
    const node = $(id);
    if (!node) return;
    node.textContent =
      typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
  }

  async function request(url, options = {}) {
    const resp = await fetch(url, options);
    const contentType = resp.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await resp.json()
      : await resp.text();
    if (!resp.ok) {
      throw new Error(
        typeof data === "string" ? data : data.detail || "请求失败 / Request failed"
      );
    }
    return data;
  }

  function readSolverQueryParams() {
    const fov = parseFloat($("fov-estimate").value);
    const fovMax = $("fov-max-error").value.trim();
    const timeout = $("solve-timeout-ms").value.trim();
    const hintRa = $("hint-ra").value.trim();
    const hintDec = $("hint-dec").value.trim();
    const params = new URLSearchParams();
    if (!Number.isNaN(fov)) params.set("fov_estimate", String(fov));
    if (fovMax !== "") params.set("fov_max_error", fovMax);
    if (timeout !== "") params.set("solve_timeout_ms", timeout);
    if (hintRa !== "") params.set("hint_ra_deg", hintRa);
    if (hintDec !== "") params.set("hint_dec_deg", hintDec);
    return params;
  }

  function readSolverBody() {
    const fov = parseFloat($("fov-estimate").value);
    const fovMax = $("fov-max-error").value.trim();
    const timeout = $("solve-timeout-ms").value.trim();
    const hintRa = $("hint-ra").value.trim();
    const hintDec = $("hint-dec").value.trim();
    const body = {};
    if (!Number.isNaN(fov)) body.fov_estimate = fov;
    if (fovMax !== "") body.fov_max_error = parseFloat(fovMax);
    if (timeout !== "") body.solve_timeout_ms = parseInt(timeout, 10);
    if (hintRa !== "") body.hint_ra_deg = parseFloat(hintRa);
    if (hintDec !== "") body.hint_dec_deg = parseFloat(hintDec);
    return body;
  }

  function formatNum(v, digits) {
    if (v === undefined || v === null || Number.isNaN(v)) return "—";
    return Number(v).toFixed(digits);
  }

  /**
   * 将解算摘要写入左上角浮层 / Fill summary panel from solve result.
   * 与视频/实时流可复用同一 payload 形状 / Same shape for video/live later.
   */
  function renderSolveOverlayPanel(result) {
    const panel = $("solve-overlay-panel");
    if (!panel) return;
    if (!result || typeof result !== "object") {
      panel.innerHTML = "";
      return;
    }
    const rows = [
      ["RA°", formatNum(result.ra_deg, 4)],
      ["Dec°", formatNum(result.dec_deg, 4)],
      ["FOV°", formatNum(result.fov_deg, 3)],
      ["Roll°", formatNum(result.roll_deg, 2)],
      ["Matches", result.matches != null ? String(result.matches) : "—"],
      ["RMSE″", formatNum(result.rmse_arcsec, 2)],
      ["Prob", formatNum(result.prob, 4)],
      ["Status", result.status != null ? String(result.status) : "—"],
    ];
    const parts = ["<dl>"];
    for (const [k, v] of rows) {
      parts.push(`<dt>${k}</dt><dd>${v}</dd>`);
    }
    parts.push("</dl>");
    panel.innerHTML = parts.join("");
  }

  /**
   * 在 canvas 上绘制叠加（与图像像素坐标一致）/ Draw overlay in image pixel coords.
   */
  function drawSolveOverlay(canvas, img, overlay, layers) {
    if (!canvas || !img || !overlay) return;
    const w = img.naturalWidth || 1;
    const h = img.naturalHeight || 1;
    canvas.width = w;
    canvas.height = h;
    canvas.style.width = `${img.clientWidth}px`;
    canvas.style.height = `${img.clientHeight}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);

    const drawAll = layers && layers.all;
    const drawPat = layers && layers.pattern;
    const drawMat = layers && layers.matched;

    if (drawAll && Array.isArray(overlay.stars_all_centroids)) {
      ctx.fillStyle = "rgba(156, 163, 175, 0.85)";
      for (const s of overlay.stars_all_centroids) {
        const x = s.x;
        const y = s.y;
        ctx.beginPath();
        ctx.arc(x, y, 2.4, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    if (drawPat && Array.isArray(overlay.stars_pattern)) {
      ctx.strokeStyle = "rgba(251, 146, 60, 0.95)";
      ctx.lineWidth = 2;
      for (const s of overlay.stars_pattern) {
        ctx.beginPath();
        ctx.arc(s.x, s.y, 6, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    if (drawMat && Array.isArray(overlay.stars_matched)) {
      ctx.strokeStyle = "rgba(34, 197, 94, 0.95)";
      ctx.fillStyle = "rgba(34, 197, 94, 0.95)";
      ctx.lineWidth = 2;
      ctx.font = "11px system-ui, sans-serif";
      for (const s of overlay.stars_matched) {
        ctx.beginPath();
        ctx.arc(s.x, s.y, 7, 0, Math.PI * 2);
        ctx.stroke();
        if (s.mag != null) {
          const label = `m${formatNum(s.mag, 1)}`;
          ctx.fillText(label, s.x + 4, s.y - 4);
        }
      }
    }
  }

  function readLayerToggles() {
    return {
      matched: $("layer-matched") && $("layer-matched").checked,
      pattern: $("layer-pattern") && $("layer-pattern").checked,
      all: $("layer-all") && $("layer-all").checked,
    };
  }

  function refreshOverlayDraw() {
    const img = $("solve-preview-img");
    const canvas = $("solve-preview-canvas");
    if (!img || !canvas || !state.lastSolveOverlay) return;
    drawSolveOverlay(canvas, img, state.lastSolveOverlay, readLayerToggles());
  }

  function setupResizeSync() {
    const img = $("solve-preview-img");
    if (!img || !window.ResizeObserver) return;
    const ro = new ResizeObserver(() => {
      refreshOverlayDraw();
    });
    ro.observe(img);
  }

  function showPreviewFromFile(file) {
    const wrap = $("solve-preview-wrap");
    const img = $("solve-preview-img");
    if (!wrap || !img) return;
    if (state.previewObjectUrl) {
      URL.revokeObjectURL(state.previewObjectUrl);
      state.previewObjectUrl = null;
    }
    state.previewObjectUrl = URL.createObjectURL(file);
    img.onload = () => {
      wrap.hidden = false;
      refreshOverlayDraw();
    };
    img.src = state.previewObjectUrl;
  }

  function applySolveResultToPreview(result) {
    state.lastSolveResult = result;
    state.lastSolveOverlay = result && result.solve_overlay ? result.solve_overlay : null;
    renderSolveOverlayPanel(result);
    const img = $("solve-preview-img");
    if (!img) return;
    if (img.complete && img.naturalWidth) {
      refreshOverlayDraw();
    } else {
      img.addEventListener("load", () => refreshOverlayDraw(), { once: true });
    }
  }

  async function onUpload() {
    const fileInput = $("analysis-file");
    if (!fileInput.files || fileInput.files.length === 0) {
      throw new Error("请先选择文件 / Please choose a file");
    }
    const file = fileInput.files[0];
    const fd = new FormData();
    fd.append("file", file);
    const data = await request("/api/analysis/upload", {
      method: "POST",
      body: fd,
    });
    state.uploadedFileName = data.filename;
    setOutput("analysis-output", data);
    if (file.type.startsWith("image/")) {
      showPreviewFromFile(file);
    }
  }

  async function onSolveImage() {
    if (!state.uploadedFileName) {
      throw new Error("请先上传图片 / Please upload an image first");
    }
    const params = readSolverQueryParams();
    params.set("input_name", state.uploadedFileName);
    const data = await request(`/api/analysis/solve/image?${params.toString()}`, {
      method: "POST",
    });
    setOutput("analysis-output", data);
    if (data && data.result) {
      applySolveResultToPreview(data.result);
    }
  }

  async function onCreateVideoJob() {
    if (!state.uploadedFileName) {
      throw new Error("请先上传视频 / Please upload a video first");
    }
    const frame_step = Number($("frame-step").value);
    const max_frames = Number($("max-frames").value);
    const body = {
      input_name: state.uploadedFileName,
      input_type: "video",
      frame_step,
      max_frames,
      ...readSolverBody(),
    };
    const data = await request("/api/analysis/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    state.lastJobId = data.job_id;
    setOutput("analysis-output", data);
  }

  async function onQueryJob() {
    if (!state.lastJobId) {
      throw new Error("暂无任务ID / No job id");
    }
    const status = await request(`/api/analysis/jobs/${state.lastJobId}`);
    let result = null;
    if (status.status === "succeeded") {
      result = await request(`/api/analysis/jobs/${state.lastJobId}/result`);
    }
    setOutput("analysis-output", { status, result });
  }

  async function onRealtimeStart() {
    const params = readSolverQueryParams();
    const data = await request(
      `/api/debug/analysis/realtime/start?${params.toString()}`,
      { method: "POST" }
    );
    setOutput("realtime-output", data);
  }

  async function onRealtimeStop() {
    const data = await request("/api/debug/analysis/realtime/stop", {
      method: "POST",
    });
    setOutput("realtime-output", data);
  }

  async function onRealtimeStatus() {
    const data = await request("/api/debug/analysis/realtime/status");
    setOutput("realtime-output", data);
  }

  function bindClick(id, handler) {
    const node = $(id);
    if (!node) return;
    node.addEventListener("click", async () => {
      try {
        await handler();
      } catch (error) {
        setOutput("analysis-output", String(error));
        setOutput("realtime-output", String(error));
      }
    });
  }

  function setupAutoPoll() {
    const checkbox = $("auto-poll-status");
    if (!checkbox) return;
    checkbox.addEventListener("change", () => {
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
      if (checkbox.checked) {
        state.pollTimer = setInterval(() => {
          onRealtimeStatus().catch(() => null);
        }, 2000);
      }
    });
    checkbox.dispatchEvent(new Event("change"));
  }

  function setupStreamEmbed() {
    const cb = $("embed-stream");
    const container = $("stream-container");
    const img = $("stream-img");
    if (!cb || !container || !img) return;
    cb.addEventListener("change", () => {
      if (cb.checked) {
        container.hidden = false;
        img.src = "/api/debug/camera/stream?quality=60";
      } else {
        container.hidden = true;
        img.removeAttribute("src");
      }
    });
  }

  function setupLayerToggles() {
    ["layer-matched", "layer-pattern", "layer-all"].forEach((id) => {
      const el = $(id);
      if (el) el.addEventListener("change", () => refreshOverlayDraw());
    });
  }

  function setupFileInputPreview() {
    const fileInput = $("analysis-file");
    if (!fileInput) return;
    fileInput.addEventListener("change", () => {
      if (fileInput.files && fileInput.files.length > 0) {
        const f = fileInput.files[0];
        if (f.type.startsWith("image/")) {
          showPreviewFromFile(f);
        }
      }
    });
  }

  bindClick("upload-btn", onUpload);
  bindClick("solve-image-btn", onSolveImage);
  bindClick("create-video-job-btn", onCreateVideoJob);
  bindClick("query-job-btn", onQueryJob);
  bindClick("realtime-start-btn", onRealtimeStart);
  bindClick("realtime-stop-btn", onRealtimeStop);
  bindClick("realtime-status-btn", onRealtimeStatus);
  setupAutoPoll();
  setupStreamEmbed();
  setupLayerToggles();
  setupFileInputPreview();
  setupResizeSync();
})();
