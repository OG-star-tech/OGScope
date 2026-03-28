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
    const params = readSolverQueryParams();
    params.set("input_name", state.uploadedFileName);
    const data = await request(`/api/analysis/solve/image?${params.toString()}`, {
      method: "POST",
    });
    setOutput("analysis-output", data);
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

  bindClick("upload-btn", onUpload);
  bindClick("solve-image-btn", onSolveImage);
  bindClick("create-video-job-btn", onCreateVideoJob);
  bindClick("query-job-btn", onQueryJob);
  bindClick("realtime-start-btn", onRealtimeStart);
  bindClick("realtime-stop-btn", onRealtimeStop);
  bindClick("realtime-status-btn", onRealtimeStatus);
  setupAutoPoll();
  setupStreamEmbed();
})();
