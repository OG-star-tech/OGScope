/* OGScope - 首页分析接入 / OGScope - Home analysis integration */

class OGScopeHomeApp {
    constructor() {
        this.isInitialized = false;
        this.isLoaded = false;
        this.loadingProgress = 0;
        this.loadingSteps = [
            { progress: 16, text: "正在连接相机流... / Connecting stream..." },
            { progress: 36, text: "正在读取分析配置... / Loading analysis settings..." },
            { progress: 62, text: "正在启动实时解算... / Starting realtime solver..." },
            { progress: 84, text: "正在同步页面控件... / Syncing UI controls..." },
            { progress: 100, text: "加载完成 / Ready" },
        ];
        this.currentStep = 0;
        this.loadingInterval = null;
        this.dataUpdateInterval = null;
        this.solveTimer = null;
        this.solveInFlight = false;
        this.retryTimer = null;
        this.consecutiveSolveErrors = 0;
        this.solvePausedUntil = 0;

        this.streamQuality = 60;
        this.solveIntervalMs = 1500;
        this.intervalMinMs = 500;
        this.intervalMaxMs = 10000;
        this.requestTimeoutMs = 3000;
        this.solverTimeoutMs = 1200;
        this.solveParams = {
            fov_estimate: 11,
            max_image_side: 1280,
            solve_profile: "balanced",
            detail_level: "summary",
            large_scale_bg_subtract: false,
        };
        this.overlayLayers = {
            video: true,
            all: true,
            matched: true,
            pattern: true,
            rejected: true,
        };

        this.latestResult = null;
        this.latestOverlay = null;
        this.resizeObserver = null;
        this._overlayFadeTimer = null;
        this.cameraStatus = null;
        this.lastTelemetryAt = 0;
        this.lastGuideAngle = 45;

        this.init();
    }

    async init() {
        try {
            this.showLoadingScreen();
            await this.startLoadingProcess();
            await this.bootstrapSettings();
            this.bindControls();
            window.addEventListener(
                "pagehide",
                () => {
                    const streamImg = document.getElementById("video-stream");
                    if (!streamImg) return;
                    try {
                        streamImg.onload = null;
                        streamImg.onerror = null;
                    } catch (_) {
                        /* ignore */
                    }
                    streamImg.src = "";
                    streamImg.removeAttribute("src");
                },
                { capture: false },
            );
            await this.startCameraStream();
            this.startDataUpdates();
            this.startSolveLoop();
            this.hideLoadingScreen();
            this.isInitialized = true;
            this.isLoaded = true;
        } catch (error) {
            console.error("[OGScope] 首页初始化失败:", error);
            this.handleInitializationError(error);
        }
    }

    showLoadingScreen() {
        const loadingScreen = document.getElementById("loading-screen");
        if (loadingScreen) {
            loadingScreen.classList.remove("hidden");
        }
    }

    hideLoadingScreen() {
        const loadingScreen = document.getElementById("loading-screen");
        const app = document.getElementById("app");
        if (loadingScreen) loadingScreen.classList.add("hidden");
        if (app) app.classList.add("loaded");
    }

    async startLoadingProcess() {
        return new Promise((resolve) => {
            this.loadingInterval = setInterval(() => {
                if (this.currentStep < this.loadingSteps.length) {
                    const step = this.loadingSteps[this.currentStep];
                    this.updateLoadingProgress(step.progress, step.text);
                    this.currentStep += 1;
                } else {
                    clearInterval(this.loadingInterval);
                    this.loadingInterval = null;
                    setTimeout(resolve, 250);
                }
            }, 360);
        });
    }

    updateLoadingProgress(progress, text) {
        this.loadingProgress = progress;
        const progressBar = document.getElementById("progress-bar");
        const loadingStatus = document.getElementById("loading-status");
        if (progressBar) progressBar.style.width = `${progress}%`;
        if (loadingStatus) loadingStatus.textContent = text;
    }

