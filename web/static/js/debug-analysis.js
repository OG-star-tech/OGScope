(function () {
  const state = {
    uploadedFileName: null,
    lastJobId: null,
    pollTimer: null,
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

  async function onCatalogDownload() {
    const source = $("catalog-source").value;
    const url = $("catalog-url").value.trim() || null;
    const magnitude_limit = Number($("magnitude-limit").value);
    const data = await request("/api/catalog/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, url, magnitude_limit }),
    });
    setOutput("catalog-status", data);
  }

  async function onCatalogBuild() {
    const magnitude_limit = Number($("magnitude-limit").value);
    const ra_bin_size_deg = Number($("ra-bin-size").value);
    const data = await request("/api/catalog/build-index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ magnitude_limit, ra_bin_size_deg }),
    });
    setOutput("catalog-status", data);
  }

  async function onCatalogStatus() {
    const data = await request("/api/catalog/status");
    setOutput("catalog-status", data);
  }

  function readStarPayload() {
    return {
      source_id: $("star-source-id").value.trim(),
      ra: Number($("star-ra").value),
      dec: Number($("star-dec").value),
      pmra: Number($("star-pmra").value),
      pmdec: Number($("star-pmdec").value),
      phot_g_mean_mag: Number($("star-mag").value),
      name_en: $("star-name-en").value.trim(),
      name_zh: $("star-name-zh").value.trim(),
      description_en: $("star-desc-en").value.trim(),
      description_zh: $("star-desc-zh").value.trim(),
    };
  }

  async function onStarCreate() {
    const payload = readStarPayload();
    const data = await request("/api/catalog/stars", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setOutput("star-output", data);
  }

  async function onStarUpdate() {
    const payload = readStarPayload();
    const sid = payload.source_id;
    const data = await request(`/api/catalog/stars/${encodeURIComponent(sid)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setOutput("star-output", data);
  }

  async function onStarDelete() {
    const sid = $("star-source-id").value.trim();
    const data = await request(`/api/catalog/stars/${encodeURIComponent(sid)}`, {
      method: "DELETE",
    });
    setOutput("star-output", data);
  }

  async function onStarGet() {
    const sid = $("star-source-id").value.trim();
    const data = await request(`/api/catalog/stars/${encodeURIComponent(sid)}`);
    setOutput("star-output", data);
  }

  async function onStarList() {
    const q = $("star-query").value.trim();
    const params = new URLSearchParams({ limit: "50", offset: "0" });
    if (q) params.set("source_query", q);
    const data = await request(`/api/catalog/stars?${params.toString()}`);
    setOutput("star-output", data);
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
  }

  async function onSolveImage() {
    if (!state.uploadedFileName) {
      throw new Error("请先上传图片 / Please upload an image first");
    }
    const hint_ra_deg = Number($("hint-ra").value);
    const hint_dec_deg = Number($("hint-dec").value);
    const params = new URLSearchParams({
      input_name: state.uploadedFileName,
      hint_ra_deg: String(hint_ra_deg),
      hint_dec_deg: String(hint_dec_deg),
    });
    const data = await request(`/api/analysis/solve/image?${params.toString()}`, {
      method: "POST",
    });
    setOutput("analysis-output", data);
  }

  async function onCreateVideoJob() {
    if (!state.uploadedFileName) {
      throw new Error("请先上传视频 / Please upload a video first");
    }
    const hint_ra_deg = Number($("hint-ra").value);
    const hint_dec_deg = Number($("hint-dec").value);
    const frame_step = Number($("frame-step").value);
    const max_frames = Number($("max-frames").value);
    const data = await request("/api/analysis/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input_name: state.uploadedFileName,
        input_type: "video",
        hint_ra_deg,
        hint_dec_deg,
        frame_step,
        max_frames,
      }),
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
    const hint_ra_deg = Number($("hint-ra").value);
    const hint_dec_deg = Number($("hint-dec").value);
    const params = new URLSearchParams({
      hint_ra_deg: String(hint_ra_deg),
      hint_dec_deg: String(hint_dec_deg),
    });
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

  bindClick("catalog-download-btn", onCatalogDownload);
  bindClick("catalog-build-btn", onCatalogBuild);
  bindClick("catalog-status-btn", onCatalogStatus);
  bindClick("star-create-btn", onStarCreate);
  bindClick("star-update-btn", onStarUpdate);
  bindClick("star-delete-btn", onStarDelete);
  bindClick("star-get-btn", onStarGet);
  bindClick("star-list-btn", onStarList);
  bindClick("upload-btn", onUpload);
  bindClick("solve-image-btn", onSolveImage);
  bindClick("create-video-job-btn", onCreateVideoJob);
  bindClick("query-job-btn", onQueryJob);
  bindClick("realtime-start-btn", onRealtimeStart);
  bindClick("realtime-stop-btn", onRealtimeStop);
  bindClick("realtime-status-btn", onRealtimeStatus);
  setupAutoPoll();
  onCatalogStatus().catch(() => null);
})();
