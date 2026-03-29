(function () {
  const state = {
    uploadedFileName: null,
    uploadedFileSignature: null,
    uploadList: [],
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

  function fileSignature(file) {
    if (!file) return null;
    return `${file.name}:${file.size}:${file.lastModified}`;
  }

  function formatBytes(n) {
    if (n == null || Number.isNaN(n)) return "—";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(2)} MB`;
  }

  function isImageFilename(name) {
    return /\.(jpe?g|png|webp|bmp|gif|fits?)$/i.test(name);
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

  function readCentroidParamsForBody() {
    const o = {};
    const sigma = parseFloat($("centroid-sigma").value);
    if (!Number.isNaN(sigma)) o.sigma = sigma;
    const maxArea = parseInt($("centroid-max-area").value, 10);
    if (!Number.isNaN(maxArea)) o.max_area = maxArea;
    const minArea = parseInt($("centroid-min-area").value, 10);
    if (!Number.isNaN(minArea)) o.min_area = minArea;
    const filtsize = parseInt($("centroid-filtsize").value, 10);
    if (!Number.isNaN(filtsize)) {
      if (filtsize % 2 === 0) {
        throw new Error("filtsize 须为奇数 / filtsize must be odd");
      }
      o.filtsize = filtsize;
    }
    const binOpen = $("centroid-binary-open");
    if (binOpen) o.binary_open = binOpen.checked;
    const mar = $("centroid-max-axis-ratio").value.trim();
    if (mar !== "") {
      const v = parseFloat(mar);
      if (Number.isNaN(v)) {
        throw new Error("max_axis_ratio 无效 / invalid max_axis_ratio");
      }
      o.max_axis_ratio = v;
    }
    return o;
  }

  function readMaxImageSide() {
    const v = parseInt($("centroid-max-image-side").value, 10);
    if (Number.isNaN(v) || v < 256) return undefined;
    return v;
  }

  function buildSolveImageBody() {
    if (!state.uploadedFileName) {
      throw new Error(
        "请先上传或选择服务器上的图片 / Upload or pick a server file first"
      );
    }
    const body = {
      input_name: state.uploadedFileName,
      ...readSolverBody(),
    };
    const centroid = readCentroidParamsForBody();
    if (Object.keys(centroid).length > 0) body.centroid = centroid;
    const mis = readMaxImageSide();
    if (mis !== undefined) body.max_image_side = mis;
    return body;
  }

  function resetCentroidDefaults() {
    document.querySelectorAll(".card-centroid [data-default]").forEach((el) => {
      if (el.type === "checkbox") {
        el.checked = el.getAttribute("data-default-checked") === "true";
      } else {
        el.value = el.getAttribute("data-default") || "";
      }
    });
  }

  function clearServerUploadSelect() {
    const sel = $("server-upload-select");
    if (sel) sel.value = "";
  }

  function formatNum(v, digits) {
    if (v === undefined || v === null || Number.isNaN(v)) return "—";
    return Number(v).toFixed(digits);
  }

  function formatMsLine(ms) {
    if (ms == null || Number.isNaN(ms)) return "—";
    const m = Number(ms);
    const sec = (m / 1000).toFixed(1);
    return `${m.toFixed(0)} ms（约 ${sec} s）`;
  }

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
      ["T_extract", formatMsLine(result.t_extract_ms)],
      ["T_solve", formatMsLine(result.t_solve_ms)],
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
    clearServerUploadSelect();
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

  function showPreviewFromServer(filename) {
    const wrap = $("solve-preview-wrap");
    const imgEl = $("solve-preview-img");
    if (!wrap || !imgEl) return;
    if (state.previewObjectUrl) {
      URL.revokeObjectURL(state.previewObjectUrl);
      state.previewObjectUrl = null;
    }
    if (!isImageFilename(filename)) {
      wrap.hidden = true;
      return;
    }
    const url = `/api/analysis/uploads/file?filename=${encodeURIComponent(filename)}`;
    imgEl.onload = () => {
      wrap.hidden = false;
      refreshOverlayDraw();
    };
    imgEl.src = url;
  }

  async function refreshUploadList(selectFilename) {
    const data = await request("/api/analysis/uploads");
    state.uploadList = data.files || [];
    const sel = $("server-upload-select");
    if (!sel) return;
    const keep = selectFilename || sel.value || "";
    sel.innerHTML =
      '<option value="">（选择已上传文件，无需重复上传）</option>';
    for (const f of state.uploadList) {
      const opt = document.createElement("option");
      opt.value = f.filename;
      opt.textContent = `${f.filename} (${formatBytes(f.size)})`;
      sel.appendChild(opt);
    }
    if (keep && [...sel.options].some((o) => o.value === keep)) {
      sel.value = keep;
    }
  }

  function onServerUploadSelect() {
    const sel = $("server-upload-select");
    if (!sel) return;
    const name = sel.value;
    if (!name) return;
    state.uploadedFileName = name;
    state.uploadedFileSignature = `__server__:${name}`;
    const fileInput = $("analysis-file");
    if (fileInput) fileInput.value = "";
    showPreviewFromServer(name);
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

  function setUploadProgressVisible(visible) {
    const el = $("upload-progress-wrap");
    if (el) el.hidden = !visible;
    const btn = $("upload-btn");
    if (btn) btn.setAttribute("aria-busy", visible ? "true" : "false");
  }

  function setSolveProgressVisible(visible) {
    const el = $("solve-progress-wrap");
    if (el) el.hidden = !visible;
    const btn = $("solve-image-btn");
    if (btn) btn.setAttribute("aria-busy", visible ? "true" : "false");
  }

  async function uploadFileInternal(file) {
    const fd = new FormData();
    fd.append("file", file);
    const data = await request("/api/analysis/upload", {
      method: "POST",
      body: fd,
    });
    state.uploadedFileName = data.filename;
    state.uploadedFileSignature = fileSignature(file);
    setOutput("analysis-output", data);
    if (file.type.startsWith("image/")) {
      showPreviewFromFile(file);
    }
    refreshUploadList(data.filename).catch(() => null);
    return data;
  }

  async function onUpload() {
    const fileInput = $("analysis-file");
    if (!fileInput.files || fileInput.files.length === 0) {
      throw new Error("请先选择文件 / Please choose a file");
    }
    const file = fileInput.files[0];
    setUploadProgressVisible(true);
    try {
      await uploadFileInternal(file);
    } finally {
      setUploadProgressVisible(false);
    }
  }

  async function onSolveImage() {
    const fileInput = $("analysis-file");
    const file =
      fileInput && fileInput.files && fileInput.files.length > 0
        ? fileInput.files[0]
        : null;

    if (file) {
      const sig = fileSignature(file);
      const needUpload =
        !state.uploadedFileName ||
        sig !== state.uploadedFileSignature ||
        sig === null;
      if (needUpload) {
        setUploadProgressVisible(true);
        try {
          await uploadFileInternal(file);
        } finally {
          setUploadProgressVisible(false);
        }
      }
    } else if (!state.uploadedFileName) {
      throw new Error(
        "请先选择图片并上传，或使用「直接解算」前在本地选好文件。"
      );
    }

    setSolveProgressVisible(true);
    try {
      const data = await request("/api/analysis/solve/image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildSolveImageBody()),
      });
      setOutput("analysis-output", data);
      if (data && data.result) {
        applySolveResultToPreview(data.result);
      }
    } finally {
      setSolveProgressVisible(false);
    }
  }

  async function onCentroidPreview() {
    if (!state.uploadedFileName) {
      throw new Error(
        "请先上传或选择服务器上的图片 / Upload or pick a server file first"
      );
    }
    const body = {
      input_name: state.uploadedFileName,
      centroid: readCentroidParamsForBody(),
      max_image_side: readMaxImageSide(),
    };
    if (Object.keys(body.centroid).length === 0) delete body.centroid;
    setSolveProgressVisible(true);
    try {
      const data = await request("/api/analysis/extract/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setOutput("analysis-output", data);
      const wrap = $("centroid-preview-wrap");
      const img = $("centroid-mask-img");
      if (data && data.binary_mask_png_base64 && img) {
        img.src = "data:image/png;base64," + data.binary_mask_png_base64;
        if (wrap) wrap.hidden = false;
      } else if (wrap) {
        wrap.hidden = true;
      }
    } finally {
      setSolveProgressVisible(false);
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
    if (!node) {
      console.warn(
        `[debug-analysis] 缺少 DOM #${id}，按钮未绑定 / Missing #${id}, click not bound`
      );
      return;
    }
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
      clearServerUploadSelect();
      if (fileInput.files && fileInput.files.length > 0) {
        const f = fileInput.files[0];
        if (f.type.startsWith("image/")) {
          showPreviewFromFile(f);
        }
      }
    });
  }

  function setupServerUploadControls() {
    const sel = $("server-upload-select");
    const btn = $("refresh-uploads-btn");
    if (sel) sel.addEventListener("change", onServerUploadSelect);
    if (btn) {
      btn.addEventListener("click", async () => {
        try {
          await refreshUploadList();
        } catch (error) {
          setOutput("analysis-output", String(error));
        }
      });
    }
  }

  bindClick("upload-btn", onUpload);
  bindClick("solve-image-btn", onSolveImage);
  bindClick("centroid-reset-btn", resetCentroidDefaults);
  bindClick("centroid-preview-btn", onCentroidPreview);
  bindClick("create-video-job-btn", onCreateVideoJob);
  bindClick("query-job-btn", onQueryJob);
  bindClick("realtime-start-btn", onRealtimeStart);
  bindClick("realtime-stop-btn", onRealtimeStop);
  bindClick("realtime-status-btn", onRealtimeStatus);
  setupAutoPoll();
  setupStreamEmbed();
  setupLayerToggles();
  setupFileInputPreview();
  setupServerUploadControls();
  setupResizeSync();
  refreshUploadList().catch(() => null);
})();