    async bootstrapSettings() {
        try {
            const settingsResp = await this.fetchJson("/api/analysis/settings", { timeoutMs: 2500 });
            const fps = Number(settingsResp.star_analysis_target_fps ?? 2 / 3);
            const baseMs = Math.round(1000 / Math.min(Math.max(fps, 0.2), 5));
            this.intervalMinMs = Number(settingsResp.star_analysis_min_interval_ms ?? 500);
            this.intervalMaxMs = Number(settingsResp.star_analysis_max_interval_ms ?? 10000);
            this.requestTimeoutMs = Number(settingsResp.star_analysis_request_timeout_ms ?? 3000);
            this.solveIntervalMs = this.clamp(baseMs, this.intervalMinMs, this.intervalMaxMs);
            this.solverTimeoutMs = Math.min(
                Number(settingsResp.solver_timeout_ms ?? 1500) * 0.6,
                1200,
            );
            this.solveParams.fov_estimate = Number(settingsResp.solver_fov_deg ?? 11);
            this.solveParams.max_image_side = Number(settingsResp.solver_max_image_side ?? 1280);
        } catch (e) {
            console.warn("[OGScope] 读取分析配置失败，使用默认值:", e);
        }
        this.syncAdjustControls();
    }

    bindControls() {
        const streamQuality = document.getElementById("adj-stream-quality");
        const solveInterval = document.getElementById("adj-solve-interval");
        const autoExposure = document.getElementById("adj-auto-exposure");
        const nightMode = document.getElementById("adj-night-mode");
        const streamImg = document.getElementById("video-stream");

        if (streamQuality) {
            streamQuality.addEventListener("input", (e) => {
                const v = Number(e.target.value);
                this.streamQuality = this.clamp(v, 35, 95);
                this.syncAdjustControls();
            });
            streamQuality.addEventListener("change", () => this.refreshStreamSource());
        }
        if (solveInterval) {
            solveInterval.addEventListener("input", (e) => {
                const v = Number(e.target.value);
                this.solveIntervalMs = this.clamp(v, this.intervalMinMs, this.intervalMaxMs);
                this.syncAdjustControls();
            });
            solveInterval.addEventListener("change", () => this.restartSolveLoop());
        }
        if (autoExposure) {
            autoExposure.addEventListener("click", async () => {
                const next = !Boolean(this.cameraStatus?.info?.auto_exposure);
                try {
                    await this.fetchJson(
                        `/api/debug/camera/auto-exposure?enabled=${next ? "true" : "false"}`,
                        { method: "POST", timeoutMs: 2500 },
                    );
                    await this.refreshCameraStatus();
                } catch (e) {
                    console.warn("[OGScope] 自动曝光切换失败:", e);
                }
            });
        }
        if (nightMode) {
            nightMode.addEventListener("click", async () => {
                const next = !Boolean(this.cameraStatus?.info?.night_mode);
                try {
                    await this.fetchJson(
                        `/api/debug/camera/night-mode?enabled=${next ? "true" : "false"}`,
                        { method: "POST", timeoutMs: 2500 },
                    );
                    await this.refreshCameraStatus();
                } catch (e) {
                    console.warn("[OGScope] 夜间模式切换失败:", e);
                }
            });
        }

        ["layer-video", "layer-all", "layer-matched", "layer-pattern", "layer-rejected"].forEach((id) => {
            const node = document.getElementById(id);
            if (!node) return;
            node.addEventListener("change", () => {
                this.overlayLayers.video = Boolean(document.getElementById("layer-video")?.checked);
                this.overlayLayers.all = Boolean(document.getElementById("layer-all")?.checked);
                this.overlayLayers.matched = Boolean(document.getElementById("layer-matched")?.checked);
                this.overlayLayers.pattern = Boolean(document.getElementById("layer-pattern")?.checked);
                this.overlayLayers.rejected = Boolean(document.getElementById("layer-rejected")?.checked);
                this.applyStreamLayer();
                this.renderOverlay();
            });
        });

        if (streamImg) {
            streamImg.addEventListener("load", () => this.renderOverlay());
            streamImg.addEventListener("error", () => {
                if (this.retryTimer != null) return;
                this.retryTimer = setTimeout(() => {
                    this.retryTimer = null;
                    this.refreshStreamSource();
                }, 600);
            });
        }

        window.addEventListener("resize", () => this.renderOverlay());
        window.addEventListener("orientationchange", () => {
            setTimeout(() => this.renderOverlay(), 100);
        });
        const viewportFrame = document.querySelector(".hud-viewport-frame");
        if (viewportFrame && typeof ResizeObserver !== "undefined") {
            this.resizeObserver = new ResizeObserver(() => this.renderOverlay());
            this.resizeObserver.observe(viewportFrame);
        }
        document.addEventListener("visibilitychange", () => {
            if (document.hidden) return;
            this.refreshStreamSource();
            this.renderOverlay();
        });
        window.addEventListener("beforeunload", () => this.cleanup());
    }

    syncAdjustControls() {
        const streamQuality = document.getElementById("adj-stream-quality");
        const streamQualityValue = document.getElementById("adj-stream-quality-value");
        const solveInterval = document.getElementById("adj-solve-interval");
        const solveIntervalValue = document.getElementById("adj-solve-interval-value");
        if (streamQuality) streamQuality.value = String(this.streamQuality);
        if (streamQualityValue) streamQualityValue.textContent = String(this.streamQuality);
        if (solveInterval) {
            solveInterval.min = String(this.intervalMinMs);
            solveInterval.max = String(this.intervalMaxMs);
            solveInterval.value = String(this.solveIntervalMs);
        }
        if (solveIntervalValue) solveIntervalValue.textContent = `${this.solveIntervalMs} ms`;
        this.syncModeButtons();
    }

    syncModeButtons() {
        const autoExposure = document.getElementById("adj-auto-exposure");
        const nightMode = document.getElementById("adj-night-mode");
        this.setBtnActive(autoExposure, Boolean(this.cameraStatus?.info?.auto_exposure));
        this.setBtnActive(nightMode, Boolean(this.cameraStatus?.info?.night_mode));
    }

    setBtnActive(btn, active) {
        if (!btn) return;
        if (active) {
            btn.classList.add("border-primary/60", "text-primary");
            btn.classList.remove("border-stone-700", "text-stone-300");
        } else {
            btn.classList.remove("border-primary/60", "text-primary");
            btn.classList.add("border-stone-700", "text-stone-300");
        }
    }

    async startCameraStream() {
        try {
            await this.fetchJson("/api/debug/camera/start", { method: "POST", timeoutMs: 4000 });
        } catch (e) {
            console.warn("[OGScope] 启动相机失败，尝试继续拉流:", e);
        }
        await this.refreshCameraStatus();
        this.refreshStreamSource();
    }

    refreshStreamSource() {
        const streamImg = document.getElementById("video-stream");
        if (!streamImg) return;
        streamImg.src = `/api/dev/debug/camera/stream?quality=${this.streamQuality}&t=${Date.now()}`;
        this.applyStreamLayer();
    }

    applyStreamLayer() {
        const streamImg = document.getElementById("video-stream");
        if (!streamImg) return;
        streamImg.style.opacity = this.overlayLayers.video ? "1" : "0.08";
    }

    startDataUpdates() {
        this.updateSystemData();
        this.dataUpdateInterval = setInterval(() => {
            this.updateSystemData();
        }, 2200);
    }

    async updateSystemData() {
        const now = Date.now();
        if (now - this.lastTelemetryAt < 700) return;
        this.lastTelemetryAt = now;
        try {
            const [sys, cam] = await Promise.all([
                this.fetchJson("/api/system/info", { timeoutMs: 2000 }),
                this.fetchJson("/api/debug/camera/status", { timeoutMs: 2000 }),
            ]);
            this.cameraStatus = cam;
            this.syncModeButtons();
            this.updateSystemUi(sys);
        } catch {
            this.updateSystemUi(null);
        }
    }

    updateSystemUi(sys) {
        const gpsCoord = document.getElementById("gps-coord");
        const altitude = document.getElementById("altitude");
        const wifiStrength = document.getElementById("wifi-strength");
        const gpsStrength = document.getElementById("gps-strength");
        const batteryLevel = document.getElementById("battery-level");
        if (gpsCoord && gpsCoord.textContent.trim() === "—") {
            gpsCoord.textContent = "39°54'15\"N  116°24'26\"E";
        }
        if (altitude) {
            const v = Number(sys?.altitude ?? sys?.elevation_m ?? 43.8);
            altitude.textContent = `${v.toFixed(1)} m`;
        }
        if (wifiStrength) {
            const v = Number(sys?.wifi_signal ?? 92);
            wifiStrength.textContent = `${this.clamp(Math.round(v), 0, 100)}%`;
        }
        if (gpsStrength) {
            const v = Number(sys?.gps_signal ?? 97);
            gpsStrength.textContent = `${this.clamp(Math.round(v), 0, 100)}%`;
        }
        if (batteryLevel) {
            const v = Number(sys?.battery ?? sys?.battery_level ?? 86);
            batteryLevel.textContent = `${this.clamp(Math.round(v), 0, 100)}%`;
        }
    }

    startSolveLoop() {
        this.stopSolveLoop();
        this.performSolveTick();
        this.solveTimer = setInterval(() => this.performSolveTick(), this.solveIntervalMs);
    }

    restartSolveLoop() {
        if (this.solveTimer == null) return;
        this.startSolveLoop();
    }

    stopSolveLoop() {
        if (this.solveTimer) {
            clearInterval(this.solveTimer);
            this.solveTimer = null;
        }
    }

    async performSolveTick() {
        if (this.solveInFlight || document.hidden) return;
        if (Date.now() < this.solvePausedUntil) return;
        this.solveInFlight = true;
        this.triggerRadarScan();
        try {
            const payload = {
                source: "camera",
                overlay_topn_count: 3,
                enable_polar_guide: true,
                solve_interval_ms: this.solveIntervalMs,
                solve_timeout_ms: this.solverTimeoutMs,
                ...this.solveParams,
            };
            const out = await this.fetchJson("/api/analysis/solve/frame", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                // 不在前端强制中断解算请求，避免服务端线程任务残留叠加
                // Do not client-abort solve requests to avoid piling server-side worker tasks.
                timeoutMs: 0,
            });
            const result = out?.result || null;
            this.latestResult = result;
            const base = result?.solve_overlay || null;
            const ext = result?.overlay_ext || null;
            const merged = base ? { ...base, overlay_ext: ext || undefined } : null;
            this.cancelOverlayFade();
            if (merged) {
                this.latestOverlay = merged;
                this.updateSolveMetrics(result, merged);
                this.renderOverlay();
            } else {
                // 避免仍用旧的 latestOverlay 读极轴；新行无 solve_overlay 时以 overlay_ext 为准 / Avoid stale overlay; use new row overlay_ext
                this.updateSolveMetrics(result, { overlay_ext: result?.overlay_ext });
                this.fadeOutAndClearOverlay();
            }
            this.consecutiveSolveErrors = 0;
        } catch (e) {
            console.warn("[OGScope] 实时解算请求失败:", e);
            this.fadeOutAndClearOverlay();
            this.consecutiveSolveErrors += 1;
            if (this.consecutiveSolveErrors >= 4) {
                // 连续失败时进入短暂冷却，避免高频失败重试拖慢设备
                // Enter short cooldown on repeated failures to reduce load.
                this.solvePausedUntil = Date.now() + 15000;
                this.consecutiveSolveErrors = 0;
            }
        } finally {
            this.solveInFlight = false;
        }
    }

    /**
     * Tetra3 Prob = false-positive probability (lower is better).
     * 与 web/spa solveDisplay 一致：极小 fp 时线性 (1-fp)*100 在 float 中恒为 100，改用 -log10 映射。
     */
    tetraFalsePositiveProbToConfidencePercent(fp) {
        if (!Number.isFinite(fp) || fp < 0) return null;
        if (fp >= 1) return 0;
        if (fp === 0) return 100;
        const raw = (1 - fp) * 100;
        if (raw <= 100 - 1e-12) {
            return Math.min(100, Math.max(0, raw));
        }
        const L = -Math.log10(Math.max(fp, Number.MIN_VALUE));
        const L0 = 14;
        const L1 = 50;
        const t = Math.min(1, Math.max(0, (L - L0) / (L1 - L0)));
        return Math.min(100, Math.max(0, 70 + 30 * t));
    }

    /**
     * @param {Record<string, unknown> | null} result
     * @param {Record<string, unknown> | null} [overlayForGuide] 用于极轴读数（无 solve_overlay 时用新响应的 overlay_ext）/ Polar text from new row when solve_overlay missing
     */
    updateSolveMetrics(result, overlayForGuide) {
        const prob = Number(result?.prob);
        const pct = Number.isFinite(prob) ? this.tetraFalsePositiveProbToConfidencePercent(prob) : null;
        const qualityFillElement = document.getElementById("quality-fill");
        const qualityValueElement = document.getElementById("quality-value");
        // 与 solveDisplay.formatProb 一致：一位小数 / Match lab one-decimal confidence
        if (qualityFillElement) {
            qualityFillElement.style.width = pct == null ? "0%" : `${this.clamp(pct, 0, 100).toFixed(1)}%`;
        }
        if (qualityValueElement) {
            qualityValueElement.textContent = pct == null ? "—" : `${pct.toFixed(1)}%`;
        }

        const errorNode = document.getElementById("alignment-error");
        const rmse = Number(result?.rmse_arcsec);
        if (errorNode) {
            errorNode.textContent = Number.isFinite(rmse) ? `${rmse.toFixed(2)}″` : "--";
        }
        const overlayRef =
            overlayForGuide !== undefined ? overlayForGuide : this.latestOverlay;
        const guide = overlayRef?.overlay_ext?.polar_guide || null;
        const azNode = document.getElementById("azimuth-offset");
        const altNode = document.getElementById("altitude-offset");
        if (guide?.delta_px && typeof guide.angular_sep_deg === "number") {
            const dx = Number(guide.delta_px.dx || 0);
            const dy = Number(guide.delta_px.dy || 0);
            const dist = Math.hypot(dx, dy);
            const scale = dist > 1e-6 ? guide.angular_sep_deg / dist : 0;
            const az = dx * scale;
            const alt = -dy * scale;
            if (azNode) azNode.textContent = `${az >= 0 ? "+" : ""}${az.toFixed(2)}°`;
            if (altNode) altNode.textContent = `${alt >= 0 ? "+" : ""}${alt.toFixed(2)}°`;
            this.lastGuideAngle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
        } else {
            if (azNode) azNode.textContent = "—";
            if (altNode) altNode.textContent = "—";
        }
    }

    /** MJPEG 可能 naturalWidth=0，回退 solve_overlay.frame_shape / Fallback when MJPEG has no intrinsic size */
    getOverlaySrcSize(streamImg, overlay) {
        let srcW = Number(streamImg.naturalWidth || 0);
        let srcH = Number(streamImg.naturalHeight || 0);
        const fs = overlay?.frame_shape;
        if ((srcW < 2 || srcH < 2) && Array.isArray(fs) && fs.length >= 2) {
            const fh = Number(fs[0]);
            const fw = Number(fs[1]);
            if (Number.isFinite(fw) && Number.isFinite(fh) && fw >= 2 && fh >= 2) {
                srcW = fw;
                srcH = fh;
            }
        }
        return { srcW, srcH };
    }

    /** 取消淡出并重置样式 / Cancel overlay fade animation */
    cancelOverlayFade() {
        if (this._overlayFadeTimer) {
            clearTimeout(this._overlayFadeTimer);
            this._overlayFadeTimer = null;
        }
        const canvas = document.getElementById("analysis-overlay-canvas");
        const guideLine = document.getElementById("polar-guide-line");
        const ref = document.getElementById("polar-reference");
        if (canvas) canvas.classList.remove("hud-overlay-fading");
        if (guideLine) guideLine.classList.remove("hud-overlay-fading");
        if (ref) ref.classList.remove("hud-overlay-fading");
    }

    /**
     * 解算失败或无 overlay 时渐变清空叠加 / Fade out overlay then clear (network error or TOO_FEW etc.)
     */
    fadeOutAndClearOverlay() {
        const hasCanvasData = this.latestOverlay != null;
        const guideLine = document.getElementById("polar-guide-line");
        const ref = document.getElementById("polar-reference");
        const polarVisible =
            (guideLine && !guideLine.classList.contains("hidden")) ||
            (ref && !ref.classList.contains("hidden"));
        if (!hasCanvasData && !polarVisible) {
            return;
        }
        this.cancelOverlayFade();
        const canvas = document.getElementById("analysis-overlay-canvas");
        if (!canvas) {
            this.latestOverlay = null;
            this.hidePolarGuides();
            return;
        }
        requestAnimationFrame(() => {
            canvas.classList.add("hud-overlay-fading");
            if (guideLine && !guideLine.classList.contains("hidden")) {
                guideLine.classList.add("hud-overlay-fading");
            }
            if (ref && !ref.classList.contains("hidden")) {
                ref.classList.add("hud-overlay-fading");
            }
            this._overlayFadeTimer = setTimeout(() => {
                this._overlayFadeTimer = null;
                this.cancelOverlayFade();
                this.latestOverlay = null;
                this.hidePolarGuides();
                this.renderOverlay();
            }, 420);
        });
    }

    renderOverlay() {
        const streamImg = document.getElementById("video-stream");
        const canvas = document.getElementById("analysis-overlay-canvas");
        if (!streamImg || !canvas) return;
        const rect = streamImg.getBoundingClientRect();
        const cssW = Math.max(1, Math.floor(rect.width));
        const cssH = Math.max(1, Math.floor(rect.height));
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.max(1, Math.floor(cssW * dpr));
        canvas.height = Math.max(1, Math.floor(cssH * dpr));
        canvas.style.width = `${cssW}px`;
        canvas.style.height = `${cssH}px`;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, cssW, cssH);

        const overlay = this.latestOverlay;
        if (!overlay) {
            this.hidePolarGuides();
            return;
        }
        const { srcW, srcH } = this.getOverlaySrcSize(streamImg, overlay);
        if (srcW < 2 || srcH < 2) {
            this.hidePolarGuides();
            return;
        }

        const coverScale = Math.max(cssW / srcW, cssH / srcH);
        const drawW = srcW * coverScale;
        const drawH = srcH * coverScale;
        const offsetX = (cssW - drawW) / 2;
        const offsetY = (cssH - drawH) / 2;
        const mapPoint = (x, y) => ({ x: x * coverScale + offsetX, y: y * coverScale + offsetY });

        if (this.overlayLayers.all && Array.isArray(overlay.stars_all_centroids)) {
            ctx.fillStyle = "rgba(226,232,240,0.90)";
            for (const s of overlay.stars_all_centroids) {
                const p = mapPoint(Number(s.x || 0), Number(s.y || 0));
                ctx.beginPath();
                ctx.arc(p.x, p.y, Math.max(1.9, 2.9 * coverScale), 0, Math.PI * 2);
                ctx.fill();
            }
        }
        if (this.overlayLayers.rejected && Array.isArray(overlay.stars_rejected_centroids)) {
            ctx.strokeStyle = "rgba(248, 113, 113, 0.95)";
            ctx.lineWidth = Math.max(1.4, 1.6 * coverScale);
            const d = Math.max(3.2, 4 * coverScale);
            for (const s of overlay.stars_rejected_centroids) {
                const p = mapPoint(Number(s.x || 0), Number(s.y || 0));
                ctx.beginPath();
                ctx.moveTo(p.x - d, p.y - d);
                ctx.lineTo(p.x + d, p.y + d);
                ctx.moveTo(p.x + d, p.y - d);
                ctx.lineTo(p.x - d, p.y + d);
                ctx.stroke();
            }
        }
        if (this.overlayLayers.pattern && Array.isArray(overlay.stars_pattern)) {
            ctx.strokeStyle = "rgba(251,146,60,0.95)";
            ctx.lineWidth = Math.max(1.6, 2.2 * coverScale);
            for (const s of overlay.stars_pattern) {
                const p = mapPoint(Number(s.x || 0), Number(s.y || 0));
                ctx.beginPath();
                ctx.arc(p.x, p.y, Math.max(5.2, 6.8 * coverScale), 0, Math.PI * 2);
                ctx.stroke();
            }
        }
        if (this.overlayLayers.matched && Array.isArray(overlay.stars_matched)) {
            ctx.strokeStyle = "rgba(74,222,128,0.95)";
            ctx.fillStyle = "rgba(74,222,128,0.96)";
            ctx.lineWidth = Math.max(1.6, 2.2 * coverScale);
            ctx.font = "11px system-ui, sans-serif";
            for (const s of overlay.stars_matched) {
                const p = mapPoint(Number(s.x || 0), Number(s.y || 0));
                ctx.beginPath();
                ctx.arc(p.x, p.y, Math.max(5.8, 7.6 * coverScale), 0, Math.PI * 2);
                ctx.stroke();
                if (s.mag != null) {
                    const mag = Number(s.mag);
                    if (Number.isFinite(mag)) ctx.fillText(`m${mag.toFixed(1)}`, p.x + 6, p.y - 6);
                }
            }
        }
        const ext = overlay.overlay_ext;
        if (Array.isArray(ext?.labels_topn) && ext.labels_topn.length > 0) {
            ctx.fillStyle = "rgba(96, 165, 250, 0.95)";
            ctx.font = `${Math.max(11, Math.round(12 * coverScale))}px system-ui, sans-serif`;
            for (const s of ext.labels_topn) {
                if (typeof s?.x !== "number" || typeof s?.y !== "number") continue;
                const p = mapPoint(s.x, s.y);
                const magText = typeof s.mag === "number" ? ` m${s.mag.toFixed(1)}` : "";
                const title = `${s.name != null && s.name !== "" ? s.name : "Star"}${magText}`;
                ctx.fillText(title, p.x + 8, p.y + 14);
            }
        }
        this.renderPolarGuides(overlay, mapPoint);
    }

    triggerRadarScan() {
        const radar = document.getElementById("solve-radar-scan");
        if (!radar) return;
        radar.classList.remove("radar-active");
        // 触发重绘后重启动画 / Retrigger CSS animation reliably
        void radar.offsetWidth;
        radar.classList.add("radar-active");
    }

    hidePolarGuides() {
        const guideLine = document.getElementById("polar-guide-line");
        const ref = document.getElementById("polar-reference");
        if (guideLine) {
            guideLine.classList.remove("hud-overlay-fading");
            guideLine.classList.add("hidden");
        }
        if (ref) {
            ref.classList.remove("hud-overlay-fading");
            ref.classList.add("hidden");
        }
    }

    renderPolarGuides(overlay, mapPoint) {
        const guideLine = document.getElementById("polar-guide-line");
        const ref = document.getElementById("polar-reference");
        const guide = overlay?.overlay_ext?.polar_guide;
        if (
            !guideLine ||
            !ref ||
            !guide ||
            typeof guide.frame_center?.x !== "number" ||
            typeof guide.frame_center?.y !== "number" ||
            typeof guide.target?.x !== "number" ||
            typeof guide.target?.y !== "number"
        ) {
            this.hidePolarGuides();
            return;
        }

        const c = mapPoint(guide.frame_center.x, guide.frame_center.y);
        const t = mapPoint(guide.target.x, guide.target.y);
        const dx = t.x - c.x;
        const dy = t.y - c.y;
        const len = Math.max(8, Math.hypot(dx, dy));
        const angle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
        const lineWidth = this.clamp(1.8 + len / 180, 1.8, 5.2);

        guideLine.style.left = `${c.x}px`;
        guideLine.style.top = `${c.y}px`;
        guideLine.style.height = `${len}px`;
        guideLine.style.width = `${lineWidth}px`;
        guideLine.style.transform = `translate(-50%, 0) rotate(${angle}deg)`;
        guideLine.style.background = "linear-gradient(180deg, rgba(255,180,168,0.02) 0%, rgba(255,180,168,0.95) 88%)";
        guideLine.classList.remove("hud-overlay-fading", "hidden");

        ref.style.left = `${t.x}px`;
        ref.style.top = `${t.y}px`;
        ref.classList.remove("hud-overlay-fading", "hidden");

        this.lastGuideAngle = angle;
    }

    async refreshCameraStatus() {
        try {
            this.cameraStatus = await this.fetchJson("/api/debug/camera/status", { timeoutMs: 2000 });
            this.syncModeButtons();
        } catch {
            this.cameraStatus = null;
        }
    }

    async fetchJson(url, options = {}) {
        const timeoutMs = Number(options.timeoutMs ?? 3000);
        const useAbort = timeoutMs > 0;
        const controller = useAbort ? new AbortController() : null;
        const timeoutId = useAbort ? setTimeout(() => controller.abort(), timeoutMs) : null;
        try {
            const resp = await fetch(url, {
                method: options.method || "GET",
                headers: options.headers,
                body: options.body,
                cache: options.cache || "no-store",
                signal: controller ? controller.signal : undefined,
            });
            const text = await resp.text();
            let data = null;
            try {
                data = text ? JSON.parse(text) : {};
            } catch {
                data = text;
            }
            if (!resp.ok) {
                throw new Error(typeof data === "string" ? data : data?.detail || `HTTP ${resp.status}`);
            }
            return data;
        } finally {
            if (timeoutId != null) clearTimeout(timeoutId);
        }
    }

    clamp(v, min, max) {
        return Math.min(max, Math.max(min, v));
    }

    handleInitializationError(error) {
        const loadingStatus = document.getElementById("loading-status");
        if (loadingStatus) {
            loadingStatus.textContent = `初始化失败 / Init failed: ${String(error)}`;
            loadingStatus.style.color = "#ff6666";
        }
        setTimeout(() => this.init(), 2500);
    }

    cleanup() {
        this.cancelOverlayFade();
        if (this.resizeObserver) {
            try {
                this.resizeObserver.disconnect();
            } catch (_) {
                /* ignore */
            }
            this.resizeObserver = null;
        }
        if (this.loadingInterval) {
            clearInterval(this.loadingInterval);
            this.loadingInterval = null;
        }
        if (this.dataUpdateInterval) {
            clearInterval(this.dataUpdateInterval);
            this.dataUpdateInterval = null;
        }
        this.stopSolveLoop();
        if (this.retryTimer) {
            clearTimeout(this.retryTimer);
            this.retryTimer = null;
        }
    }
}

function bootOGScopeHomeApp() {
    window.OGScopeApp = new OGScopeHomeApp();
}

// 若脚本在 DOMContentLoaded 之后动态插入（如 Vite 首页入口），需立即启动 / If script loads after DOMContentLoaded (e.g. Vite home entry), boot immediately.
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootOGScopeHomeApp);
} else {
    bootOGScopeHomeApp();
}
