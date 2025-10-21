/**
 * OGScope 调试控制台 JavaScript
 * 提供相机调试、拍摄控制、参数设置等功能
 */

class DebugConsole {
    constructor() {
        this.cameraStatus = {
            connected: false,
            streaming: false,
            recording: false
        };
        this.previewActive = false;
        
        this.currentSettings = {
            exposure: 10000,
            gain: 1.0,
            digitalGain: 1.0,
            rotation: 180,
            // 新增参数
            contrast: 1.0,
            brightness: 0.0,
            saturation: 1.0,
            sharpness: 1.0,
            noiseReduction: 0,
            whiteBalanceMode: 'auto',
            whiteBalanceGainR: 1.0,
            whiteBalanceGainB: 1.0,
            nightMode: false
        };
        
        this.presets = [];
        this.files = [];
        this.recordingStartTime = null;
        this.recordingInterval = null;
        this.statusInterval = null;
        
        // 实时数据流分析
        this.streamStats = {
            frameCount: 0,
            lastFrameTime: null,
            fpsCalculated: 0.0,
            resolutionDetected: null,
            dataSize: 0,
            avgFrameSize: 0,
            frameTimes: [],
            startTime: null
        };
        
        this.init();
    }
    
    /**
     * 分析实时数据流
     */
    analyzeStreamData(imageElement) {
        const currentTime = performance.now();
        
        // 记录开始时间
        if (this.streamStats.startTime === null) {
            this.streamStats.startTime = currentTime;
        }
        
        // 更新帧计数
        this.streamStats.frameCount++;
        
        // 检测分辨率并调整容器宽高比
        if (imageElement && imageElement.naturalWidth && imageElement.naturalHeight) {
            const detectedRes = `${imageElement.naturalWidth}x${imageElement.naturalHeight}`;
            if (this.streamStats.resolutionDetected !== detectedRes) {
                this.streamStats.resolutionDetected = detectedRes;
                console.log(`[Stream] 检测到分辨率: ${detectedRes}`);
                this.updateVideoContainerAspectRatio(imageElement.naturalWidth, imageElement.naturalHeight);
            }
        }
        
        // 计算帧率
        if (this.streamStats.lastFrameTime !== null) {
            const timeDiff = currentTime - this.streamStats.lastFrameTime;
            // 忽略过小的时间差（可能由浏览器缓存/事件合并导致的“超高FPS”）
            if (timeDiff > 10) {
                let fps = 1000 / timeDiff; // 转换为每秒帧数
                // 上限保护：以相机报告 fps 的 2 倍或默认 10fps 作为硬上限
                const reported = (this.cameraStatus?.info?.fps) || 5;
                const fpsCap = Math.max(10, reported * 2);
                if (fps > fpsCap) fps = fpsCap;
                this.streamStats.frameTimes.push(fps);
                
                // 保持最近10帧的FPS数据
                if (this.streamStats.frameTimes.length > 10) {
                    this.streamStats.frameTimes.shift();
                }
                
                // 计算平均FPS
                const avgFps = this.streamStats.frameTimes.reduce((a, b) => a + b, 0) / this.streamStats.frameTimes.length;
                this.streamStats.fpsCalculated = avgFps;
            }
        }
        
        this.streamStats.lastFrameTime = currentTime;
        
        // 更新UI显示
        this.updateStreamStatsDisplay();
    }
    
    /**
     * 根据相机分辨率动态调整视频容器的宽高比
     * 考虑传感器原生宽高比，避免画面被压缩
     */
    updateVideoContainerAspectRatio(width, height) {
        const videoContainer = document.querySelector('.video-container');
        if (!videoContainer) return;
        
        // IMX327传感器原生宽高比约为16:9 (1945x1097)
        const sensorAspectRatio = 1945 / 1097; // ≈ 1.773
        const outputAspectRatio = width / height;
        
        // 如果输出分辨率与传感器比例差异较大，使用传感器比例
        // 这样可以避免画面被压缩
        let targetAspectRatio;
        if (Math.abs(outputAspectRatio - sensorAspectRatio) > 0.1) {
            // 使用传感器原生比例
            targetAspectRatio = sensorAspectRatio;
            console.log(`[UI] 输出分辨率${width}x${height}与传感器比例差异较大，使用传感器比例: ${sensorAspectRatio.toFixed(3)}`);
        } else {
            // 使用输出分辨率比例
            targetAspectRatio = outputAspectRatio;
            console.log(`[UI] 使用输出分辨率比例: ${width}:${height} (${outputAspectRatio.toFixed(3)})`);
        }
        
        // 设置CSS自定义属性
        videoContainer.style.aspectRatio = `${targetAspectRatio}`;
        
        // 添加视觉反馈
        videoContainer.classList.add('aspect-ratio-changing');
        setTimeout(() => {
            videoContainer.classList.remove('aspect-ratio-changing');
        }, 300);
    }
    
    /**
     * 更新数据流统计显示
     */
    updateStreamStatsDisplay() {
        // 更新分辨率显示
        if (this.streamStats.resolutionDetected) {
            const resolutionElement = document.getElementById('detected-resolution');
            if (resolutionElement) {
                resolutionElement.textContent = this.streamStats.resolutionDetected;
            }
        }
        
        // 更新FPS显示
        const fpsElement = document.getElementById('calculated-fps');
        if (fpsElement) {
            fpsElement.textContent = this.streamStats.fpsCalculated.toFixed(2);
        }
        
        // 更新帧计数显示
        const frameCountElement = document.getElementById('frame-count');
        if (frameCountElement) {
            frameCountElement.textContent = this.streamStats.frameCount;
        }
        
        // 更新数据大小显示
        const dataSizeElement = document.getElementById('data-size');
        if (dataSizeElement) {
            const dataSizeMB = (this.streamStats.dataSize / (1024 * 1024)).toFixed(2);
            dataSizeElement.textContent = `${dataSizeMB} MB`;
        }
        
        // 更新流状态显示
        const streamStatusElement = document.getElementById('stream-status');
        if (streamStatusElement) {
            const isActive = this.streamStats.lastFrameTime !== null && 
                           (performance.now() - this.streamStats.lastFrameTime) < 5000;
            streamStatusElement.textContent = isActive ? '活跃' : '非活跃';
            streamStatusElement.className = isActive ? 'status-active' : 'status-inactive';
        }
        
        // 更新运行时长显示
        const runtimeElement = document.getElementById('runtime');
        if (runtimeElement && this.streamStats.startTime !== null) {
            const runtime = (performance.now() - this.streamStats.startTime) / 1000;
            runtimeElement.textContent = `${runtime.toFixed(1)}s`;
        }
    }
    
    /**
     * 重置数据流统计
     */
    resetStreamStats() {
        this.streamStats = {
            frameCount: 0,
            lastFrameTime: null,
            fpsCalculated: 0.0,
            resolutionDetected: null,
            dataSize: 0,
            avgFrameSize: 0,
            frameTimes: [],
            startTime: null
        };
        this.updateStreamStatsDisplay();
    }
    
    /**
     * 设置画面旋转角度
     */
    async setRotation(rotation) {
        try {
            const response = await fetch(`/api/debug/camera/rotation/${rotation}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            if (result.success) {
                this.currentSettings.rotation = rotation;
                this.updateRotationDisplay();
                this.showNotification(result.message, 'success');
            } else {
                throw new Error(result.message || '设置旋转失败');
            }
        } catch (error) {
            console.error('设置旋转失败:', error);
            this.showNotification(`设置旋转失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 更新旋转角度显示
     */
    updateRotationDisplay() {
        // 更新当前角度显示
        const rotationElement = document.getElementById('current-rotation');
        if (rotationElement) {
            rotationElement.textContent = `${this.currentSettings.rotation}°`;
        }
        
        // 更新按钮状态
        document.querySelectorAll('[data-rotation]').forEach(button => {
            const buttonRotation = parseInt(button.dataset.rotation);
            if (buttonRotation === this.currentSettings.rotation) {
                button.classList.remove('btn-secondary');
                button.classList.add('btn-primary');
            } else {
                button.classList.remove('btn-primary');
                button.classList.add('btn-secondary');
            }
        });
    }
    
    /**
     * 初始化调试控制台
     */
    async init() {
        console.log('[DebugConsole] 初始化调试控制台...');
        
        // 设置事件监听器
        this.setupEventListeners();
        
        // 初始化UI
        this.initUI();
        
        // 加载数据
        await this.loadPresets();
        await this.loadFiles();
        
        // 更新相机状态
        await this.updateCameraStatus();
        
        // 启动图像质量监控
        this.startQualityMonitoring();
        
        console.log('[DebugConsole] 调试控制台初始化完成');
    }
    
    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 标签页切换
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });
        
        // 相机控制
        document.getElementById('start-preview')?.addEventListener('click', () => {
            this.startPreview();
        });
        
        document.getElementById('stop-preview')?.addEventListener('click', () => {
            this.stopPreview();
        });
        
        // 拍摄控制
        document.getElementById('capture-image')?.addEventListener('click', () => {
            this.captureImage();
        });
        
        document.getElementById('start-recording')?.addEventListener('click', () => {
            this.startRecording();
        });
        
        document.getElementById('stop-recording')?.addEventListener('click', () => {
            this.stopRecording();
        });
        
        // 参数设置
        document.getElementById('exposure-setting')?.addEventListener('input', (e) => {
            this.updateExposureDisplay(parseInt(e.target.value));
        });
        
        document.getElementById('gain-setting')?.addEventListener('input', (e) => {
            this.updateGainDisplay(parseFloat(e.target.value));
        });
        
        document.getElementById('digital-gain-setting')?.addEventListener('input', (e) => {
            this.updateDigitalGainDisplay(parseFloat(e.target.value));
        });
        
        document.getElementById('apply-settings')?.addEventListener('click', () => {
            this.applySettings();
        });
        
        document.getElementById('reset-settings')?.addEventListener('click', () => {
            this.resetSettings();
        });
        
        // 预设管理
        document.getElementById('save-preset')?.addEventListener('click', () => {
            this.savePreset();
        });
        
        // 文件管理
        document.getElementById('refresh-files')?.addEventListener('click', () => {
            this.loadFiles();
        });
        
        // 设置重置统计按钮事件监听器
        document.getElementById('reset-stats')?.addEventListener('click', () => {
            this.resetStreamStats();
        });
        
        // 设置旋转控制按钮事件监听器
        document.querySelectorAll('[data-rotation]').forEach(button => {
            button.addEventListener('click', (e) => {
                const rotation = parseInt(e.target.dataset.rotation);
                this.setRotation(rotation);
            });
        });
        
        // 新增参数控制事件监听器
        document.getElementById('contrast-setting')?.addEventListener('input', (e) => {
            this.updateContrastDisplay(parseFloat(e.target.value));
        });
        
        document.getElementById('brightness-setting')?.addEventListener('input', (e) => {
            this.updateBrightnessDisplay(parseFloat(e.target.value));
        });
        
        document.getElementById('saturation-setting')?.addEventListener('input', (e) => {
            this.updateSaturationDisplay(parseFloat(e.target.value));
        });
        
        document.getElementById('sharpness-setting')?.addEventListener('input', (e) => {
            this.updateSharpnessDisplay(parseFloat(e.target.value));
        });
        
        document.getElementById('noise-reduction-setting')?.addEventListener('input', (e) => {
            this.updateNoiseReductionDisplay(parseInt(e.target.value));
        });
        
        document.getElementById('white-balance-mode')?.addEventListener('change', (e) => {
            this.updateWhiteBalanceMode(e.target.value);
        });
        
        document.getElementById('wb-gain-r')?.addEventListener('input', (e) => {
            this.updateWhiteBalanceGainR(parseFloat(e.target.value));
        });
        
        document.getElementById('wb-gain-b')?.addEventListener('input', (e) => {
            this.updateWhiteBalanceGainB(parseFloat(e.target.value));
        });
        
        // 夜间模式控制
        document.getElementById('night-mode-preset')?.addEventListener('click', () => {
            this.applyNightModePreset();
        });
        
        document.getElementById('toggle-night-mode')?.addEventListener('click', () => {
            this.toggleNightMode();
        });
        
        // 安全机制
        document.getElementById('backup-settings')?.addEventListener('click', () => {
            this.backupSettings();
        });
        
        document.getElementById('restore-settings')?.addEventListener('click', () => {
            this.restoreSettings();
        });
        
        // 分辨率预设选择
        document.querySelectorAll('[data-res]').forEach(button => {
            button.addEventListener('click', (e) => {
                document.querySelectorAll('[data-res]').forEach(b=>b.classList.remove('btn-primary'));
                e.currentTarget.classList.add('btn-primary');
            });
        });
        // 应用分辨率（仅宽高，不影响帧率）
        document.getElementById('apply-resolution')?.addEventListener('click', () => {
            const activeBtn = document.querySelector('[data-res].btn-primary');
            if (!activeBtn) {
                this.showNotification('请选择分辨率预设', 'warning');
                return;
            }
            const [w, h] = activeBtn.dataset.res.split('x').map(v=>parseInt(v));
            this.applySizeOnly(w, h);
        });

        // 应用单独帧率
        document.getElementById('apply-fps')?.addEventListener('click', async () => {
            const fpsInput = document.getElementById('fps-input');
            const fps = parseInt(fpsInput?.value || '5');
            const btn = document.getElementById('apply-fps');
            
            if (!Number.isFinite(fps) || fps <= 0) {
                this.showNotification('请输入有效的帧率', 'warning');
                return;
            }
            try {
                if (btn) btn.disabled = true;
                this.showNotification('正在设置帧率...', 'info');
                
                // 尽量不中断预览直接应用
                const params = new URLSearchParams({ fps: String(fps) });
                const resp = await fetch(`/api/debug/camera/fps?${params.toString()}`, { method: 'POST' });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || '设置帧率失败');
                }
                this.showNotification('帧率已应用', 'success');
                await this.updateCameraStatus();
            } catch (e) {
                console.error(e);
                this.showNotification(`设置帧率失败: ${e.message}`, 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        });

        // 应用采样模式
        document.getElementById('apply-sampling')?.addEventListener('click', async () => {
            const sel = document.getElementById('sampling-select');
            const mode = sel?.value || 'supersample';
            const btn = document.getElementById('apply-sampling');
            
            try {
                if (btn) btn.disabled = true;
                this.showNotification('正在切换采样模式...', 'info');
                
                // 停止预览以避免旧源卡住
                try { await this.stopPreview(); } catch(_){}
                const params = new URLSearchParams({ mode });
                const resp = await fetch(`/api/debug/camera/sampling?${params.toString()}`, { method: 'POST' });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || '设置采样模式失败');
                }
                this.showNotification('采样模式已切换', 'success');
                // 刷新状态并重启预览
                await this.updateCameraStatus();
                await this.startPreview();
            } catch (e) {
                console.error(e);
                this.showNotification(`设置采样模式失败: ${e.message}`, 'error');
                // 尝试恢复预览
                try {
                    await this.updateCameraStatus();
                    if (this.cameraStatus.streaming) {
                        await this.startPreview();
                    }
                } catch (recoveryError) {
                    console.error('[apply-sampling] recovery failed:', recoveryError);
                }
            } finally {
                if (btn) btn.disabled = false;
            }
        });
        
        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            this.handleKeyboardShortcuts(e);
        });

        // 启动时同步一次边框状态
        this.setRecOverlay(this.cameraStatus.recording);
    }
    
    /**
     * 初始化UI
     */
    initUI() {
        // 设置默认标签页
        this.switchTab('preview');
        
        // 初始化参数显示
        this.updateExposureDisplay(this.currentSettings.exposure);
        this.updateGainDisplay(this.currentSettings.gain);
        this.updateDigitalGainDisplay(this.currentSettings.digitalGain);
        
        // 添加触摸反馈
        document.querySelectorAll('.btn, .tab-button, .control-row input').forEach(element => {
            element.classList.add('touch-feedback');
        });
    }
    
    /**
     * 切换标签页
     */
    switchTab(tabName) {
        // 更新按钮状态
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        
        // 更新内容显示
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `tab-${tabName}`);
        });
        
        // 特殊处理
        if (tabName === 'files') {
            this.loadFiles();
        } else if (tabName === 'presets') {
            this.loadPresets();
        }
    }
    
    /**
     * 更新相机状态
     */
    async updateCameraStatus() {
        try {
            const response = await fetch('/api/debug/camera/status');
            const status = await response.json();
            
            this.cameraStatus = status;
            this.updateStatusUI();
            this.updateInfoUI();
            
            // 如果相机正在运行，且预览未激活，则启动预览循环（避免重复重置统计）
            if (status.streaming && !this.previewActive) {
                this.startPreviewUpdate();
            }
            // 同步录制状态与计时
            if (this.cameraStatus.recording) {
                if (!this.recordingStartTime) {
                    this.recordingStartTime = Date.now();
                    this.startRecordingTimer();
                }
                this.updateRecordingButtons(true);
                this.setRecOverlay(true);
            } else {
                this.stopRecordingTimer();
                this.updateRecordingButtons(false);
                this.setRecOverlay(false);
            }
            
        } catch (error) {
            console.error('[DebugConsole] 获取相机状态失败:', error);
            this.showNotification('获取相机状态失败', 'error');
        }
    }
    
    /**
     * 更新状态UI
     */
    updateStatusUI() {
        const statusIndicator = document.getElementById('camera-status');
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('.status-text');
        
        if (this.cameraStatus.recording) {
            statusDot.className = 'status-dot recording';
            statusText.textContent = '录制中';
        } else if (this.cameraStatus.streaming) {
            statusDot.className = 'status-dot online';
            statusText.textContent = '预览中';
        } else if (this.cameraStatus.connected) {
            statusDot.className = 'status-dot online';
            statusText.textContent = '已连接';
        } else {
            statusDot.className = 'status-dot offline';
            statusText.textContent = '相机离线';
        }
        
        // 更新预览状态
        document.getElementById('preview-status').textContent = 
            this.cameraStatus.streaming ? '运行中' : '未启动';
        
        // 更新录制状态
        document.getElementById('recording-status').textContent = 
            this.cameraStatus.recording ? '录制中' : '未录制';
        
        // 更新按钮状态
        this.updateButtonStates();
    }

    /**
     * 更新分辨率/帧率显示
     */
    updateInfoUI() {
        const resEl = document.getElementById('resolution');
        const fpsEl = document.getElementById('fps');
        const info = this.cameraStatus.info || {};
        const width = info.width || (info.resolution ? parseInt(String(info.resolution).split('x')[0]) : null);
        const height = info.height || (info.resolution ? parseInt(String(info.resolution).split('x')[1]) : null);
        if (width && height) {
            resEl.textContent = `${width}x${height}`;
        } else {
            resEl.textContent = '--';
        }
        fpsEl.textContent = (info.fps || this.cameraStatus.fps || 0) ? `${info.fps || this.cameraStatus.fps}` : '--';
        const samplingEl = document.getElementById('sampling-mode');
        if (samplingEl) samplingEl.textContent = info.sampling_mode || '--';
    }
    
    /**
     * 启动预览
     */
    async startPreview() {
        try {
            // 显示启动状态
            this.showNotification('正在启动相机预览...', 'info');
            
            const response = await fetch('/api/debug/camera/start', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification('相机预览已启动', 'success');
                this.startPreviewUpdate();
                this.updateButtonStates();
                await this.updateCameraStatus();
                this.beginStatusPolling();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '启动预览失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 启动预览失败:', error);
            this.showNotification(`启动预览失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 停止预览
     */
    async stopPreview() {
        try {
            await fetch('/api/debug/camera/stop', {
                method: 'POST'
            });
            
            this.stopPreviewUpdate();
            this.updateButtonStates();
            await this.updateCameraStatus();
            this.showNotification('相机预览已停止', 'info');
            this.endStatusPolling();
            
        } catch (error) {
            console.error('[DebugConsole] 停止预览失败:', error);
            this.showNotification('停止预览失败', 'error');
        }
    }
    
    /**
     * 开始预览更新
     */
    startPreviewUpdate() {
        this.stopPreviewUpdate(); // 清除现有定时器
        const previewImg = document.getElementById('preview-image');
        const overlay = document.getElementById('preview-overlay');
        if (!previewImg || !overlay) return;

        // 启动前立即隐藏覆盖层，并重置统计，避免提示一直停留
        overlay.classList.add('hidden');
        this.resetStreamStats();

        // 使用单次请求循环（避免并发取消）：每次等上一帧 onload/onerror/超时 后再发起下一帧
        this.previewActive = true;
        // 提高预览帧率到15fps以获得更流畅的体验
        const fps = 15;
        const intervalMs = Math.max(1000 / fps, 50);
        let consecutiveFailures = 0;
        let frameToken = 0;
        let firstFrameAttempts = 0;
        const maxFirstFrameAttempts = 10;  // 前10次请求使用更短间隔

        const loop = () => {
            if (!this.previewActive) return;
            const loader = new Image();
            const startedAt = performance.now();
            const myToken = ++frameToken;
            
            // 增加第一帧尝试计数
            if (firstFrameAttempts < maxFirstFrameAttempts) {
                firstFrameAttempts++;
            }

            // 帧超时保护：1s 未返回则视为失败，退避重试（减少等待时间）
            let timeoutId = setTimeout(() => {
                if (!this.previewActive || myToken !== frameToken) return;
                consecutiveFailures++;
                const retryDelay = Math.min(1000, 200 + consecutiveFailures * 200);
                this.previewTimer = setTimeout(loop, retryDelay);
            }, 1000);

            loader.onload = () => {
                // 交换显示源，避免中途取消请求
                previewImg.src = loader.src;
                this.analyzeStreamData(loader);
                if (timeoutId) { clearTimeout(timeoutId); timeoutId = null; }
                consecutiveFailures = 0;
                
                // 第一帧获取成功后，恢复正常间隔
                if (firstFrameAttempts < maxFirstFrameAttempts) {
                    firstFrameAttempts = maxFirstFrameAttempts;
                    console.log(`[Preview] 第一帧获取成功，耗时 ${(performance.now() - startedAt).toFixed(1)}ms`);
                }
                
                const elapsed = performance.now() - startedAt;
                // 第一帧阶段使用更短间隔
                const currentInterval = firstFrameAttempts < maxFirstFrameAttempts ? 100 : intervalMs;
                const delay = Math.max(0, currentInterval - elapsed);
                this.previewTimer = setTimeout(loop, delay);
            };
            loader.onerror = () => {
                // 失败则稍后重试
                if (timeoutId) { clearTimeout(timeoutId); timeoutId = null; }
                consecutiveFailures++;
                const retryDelay = Math.min(1000, 200 + consecutiveFailures * 200);
                this.previewTimer = setTimeout(loop, retryDelay);
            };
            loader.src = `/api/debug/camera/preview?t=${Date.now()}`;
        };
        loop();

        // 看门狗：若2秒未收到帧，强制刷新状态（更敏感的检测）
        this.previewWatchdog = setInterval(() => {
            if (this.streamStats.lastFrameTime === null) return;
            const since = performance.now() - this.streamStats.lastFrameTime;
            if (since > 2000) {
                this.updateCameraStatus();
            }
        }, 1000);
    }
    
    /**
     * 停止预览更新
     */
    stopPreviewUpdate() {
        if (this.previewInterval) {
            clearInterval(this.previewInterval);
            this.previewInterval = null;
        }
        if (this.previewTimer) {
            clearTimeout(this.previewTimer);
            this.previewTimer = null;
        }
        this.previewActive = false;
        if (this.previewWatchdog) {
            clearInterval(this.previewWatchdog);
            this.previewWatchdog = null;
        }
        // 复位预览图片
        const previewImg = document.getElementById('preview-image');
        if (previewImg) {
            try { previewImg.onload = null; previewImg.onerror = null; } catch(_){}
            previewImg.src = '/static/images/placeholder-camera.png';
        }
        // 显示覆盖层
        document.getElementById('preview-overlay').classList.remove('hidden');
    }
    
    /**
     * 拍摄图片
     */
    async captureImage() {
        if (!this.cameraStatus.streaming) {
            this.showNotification('请先启动相机预览', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/debug/camera/capture', {
                method: 'POST'
            });
            
            if (response.ok) {
                const result = await response.json();
                this.showNotification(`照片已保存: ${result.filename}`, 'success');
                
                // 更新最后拍摄时间
                const now = new Date();
                document.getElementById('last-capture').textContent = 
                    now.toLocaleTimeString();
                
                // 刷新文件列表
                await this.loadFiles();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '拍摄失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 拍摄失败:', error);
            this.showNotification(`拍摄失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 开始录制
     */
    async startRecording() {
        if (!this.cameraStatus.streaming) {
            this.showNotification('请先启动相机预览', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/debug/camera/record/start', {
                method: 'POST'
            });
            
            if (response.ok) {
                const result = await response.json();
                this.showNotification(`开始录制: ${result.filename}`, 'success');
                
                // 开始计时
                this.recordingStartTime = Date.now();
                this.startRecordingTimer();
                
                // 更新按钮状态
                this.updateRecordingButtons(true);
                this.setRecOverlay(true);
                
                // 更新状态
                await this.updateCameraStatus();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '开始录制失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 开始录制失败:', error);
            this.showNotification(`开始录制失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 停止录制
     */
    async stopRecording() {
        try {
            await fetch('/api/debug/camera/record/stop', {
                method: 'POST'
            });
            
            this.showNotification('录制已停止', 'info');
            
            // 停止计时
            this.stopRecordingTimer();
            
            // 更新按钮状态
            this.updateRecordingButtons(false);
            this.setRecOverlay(false);
            
            // 更新状态
            await this.updateCameraStatus();
            
            // 刷新文件列表
            await this.loadFiles();
            
        } catch (error) {
            console.error('[DebugConsole] 停止录制失败:', error);
            this.showNotification('停止录制失败', 'error');
        }
    }
    
    /**
     * 开始录制计时器
     */
    startRecordingTimer() {
        this.stopRecordingTimer(); // 清除现有定时器
        
        this.recordingInterval = setInterval(() => {
            if (this.recordingStartTime) {
                const duration = Date.now() - this.recordingStartTime;
                const minutes = Math.floor(duration / 60000);
                const seconds = Math.floor((duration % 60000) / 1000);
                
                document.getElementById('recording-duration').textContent = 
                    `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                const badgeTime = document.getElementById('rec-badge-time');
                if (badgeTime) {
                    badgeTime.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                }
            }
        }, 1000);
    }
    
    /**
     * 停止录制计时器
     */
    stopRecordingTimer() {
        if (this.recordingInterval) {
            clearInterval(this.recordingInterval);
            this.recordingInterval = null;
        }
        
        document.getElementById('recording-duration').textContent = '00:00';
        this.recordingStartTime = null;
        const badgeTime = document.getElementById('rec-badge-time');
        if (badgeTime) badgeTime.textContent = '00:00';

    }

    beginStatusPolling() {
        this.endStatusPolling();
        this.statusInterval = setInterval(() => this.updateCameraStatus(), 1000);
    }
    endStatusPolling() {
        if (this.statusInterval) {
            clearInterval(this.statusInterval);
            this.statusInterval = null;
        }
    }

    async applySizeOnly(width, height) {
        const btn = document.getElementById('apply-resolution');
        try {
            if (btn) btn.disabled = true;
            this.showNotification('正在设置分辨率...', 'info');
            
            const params = new URLSearchParams({ width: String(width), height: String(height) });
            // 先停止预览，避免浏览器持有旧图像源导致卡死
            try { await this.stopPreview(); } catch(_){}
            const url = `/api/debug/camera/size?${params.toString()}`;
            console.debug('[applySizeOnly] POST', url);
            const resp = await fetch(url, { method: 'POST' });
            if (!resp.ok) {
                let detail = '设置分辨率失败';
                try {
                    const err = await resp.json();
                    detail = err.detail || detail;
                } catch (_) {
                    try { detail = await resp.text(); } catch(_){}
                }
                throw new Error(detail);
            }
            const data = await resp.json();
            const info = data?.info || {};
            const applied = info?.width && info?.height ? `${info.width}x${info.height}` : `${width}x${height}`;
            this.showNotification(`分辨率已应用: ${applied}`, 'success');
            // 重新启动预览，确保新分辨率生效
            await this.updateCameraStatus();
            await this.startPreview();
        } catch (e) {
            console.error('[applySizeOnly] error:', e);
            this.showNotification(`设置分辨率失败: ${e.message}`, 'error');
            // 尝试恢复预览
            try {
                await this.updateCameraStatus();
                if (this.cameraStatus.streaming) {
                    await this.startPreview();
                }
            } catch (recoveryError) {
                console.error('[applySizeOnly] recovery failed:', recoveryError);
            }
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    setRecOverlay(isRecording) {
        const container = document.getElementById('video-container');
        const badge = document.getElementById('rec-badge');
        if (!container || !badge) return;
        container.classList.toggle('recording-border', !!isRecording);
        badge.classList.toggle('show', !!isRecording);
    }
    
    /**
     * 更新曝光显示
     */
    updateExposureDisplay(value) {
        document.getElementById('exposure-value').textContent = value;
        this.currentSettings.exposure = value;
    }
    
    /**
     * 更新增益显示
     */
    updateGainDisplay(value) {
        document.getElementById('gain-value').textContent = value.toFixed(1);
        this.currentSettings.gain = value;
    }
    
    /**
     * 更新数字增益显示
     */
    updateDigitalGainDisplay(value) {
        document.getElementById('digital-gain-value').textContent = value.toFixed(1);
        this.currentSettings.digitalGain = value;
    }
    
    /**
     * 更新对比度显示
     */
    updateContrastDisplay(value) {
        document.getElementById('contrast-value').textContent = value.toFixed(1);
        this.currentSettings.contrast = value;
    }
    
    /**
     * 更新亮度显示
     */
    updateBrightnessDisplay(value) {
        document.getElementById('brightness-value').textContent = value.toFixed(1);
        this.currentSettings.brightness = value;
    }
    
    /**
     * 更新饱和度显示
     */
    updateSaturationDisplay(value) {
        document.getElementById('saturation-value').textContent = value.toFixed(1);
        this.currentSettings.saturation = value;
    }
    
    /**
     * 更新锐度显示
     */
    updateSharpnessDisplay(value) {
        document.getElementById('sharpness-value').textContent = value.toFixed(1);
        this.currentSettings.sharpness = value;
    }
    
    /**
     * 更新降噪级别显示
     */
    updateNoiseReductionDisplay(value) {
        document.getElementById('noise-reduction-value').textContent = value;
        this.currentSettings.noiseReduction = value;
    }
    
    /**
     * 更新白平衡模式
     */
    updateWhiteBalanceMode(mode) {
        this.currentSettings.whiteBalanceMode = mode;
        const gainsDiv = document.getElementById('white-balance-gains');
        if (mode === 'manual') {
            gainsDiv.style.display = 'block';
        } else {
            gainsDiv.style.display = 'none';
        }
    }
    
    /**
     * 更新白平衡红色增益
     */
    updateWhiteBalanceGainR(value) {
        document.getElementById('wb-gain-r-value').textContent = value.toFixed(1);
        this.currentSettings.whiteBalanceGainR = value;
    }
    
    /**
     * 更新白平衡蓝色增益
     */
    updateWhiteBalanceGainB(value) {
        document.getElementById('wb-gain-b-value').textContent = value.toFixed(1);
        this.currentSettings.whiteBalanceGainB = value;
    }
    
    /**
     * 应用设置
     */
    async applySettings() {
        try {
            // 应用基础参数
            const response = await fetch('/api/debug/camera/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    exposure: this.currentSettings.exposure,
                    gain: this.currentSettings.gain
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '应用基础设置失败');
            }
            
            // 应用图像增强参数
            await this.applyImageEnhancement();
            
            // 应用降噪设置
            await this.applyNoiseReduction();
            
            // 应用白平衡设置
            await this.applyWhiteBalance();
            
            this.showNotification('相机设置已应用', 'success');
            await this.updateCameraStatus();
            await this.updateImageQuality();
            
        } catch (error) {
            console.error('[DebugConsole] 应用设置失败:', error);
            this.showNotification(`应用设置失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 应用图像增强参数
     */
    async applyImageEnhancement() {
        const params = new URLSearchParams({
            contrast: this.currentSettings.contrast,
            brightness: this.currentSettings.brightness,
            saturation: this.currentSettings.saturation,
            sharpness: this.currentSettings.sharpness
        });
        
        const response = await fetch(`/api/debug/camera/image-enhancement?${params}`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '应用图像增强参数失败');
        }
    }
    
    /**
     * 应用降噪设置
     */
    async applyNoiseReduction() {
        const params = new URLSearchParams({
            level: this.currentSettings.noiseReduction
        });
        
        const response = await fetch(`/api/debug/camera/noise-reduction?${params}`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '应用降噪设置失败');
        }
    }
    
    /**
     * 应用白平衡设置
     */
    async applyWhiteBalance() {
        const params = new URLSearchParams({
            mode: this.currentSettings.whiteBalanceMode,
            gain_r: this.currentSettings.whiteBalanceGainR,
            gain_b: this.currentSettings.whiteBalanceGainB
        });
        
        const response = await fetch(`/api/debug/camera/white-balance?${params}`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '应用白平衡设置失败');
        }
    }
    
    /**
     * 应用夜间模式预设
     */
    async applyNightModePreset() {
        try {
            const response = await fetch('/api/debug/camera/night-mode-preset', {
                method: 'POST'
            });
            
            if (response.ok) {
                const result = await response.json();
                this.showNotification('夜间模式预设已应用', 'success');
                
                // 更新UI显示
                await this.updateCameraStatus();
                await this.updateImageQuality();
                
                // 更新当前设置
                if (result.preset) {
                    this.currentSettings.exposure = result.preset.exposure_us;
                    this.currentSettings.gain = result.preset.analogue_gain;
                    this.currentSettings.digitalGain = result.preset.digital_gain;
                    this.currentSettings.noiseReduction = result.preset.noise_reduction;
                    this.currentSettings.whiteBalanceMode = result.preset.white_balance_mode;
                    this.currentSettings.contrast = result.preset.contrast;
                    this.currentSettings.brightness = result.preset.brightness;
                    this.currentSettings.saturation = result.preset.saturation;
                    this.currentSettings.sharpness = result.preset.sharpness;
                    this.currentSettings.nightMode = result.preset.night_mode;
                    
                    this.updateAllDisplays();
                }
            } else {
                const error = await response.json();
                throw new Error(error.detail || '应用夜间模式预设失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 应用夜间模式预设失败:', error);
            this.showNotification(`应用夜间模式预设失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 切换夜间模式
     */
    async toggleNightMode() {
        try {
            const enabled = !this.currentSettings.nightMode;
            const params = new URLSearchParams({ enabled: enabled });
            
            const response = await fetch(`/api/debug/camera/night-mode?${params}`, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.currentSettings.nightMode = enabled;
                const modeText = enabled ? '启用' : '关闭';
                this.showNotification(`夜间模式已${modeText}`, 'success');
                
                // 更新UI显示
                document.getElementById('night-mode-status').textContent = enabled ? '开启' : '关闭';
                await this.updateImageQuality();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '切换夜间模式失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 切换夜间模式失败:', error);
            this.showNotification(`切换夜间模式失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 备份设置
     */
    async backupSettings() {
        try {
            const response = await fetch('/api/debug/camera/backup-settings', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification('设置已备份', 'success');
            } else {
                const error = await response.json();
                throw new Error(error.detail || '备份设置失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 备份设置失败:', error);
            this.showNotification(`备份设置失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 恢复设置
     */
    async restoreSettings() {
        if (!confirm('确定要恢复备份的设置吗？这将覆盖当前的所有设置。')) {
            return;
        }
        
        try {
            const response = await fetch('/api/debug/camera/restore-settings', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification('设置已恢复', 'success');
                
                // 重新加载相机状态
                await this.updateCameraStatus();
                await this.updateImageQuality();
                this.updateAllDisplays();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '恢复设置失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 恢复设置失败:', error);
            this.showNotification(`恢复设置失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 更新图像质量监控 - 基于实际图像分析
     */
    async updateImageQuality() {
        try {
            console.log('[QualityMonitoring] 正在获取图像质量数据...');
            
            // 获取相机参数
            const response = await fetch('/api/debug/camera/image-quality');
            if (!response.ok) {
                console.error('[QualityMonitoring] API请求失败:', response.status);
                return;
            }
            
            const result = await response.json();
            if (!result.success || !result.quality) {
                console.warn('[QualityMonitoring] API返回数据格式异常:', result);
                return;
            }
            
            const quality = result.quality;
            const cameraParams = quality.camera_params || {};
            
            // 基于实际预览图像进行分析
            const previewImg = document.getElementById('preview-image');
            if (previewImg && previewImg.src && !previewImg.src.includes('placeholder')) {
                try {
                    const imageAnalysis = this.analyzeImageQuality(previewImg, cameraParams);
                    
                    // 更新质量条
                    this.updateQualityBar('noise-level-bar', imageAnalysis.noise_level);
                    this.updateQualityBar('exposure-bar', imageAnalysis.exposure_adequacy);
                    this.updateQualityBar('gain-bar', quality.gain_level);
                    
                    // 更新数值显示
                    const noiseElement = document.getElementById('noise-level');
                    const exposureElement = document.getElementById('exposure-level');
                    const gainElement = document.getElementById('gain-level');
                    
                    if (noiseElement) noiseElement.textContent = (imageAnalysis.noise_level * 100).toFixed(0) + '%';
                    if (exposureElement) exposureElement.textContent = (imageAnalysis.exposure_adequacy * 100).toFixed(0) + '%';
                    if (gainElement) gainElement.textContent = (quality.gain_level * 100).toFixed(0) + '%';
                    
                    // 更新建议
                    this.updateRecommendations(imageAnalysis.recommendations);
                    
                    console.log('[QualityMonitoring] 基于实际图像的质量分析完成:', imageAnalysis);
                } catch (error) {
                    console.warn('[QualityMonitoring] 图像分析失败，使用参数估算:', error);
                    this.updateImageQualityFromParams(quality);
                }
            } else {
                console.log('[QualityMonitoring] 预览图像不可用，使用参数估算');
                this.updateImageQualityFromParams(quality);
            }
            
            // 更新夜间模式状态
            const nightModeElement = document.getElementById('night-mode-status');
            if (nightModeElement) {
                nightModeElement.textContent = quality.night_mode ? '开启' : '关闭';
            }
            this.currentSettings.nightMode = quality.night_mode;
            
            // 如果直方图可见，同时更新直方图（前端计算）
            if (this.histogramVisible) {
                this.updateHistogram();
            }
            
        } catch (error) {
            console.error('[QualityMonitoring] 更新图像质量失败:', error);
        }
    }
    
    /**
     * 基于参数更新图像质量（回退方案）
     */
    updateImageQualityFromParams(quality) {
        // 使用后端计算的质量指标
        const noiseLevel = quality.noise_level || 0.0;
        const exposureAdequacy = quality.exposure_adequacy || 0.0;
        const gainLevel = quality.gain_level || 0.0;
        
        // 更新UI
        this.updateQualityBar('noise-level-bar', noiseLevel);
        this.updateQualityBar('exposure-bar', exposureAdequacy);
        this.updateQualityBar('gain-bar', gainLevel);
        
        const noiseElement = document.getElementById('noise-level');
        const exposureElement = document.getElementById('exposure-level');
        const gainElement = document.getElementById('gain-level');
        
        if (noiseElement) noiseElement.textContent = (noiseLevel * 100).toFixed(0) + '%';
        if (exposureElement) exposureElement.textContent = (exposureAdequacy * 100).toFixed(0) + '%';
        if (gainElement) gainElement.textContent = (gainLevel * 100).toFixed(0) + '%';
        
        // 使用后端生成的建议
        const recommendations = quality.recommended_adjustments || [];
        this.updateRecommendations(recommendations);
        
        console.log('[QualityMonitoring] 使用后端计算的质量指标:', {
            noise_level: noiseLevel,
            exposure_adequacy: exposureAdequacy,
            gain_level: gainLevel
        });
    }
    
    /**
     * 分析图像质量 - 基于实际图像
     */
    analyzeImageQuality(imageElement, cameraParams) {
        try {
            // 创建临时canvas来分析图像
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            
            // 设置canvas尺寸
            canvas.width = imageElement.naturalWidth || imageElement.width;
            canvas.height = imageElement.naturalHeight || imageElement.height;
            
            // 绘制图像到canvas
            ctx.drawImage(imageElement, 0, 0);
            
            // 获取图像数据
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const data = imageData.data;
            
            // 计算图像统计信息
            const stats = this.calculateImageStats(data, canvas.width, canvas.height);
            
            // 计算噪点水平
            const noiseLevel = this.calculateNoiseLevel(data, canvas.width, canvas.height, cameraParams);
            
            // 计算曝光充足度
            const exposureAdequacy = this.calculateExposureAdequacy(stats);
            
            // 生成建议
            const recommendations = this.generateImageBasedRecommendations(stats, noiseLevel, exposureAdequacy, cameraParams);
            
            return {
                noise_level: Math.min(1.0, noiseLevel),
                exposure_adequacy: Math.min(1.0, exposureAdequacy),
                recommendations: recommendations,
                image_stats: stats
            };
            
        } catch (error) {
            console.error('图像质量分析失败:', error);
            throw error;
        }
    }
    
    /**
     * 计算图像统计信息
     */
    calculateImageStats(data, width, height) {
        let totalBrightness = 0;
        let totalPixels = 0;
        const histogram = new Array(256).fill(0);
        
        // 计算亮度和直方图
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            
            // 计算灰度值
            const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
            
            histogram[gray]++;
            totalBrightness += gray;
            totalPixels++;
        }
        
        const meanBrightness = totalBrightness / totalPixels;
        
        // 计算标准差
        let variance = 0;
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
            variance += Math.pow(gray - meanBrightness, 2);
        }
        const stdBrightness = Math.sqrt(variance / totalPixels);
        
        // 计算暗部、中部、亮部像素比例
        const darkPixels = histogram.slice(0, 50).reduce((sum, count) => sum + count, 0) / totalPixels;
        const midPixels = histogram.slice(50, 200).reduce((sum, count) => sum + count, 0) / totalPixels;
        const brightPixels = histogram.slice(200, 256).reduce((sum, count) => sum + count, 0) / totalPixels;
        
        return {
            mean_brightness: meanBrightness,
            std_brightness: stdBrightness,
            dark_pixels_percent: darkPixels * 100,
            mid_pixels_percent: midPixels * 100,
            bright_pixels_percent: brightPixels * 100,
            total_pixels: totalPixels
        };
    }
    
    /**
     * 计算噪点水平
     */
    calculateNoiseLevel(data, width, height, cameraParams) {
        try {
            // 改进的噪点检测：基于相邻像素的差异
            let noiseSum = 0;
            let noiseCount = 0;
            
            // 采样检测（减少计算量）
            const step = Math.max(1, Math.floor(width * height / 8000)); // 检测更多像素以提高准确性
            
            for (let i = 0; i < data.length - 12; i += step * 4) {
                const x = (i / 4) % width;
                const y = Math.floor((i / 4) / width);
                
                if (x < width - 1 && y < height - 1) {
                    // 计算当前像素的灰度值
                    const r1 = data[i];
                    const g1 = data[i + 1];
                    const b1 = data[i + 2];
                    const gray1 = 0.299 * r1 + 0.587 * g1 + 0.114 * b1;
                    
                    // 计算右侧像素的灰度值
                    const r2 = data[i + 4];
                    const g2 = data[i + 5];
                    const b2 = data[i + 6];
                    const gray2 = 0.299 * r2 + 0.587 * g2 + 0.114 * b2;
                    
                    // 计算下方像素的灰度值
                    const r3 = data[i + width * 4];
                    const g3 = data[i + width * 4 + 1];
                    const b3 = data[i + width * 4 + 2];
                    const gray3 = 0.299 * r3 + 0.587 * g3 + 0.114 * b3;
                    
                    // 计算局部变化
                    const horizontalDiff = Math.abs(gray1 - gray2);
                    const verticalDiff = Math.abs(gray1 - gray3);
                    const localNoise = (horizontalDiff + verticalDiff) / 2;
                    
                    noiseSum += localNoise;
                    noiseCount++;
                }
            }
            
            const avgNoise = noiseSum / noiseCount;
            
            // 改进的归一化噪点水平 (0-1)
            // 降低阈值，使噪点检测更敏感
            let noiseLevel = Math.min(1.0, avgNoise / 30.0); // 从50.0降低到30.0
            
            // 确保最小噪点水平不为0
            noiseLevel = Math.max(0.05, noiseLevel);
            
            // 考虑增益对噪点的影响（更敏感）
            const analogueGain = cameraParams.analogue_gain || 1.0;
            const gainFactor = Math.min(2.5, analogueGain / 6.0); // 从8.0降低到6.0
            noiseLevel *= gainFactor;
            
            // 考虑降噪效果
            const noiseReduction = cameraParams.noise_reduction || 0;
            const noiseReductionEffect = noiseReduction * 0.25; // 从0.2增加到0.25
            noiseLevel = Math.max(0.05, noiseLevel - noiseReductionEffect);
            
            // 夜间模式会增加噪点
            if (cameraParams.night_mode) {
                noiseLevel *= 1.3;
            }
            
            // 曝光时间过短会增加噪点
            const exposureUs = cameraParams.exposure_us || 10000;
            if (exposureUs < 5000) {
                noiseLevel *= 1.2;
            } else if (exposureUs < 10000) {
                noiseLevel *= 1.1;
            }
            
            return Math.min(1.0, noiseLevel);
            
        } catch (error) {
            console.warn('噪点计算失败:', error);
            // 改进的回退方案：基于增益的估算
            const analogueGain = cameraParams.analogue_gain || 1.0;
            if (analogueGain >= 16.0) return 0.7;
            else if (analogueGain >= 12.0) return 0.6;
            else if (analogueGain >= 8.0) return 0.5;
            else if (analogueGain >= 4.0) return 0.35;
            else if (analogueGain >= 2.0) return 0.25;
            else if (analogueGain >= 1.5) return 0.15;
            else return 0.1; // 确保不会为0
        }
    }
    
    /**
     * 计算曝光充足度
     */
    calculateExposureAdequacy(stats) {
        const { mean_brightness, dark_pixels_percent, bright_pixels_percent } = stats;
        
        let exposureScore = 1.0;
        
        // 检查是否过暗
        if (dark_pixels_percent > 60) {
            exposureScore *= 0.5;
        } else if (dark_pixels_percent > 40) {
            exposureScore *= 0.8;
        }
        
        // 检查是否过亮
        if (bright_pixels_percent > 40) {
            exposureScore *= 0.7;
        } else if (bright_pixels_percent > 20) {
            exposureScore *= 0.9;
        }
        
        // 检查平均亮度
        if (mean_brightness < 50) {
            exposureScore *= 0.6;
        } else if (mean_brightness < 80) {
            exposureScore *= 0.8;
        } else if (mean_brightness > 200) {
            exposureScore *= 0.7;
        }
        
        return Math.min(1.0, exposureScore);
    }
    
    /**
     * 生成基于图像的建议
     */
    generateImageBasedRecommendations(stats, noiseLevel, exposureAdequacy, cameraParams) {
        const recommendations = [];
        
        // 噪点建议
        if (noiseLevel > 0.6) {
            recommendations.push("检测到高噪点水平，建议降低增益或启用降噪");
        } else if (noiseLevel > 0.4) {
            recommendations.push("噪点水平中等，可考虑适当降低增益");
        } else if (noiseLevel < 0.1) {
            recommendations.push("噪点水平很低，图像质量良好");
        }
        
        // 曝光建议
        if (exposureAdequacy < 0.5) {
            recommendations.push("图像曝光不足，建议增加曝光时间或增益");
        } else if (exposureAdequacy > 0.9) {
            recommendations.push("图像曝光充足，当前设置良好");
        }
        
        // 亮度分布建议
        if (stats.mean_brightness < 50) {
            recommendations.push("图像整体偏暗，建议增加曝光时间");
        } else if (stats.mean_brightness > 200) {
            recommendations.push("图像整体偏亮，建议减少曝光时间");
        }
        
        // 如果没有建议，提供正面反馈
        if (recommendations.length === 0) {
            recommendations.push("当前设置良好，图像质量稳定");
        }
        
        return recommendations;
    }
    
    /**
     * 生成基于参数的建议
     */
    generateParameterBasedRecommendations(cameraParams) {
        const recommendations = [];
        const analogueGain = cameraParams.analogue_gain || 1.0;
        const exposureUs = cameraParams.exposure_us || 10000;
        const noiseReduction = cameraParams.noise_reduction || 0;
        
        // 增益建议
        if (analogueGain > 12.0) {
            recommendations.push("增益过高，建议降低以减少噪点");
        } else if (analogueGain < 1.5 && cameraParams.night_mode) {
            recommendations.push("夜间模式建议适当增加增益");
        }
        
        // 曝光建议
        if (exposureUs < 10000) {
            recommendations.push("曝光时间较短，可适当增加以获得更好画质");
        } else if (exposureUs > 50000) {
            recommendations.push("曝光时间较长，注意避免运动模糊");
        }
        
        // 降噪建议
        if (noiseReduction === 0 && analogueGain > 4.0) {
            recommendations.push("建议启用降噪功能");
        }
        
        if (recommendations.length === 0) {
            recommendations.push("当前设置良好，图像质量稳定");
        }
        
        return recommendations;
    }
    
    /**
     * 更新质量条
     */
    updateQualityBar(barId, value) {
        const bar = document.getElementById(barId);
        if (bar) {
            bar.style.width = (value * 100) + '%';
        }
    }
    
    /**
     * 更新建议显示
     */
    updateRecommendations(recommendations) {
        const container = document.getElementById('quality-recommendations');
        if (!container) return;
        
        if (recommendations && recommendations.length > 0) {
            container.innerHTML = `
                <h5>调整建议</h5>
                ${recommendations.map(rec => `<div class="recommendation-item">${rec}</div>`).join('')}
            `;
        } else {
            container.innerHTML = '<h5>调整建议</h5><div class="recommendation-item">当前设置良好，无需调整</div>';
        }
    }
    
    /**
     * 更新所有显示
     */
    updateAllDisplays() {
        this.updateExposureDisplay(this.currentSettings.exposure);
        this.updateGainDisplay(this.currentSettings.gain);
        this.updateDigitalGainDisplay(this.currentSettings.digitalGain);
        this.updateContrastDisplay(this.currentSettings.contrast);
        this.updateBrightnessDisplay(this.currentSettings.brightness);
        this.updateSaturationDisplay(this.currentSettings.saturation);
        this.updateSharpnessDisplay(this.currentSettings.sharpness);
        this.updateNoiseReductionDisplay(this.currentSettings.noiseReduction);
        
        // 更新白平衡模式
        const wbSelect = document.getElementById('white-balance-mode');
        if (wbSelect) {
            wbSelect.value = this.currentSettings.whiteBalanceMode;
            this.updateWhiteBalanceMode(this.currentSettings.whiteBalanceMode);
        }
        
        this.updateWhiteBalanceGainR(this.currentSettings.whiteBalanceGainR);
        this.updateWhiteBalanceGainB(this.currentSettings.whiteBalanceGainB);
    }
    
    /**
     * 启动图像质量监控
     */
    startQualityMonitoring() {
        this.stopQualityMonitoring(); // 清除现有定时器
        
        console.log('[QualityMonitoring] 启动图像质量监控...');
        
        // 立即更新一次
        this.updateImageQuality();
        
        // 每3秒更新一次质量指标（更频繁的更新）
        this.qualityMonitoringInterval = setInterval(() => {
            this.updateImageQuality();
        }, 3000);
        
        // 初始化直方图
        this.initHistogram();
        
        console.log('[QualityMonitoring] 图像质量监控已启动');
    }
    
    /**
     * 停止图像质量监控
     */
    stopQualityMonitoring() {
        if (this.qualityMonitoringInterval) {
            clearInterval(this.qualityMonitoringInterval);
            this.qualityMonitoringInterval = null;
            console.log('[QualityMonitoring] 图像质量监控已停止');
        }
    }
    
    /**
     * 初始化直方图
     */
    initHistogram() {
        this.histogramCanvas = document.getElementById('histogram-canvas');
        if (this.histogramCanvas) {
            this.histogramCtx = this.histogramCanvas.getContext('2d');
            
            // 绑定事件
            const toggleBtn = document.getElementById('toggle-histogram');
            const typeSelect = document.getElementById('histogram-type');
            
            if (toggleBtn) {
                toggleBtn.addEventListener('click', () => this.toggleHistogram());
            }
            
            if (typeSelect) {
                typeSelect.addEventListener('change', (e) => {
                    this.histogramType = e.target.value;
                    if (this.histogramVisible) {
                        this.updateHistogram();
                    }
                });
            }
        }
    }
    
    /**
     * 切换直方图显示
     */
    toggleHistogram() {
        this.histogramVisible = !this.histogramVisible;
        const display = document.getElementById('histogram-display');
        const toggleBtn = document.getElementById('toggle-histogram');
        
        if (display && toggleBtn) {
            if (this.histogramVisible) {
                display.style.display = 'block';
                toggleBtn.textContent = '隐藏直方图';
                this.updateHistogram();
            } else {
                display.style.display = 'none';
                toggleBtn.textContent = '显示直方图';
            }
        }
    }
    
    /**
     * 更新直方图
     */
    async updateHistogram() {
        if (!this.histogramVisible || !this.histogramCtx) {
            return;
        }
        
        try {
            // 获取预览图像
            const previewImg = document.getElementById('preview-image');
            if (!previewImg || !previewImg.src || previewImg.src.includes('placeholder')) {
                console.warn('预览图像不可用，等待有效图像...');
                return;
            }
            
            // 创建临时canvas来分析图像
            const tempCanvas = document.createElement('canvas');
            const tempCtx = tempCanvas.getContext('2d');
            
            // 设置canvas尺寸
            tempCanvas.width = previewImg.naturalWidth || previewImg.width;
            tempCanvas.height = previewImg.naturalHeight || previewImg.height;
            
            // 绘制图像到canvas
            tempCtx.drawImage(previewImg, 0, 0);
            
            // 获取图像数据
            const imageData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
            const histogramData = this.calculateHistogram(imageData);
            
            // 绘制直方图
            this.drawHistogram(histogramData);
            this.updateHistogramStats(histogramData);
            
        } catch (error) {
            console.error('获取直方图数据失败:', error);
        }
    }
    
    /**
     * 计算图像直方图
     */
    calculateHistogram(imageData) {
        const data = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        
        // 初始化直方图数组
        const histogram = new Array(256).fill(0);
        const rgbHistogram = {
            r: new Array(256).fill(0),
            g: new Array(256).fill(0),
            b: new Array(256).fill(0)
        };
        
        let totalPixels = 0;
        let sumBrightness = 0;
        let sumSquaredBrightness = 0;
        
        // 计算直方图
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            
            // RGB直方图
            rgbHistogram.r[r]++;
            rgbHistogram.g[g]++;
            rgbHistogram.b[b]++;
            
            // 计算灰度值 (使用标准权重)
            const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
            histogram[gray]++;
            
            totalPixels++;
            sumBrightness += gray;
            sumSquaredBrightness += gray * gray;
        }
        
        // 归一化直方图（转换为百分比）
        const normalizedHistogram = histogram.map(count => (count / totalPixels) * 100);
        
        // 计算统计信息
        const meanBrightness = sumBrightness / totalPixels;
        const variance = (sumSquaredBrightness / totalPixels) - (meanBrightness * meanBrightness);
        const stdBrightness = Math.sqrt(variance);
        
        // 计算曝光分析
        const darkPixels = histogram.slice(0, 50).reduce((sum, count) => sum + count, 0) / totalPixels * 100;
        const brightPixels = histogram.slice(200, 256).reduce((sum, count) => sum + count, 0) / totalPixels * 100;
        const midPixels = histogram.slice(50, 200).reduce((sum, count) => sum + count, 0) / totalPixels * 100;
        
        return {
            histogram: normalizedHistogram,
            rgb_histogram: {
                r: rgbHistogram.r.map(count => (count / totalPixels) * 100),
                g: rgbHistogram.g.map(count => (count / totalPixels) * 100),
                b: rgbHistogram.b.map(count => (count / totalPixels) * 100)
            },
            statistics: {
                mean_brightness: Math.round(meanBrightness * 10) / 10,
                std_brightness: Math.round(stdBrightness * 10) / 10,
                dark_pixels_percent: Math.round(darkPixels * 10) / 10,
                bright_pixels_percent: Math.round(brightPixels * 10) / 10,
                mid_pixels_percent: Math.round(midPixels * 10) / 10
            },
            exposure_analysis: {
                is_underexposed: darkPixels > 60,
                is_overexposed: brightPixels > 30,
                is_well_exposed: darkPixels >= 20 && darkPixels <= 40 && brightPixels >= 10 && brightPixels <= 30,
                dynamic_range: Math.round(stdBrightness * 10) / 10
            }
        };
    }
    
    /**
     * 绘制直方图
     */
    drawHistogram(histogramData) {
        const canvas = this.histogramCanvas;
        const ctx = this.histogramCtx;
        
        if (!canvas || !ctx) return;
        
        const width = canvas.width;
        const height = canvas.height;
        
        // 清除画布
        ctx.clearRect(0, 0, width, height);
        
        // 设置背景
        ctx.fillStyle = '#1a1a1a';
        ctx.fillRect(0, 0, width, height);
        
        if (this.histogramType === 'grayscale') {
            this.drawGrayscaleHistogram(ctx, histogramData.histogram, width, height);
        } else {
            this.drawRGBHistogram(ctx, histogramData.rgb_histogram, width, height);
        }
        
        // 绘制网格线
        this.drawHistogramGrid(ctx, width, height);
    }
    
    /**
     * 绘制灰度直方图
     */
    drawGrayscaleHistogram(ctx, histogram, width, height) {
        if (!histogram || histogram.length === 0) return;
        
        const maxValue = Math.max(...histogram);
        const barWidth = width / histogram.length;
        
        ctx.fillStyle = '#e0e0e0';
        
        for (let i = 0; i < histogram.length; i++) {
            const barHeight = (histogram[i] / maxValue) * height;
            const x = i * barWidth;
            const y = height - barHeight;
            
            ctx.fillRect(x, y, barWidth, barHeight);
        }
    }
    
    /**
     * 绘制RGB直方图
     */
    drawRGBHistogram(ctx, rgbHistogram, width, height) {
        if (!rgbHistogram || !rgbHistogram.r || !rgbHistogram.g || !rgbHistogram.b) return;
        
        const maxValue = Math.max(
            Math.max(...rgbHistogram.r),
            Math.max(...rgbHistogram.g),
            Math.max(...rgbHistogram.b)
        );
        
        const barWidth = width / rgbHistogram.r.length;
        
        // 绘制R通道
        ctx.fillStyle = 'rgba(255, 0, 0, 0.7)';
        for (let i = 0; i < rgbHistogram.r.length; i++) {
            const barHeight = (rgbHistogram.r[i] / maxValue) * height;
            const x = i * barWidth;
            const y = height - barHeight;
            ctx.fillRect(x, y, barWidth, barHeight);
        }
        
        // 绘制G通道
        ctx.fillStyle = 'rgba(0, 255, 0, 0.7)';
        for (let i = 0; i < rgbHistogram.g.length; i++) {
            const barHeight = (rgbHistogram.g[i] / maxValue) * height;
            const x = i * barWidth;
            const y = height - barHeight;
            ctx.fillRect(x, y, barWidth, barHeight);
        }
        
        // 绘制B通道
        ctx.fillStyle = 'rgba(0, 0, 255, 0.7)';
        for (let i = 0; i < rgbHistogram.b.length; i++) {
            const barHeight = (rgbHistogram.b[i] / maxValue) * height;
            const x = i * barWidth;
            const y = height - barHeight;
            ctx.fillRect(x, y, barWidth, barHeight);
        }
    }
    
    /**
     * 绘制直方图网格
     */
    drawHistogramGrid(ctx, width, height) {
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.lineWidth = 1;
        
        // 水平网格线
        for (let i = 0; i <= 4; i++) {
            const y = (height / 4) * i;
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(width, y);
            ctx.stroke();
        }
        
        // 垂直网格线
        for (let i = 0; i <= 4; i++) {
            const x = (width / 4) * i;
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, height);
            ctx.stroke();
        }
    }
    
    /**
     * 更新直方图统计信息
     */
    updateHistogramStats(histogramData) {
        const statsContainer = document.getElementById('histogram-stats');
        if (!statsContainer || !histogramData.statistics) return;
        
        const stats = histogramData.statistics;
        const analysis = histogramData.exposure_analysis;
        
        statsContainer.innerHTML = `
            <div class="histogram-stat-item">
                <span class="histogram-stat-label">平均亮度</span>
                <span class="histogram-stat-value">${stats.mean_brightness}</span>
            </div>
            <div class="histogram-stat-item">
                <span class="histogram-stat-label">亮度标准差</span>
                <span class="histogram-stat-value">${stats.std_brightness}</span>
            </div>
            <div class="histogram-stat-item">
                <span class="histogram-stat-label">暗部像素</span>
                <span class="histogram-stat-value">${stats.dark_pixels_percent}%</span>
            </div>
            <div class="histogram-stat-item">
                <span class="histogram-stat-label">亮部像素</span>
                <span class="histogram-stat-value">${stats.bright_pixels_percent}%</span>
            </div>
            <div class="histogram-stat-item">
                <span class="histogram-stat-label">中部像素</span>
                <span class="histogram-stat-value">${stats.mid_pixels_percent}%</span>
            </div>
            <div class="histogram-stat-item">
                <span class="histogram-stat-label">动态范围</span>
                <span class="histogram-stat-value">${analysis.dynamic_range}</span>
            </div>
        `;
        
        // 添加曝光分析
        let analysisClass = 'well-exposed';
        let analysisText = '曝光良好';
        
        if (analysis.is_underexposed) {
            analysisClass = 'underexposed';
            analysisText = '曝光不足';
        } else if (analysis.is_overexposed) {
            analysisClass = 'overexposed';
            analysisText = '曝光过度';
        }
        
        const analysisDiv = document.createElement('div');
        analysisDiv.className = `histogram-exposure-analysis ${analysisClass}`;
        analysisDiv.innerHTML = `
            <strong>曝光分析:</strong> ${analysisText}<br>
            <small>暗部: ${stats.dark_pixels_percent}% | 亮部: ${stats.bright_pixels_percent}% | 动态范围: ${analysis.dynamic_range}</small>
        `;
        
        statsContainer.appendChild(analysisDiv);
    }
    
    /**
     * 重置设置
     */
    async resetSettings() {
        try {
            const response = await fetch('/api/debug/camera/reset', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification('相机已重置到默认设置', 'success');
                
                // 重新加载相机状态以获取默认值
                await this.updateCameraStatus();
                
                // 更新UI显示
                if (this.cameraStatus.info) {
                    this.updateExposureDisplay(this.cameraStatus.info.exposure_us);
                    this.updateGainDisplay(this.cameraStatus.info.analogue_gain);
                    this.updateDigitalGainDisplay(this.cameraStatus.info.digital_gain || 1.0);
                }
            } else {
                const error = await response.json();
                throw new Error(error.detail || '重置设置失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 重置设置失败:', error);
            this.showNotification(`重置设置失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 加载预设
     */
    async loadPresets() {
        try {
            const response = await fetch('/api/debug/camera/presets');
            const data = await response.json();
            
            this.presets = data.presets || [];
            this.renderPresets();
            
        } catch (error) {
            console.error('[DebugConsole] 加载预设失败:', error);
            this.showNotification('加载预设失败', 'error');
        }
    }
    
    /**
     * 渲染预设列表
     */
    renderPresets() {
        const presetsGrid = document.getElementById('presets-grid');
        
        if (this.presets.length === 0) {
            presetsGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">💾</div>
                    <div class="empty-state-text">暂无预设</div>
                    <div class="empty-state-subtext">保存当前设置作为预设</div>
                </div>
            `;
            return;
        }
        
        presetsGrid.innerHTML = this.presets.map(preset => `
            <div class="preset-item">
                <div class="preset-name">${preset.name}</div>
                <div class="preset-description">${preset.description || '无描述'}</div>
                <div class="preset-params">
                    曝光: ${preset.exposure_us}μs | 增益: ${preset.analogue_gain}x
                </div>
                <div class="preset-actions">
                    <button class="btn btn-primary" onclick="window.debugConsole.applyPreset('${preset.name}')">
                        应用
                    </button>
                    <button class="btn btn-error" onclick="window.debugConsole.deletePreset('${preset.name}')">
                        删除
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    /**
     * 保存预设
     */
    async savePreset() {
        const name = document.getElementById('preset-name').value.trim();
        const description = document.getElementById('preset-description').value.trim();
        
        if (!name) {
            this.showNotification('请输入预设名称', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/debug/camera/presets', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: name,
                    description: description,
                    exposure_us: this.currentSettings.exposure,
                    analogue_gain: this.currentSettings.gain,
                    digital_gain: this.currentSettings.digitalGain
                })
            });
            
            if (response.ok) {
                this.showNotification('预设保存成功', 'success');
                
                // 清空表单
                document.getElementById('preset-name').value = '';
                document.getElementById('preset-description').value = '';
                
                // 重新加载预设
                await this.loadPresets();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '保存预设失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 保存预设失败:', error);
            this.showNotification(`保存预设失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 应用预设
     */
    async applyPreset(presetName) {
        try {
            const response = await fetch(`/api/debug/camera/presets/${encodeURIComponent(presetName)}/apply`, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification(`预设 '${presetName}' 已应用`, 'success');
                
                // 重新加载相机状态
                await this.updateCameraStatus();
                
                // 更新UI显示
                if (this.cameraStatus.info) {
                    this.updateExposureDisplay(this.cameraStatus.info.exposure_us);
                    this.updateGainDisplay(this.cameraStatus.info.analogue_gain);
                    this.updateDigitalGainDisplay(this.cameraStatus.info.digital_gain || 1.0);
                }
            } else {
                const error = await response.json();
                throw new Error(error.detail || '应用预设失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 应用预设失败:', error);
            this.showNotification(`应用预设失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 删除预设
     */
    async deletePreset(presetName) {
        if (!confirm(`确定要删除预设 '${presetName}' 吗？`)) {
            return;
        }
        
        try {
            const response = await fetch(`/api/debug/camera/presets/${encodeURIComponent(presetName)}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                this.showNotification(`预设 '${presetName}' 已删除`, 'success');
                await this.loadPresets();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '删除预设失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 删除预设失败:', error);
            this.showNotification(`删除预设失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 加载文件列表
     */
    async loadFiles() {
        try {
            const response = await fetch('/api/debug/files');
            const data = await response.json();
            
            this.files = data.files || [];
            this.renderFiles();
            
        } catch (error) {
            console.error('[DebugConsole] 加载文件列表失败:', error);
            this.showNotification('加载文件列表失败', 'error');
        }
    }
    
    /**
     * 渲染文件列表
     */
    renderFiles() {
        const filesList = document.getElementById('files-list');
        
        if (this.files.length === 0) {
            filesList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📁</div>
                    <div class="empty-state-text">暂无文件</div>
                    <div class="empty-state-subtext">开始拍摄或录制视频</div>
                </div>
            `;
            return;
        }
        
        filesList.innerHTML = this.files.map(file => {
            const icon = file.type === 'image' ? '📷' : '🎥';
            const size = this.formatFileSize(file.size);
            const modified = new Date(file.modified).toLocaleString();
            
            return `
                <div class="file-item">
                    <div class="file-icon">${icon}</div>
                    <div class="file-info">
                        <div class="file-name">${file.name}</div>
                        <div class="file-meta">${size} • ${modified}</div>
                    </div>
                    <div class="file-actions">
                        <button class="btn btn-info" onclick="window.debugConsole.downloadFile('${file.name}')">
                            下载
                        </button>
                        <button class="btn btn-secondary" onclick="window.debugConsole.showFileInfo('${file.name}')">
                            详情
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    /**
     * 下载文件
     */
    downloadFile(filename) {
        const link = document.createElement('a');
        link.href = `/api/debug/files/${encodeURIComponent(filename)}`;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        this.showNotification(`开始下载: ${filename}`, 'info');
    }
    
    /**
     * 显示文件信息
     */
    async showFileInfo(filename) {
        try {
            const response = await fetch(`/api/debug/files/${encodeURIComponent(filename)}/info`);
            const info = await response.json();
            
            const infoHtml = `
                <div class="file-info-detail">
                    <h3>📄 ${info.filename}</h3>
                    <div class="info-grid">
                        <div class="info-item">
                            <span class="info-label">文件大小:</span>
                            <span class="info-value">${this.formatFileSize(info.size)}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">修改时间:</span>
                            <span class="info-value">${new Date(info.modified).toLocaleString()}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">文件类型:</span>
                            <span class="info-value">${info.type === 'image' ? '图片' : '视频'}</span>
                        </div>
                        ${info.exposure_us ? `
                        <div class="info-item">
                            <span class="info-label">曝光时间:</span>
                            <span class="info-value">${info.exposure_us}μs</span>
                        </div>
                        ` : ''}
                        ${info.analogue_gain ? `
                        <div class="info-item">
                            <span class="info-label">模拟增益:</span>
                            <span class="info-value">${info.analogue_gain}x</span>
                        </div>
                        ` : ''}
                        ${info.resolution ? `
                        <div class="info-item">
                            <span class="info-label">分辨率:</span>
                            <span class="info-value">${info.resolution}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>
            `;
            
            this.showModal('文件信息', infoHtml);
            
        } catch (error) {
            console.error('[DebugConsole] 获取文件信息失败:', error);
            this.showNotification('获取文件信息失败', 'error');
        }
    }
    
    /**
     * 格式化文件大小
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    /**
     * 更新按钮状态
     */
    updateButtonStates() {
        const startBtn = document.getElementById('start-preview');
        const stopBtn = document.getElementById('stop-preview');
        
        if (startBtn) {
            startBtn.disabled = this.cameraStatus.streaming;
            if (this.cameraStatus.streaming) {
                startBtn.classList.add('disabled');
            } else {
                startBtn.classList.remove('disabled');
            }
        }
        
        if (stopBtn) {
            stopBtn.disabled = !this.cameraStatus.streaming;
            if (!this.cameraStatus.streaming) {
                stopBtn.classList.add('disabled');
            } else {
                stopBtn.classList.remove('disabled');
            }
        }
    }
    
    /**
     * 更新录制按钮状态
     */
    updateRecordingButtons(isRecording) {
        const startBtn = document.getElementById('start-recording');
        const stopBtn = document.getElementById('stop-recording');
        
        if (startBtn) startBtn.disabled = isRecording;
        if (stopBtn) stopBtn.disabled = !isRecording;
    }
    
    /**
     * 处理键盘快捷键
     */
    handleKeyboardShortcuts(e) {
        // 防止在输入框中触发快捷键
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        
        switch(e.key) {
            case '1':
                this.switchTab('preview');
                break;
            case '2':
                this.switchTab('capture');
                break;
            case '3':
                this.switchTab('settings');
                break;
            case '4':
                this.switchTab('presets');
                break;
            case '5':
                this.switchTab('files');
                break;
            case ' ':
                e.preventDefault();
                if (this.cameraStatus.streaming) {
                    this.stopPreview();
                } else {
                    this.startPreview();
                }
                break;
            case 'c':
                if (this.cameraStatus.streaming) {
                    this.captureImage();
                }
                break;
            case 'r':
                if (this.cameraStatus.recording) {
                    this.stopRecording();
                } else if (this.cameraStatus.streaming) {
                    this.startRecording();
                }
                break;
            case 'Escape':
                if (this.cameraStatus.recording) {
                    this.stopRecording();
                }
                break;
        }
    }
    
    /**
     * 显示通知
     */
    showNotification(message, type = 'info') {
        const notifications = document.getElementById('notifications');
        
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        notifications.appendChild(notification);
        
        // 显示动画
        setTimeout(() => {
            notification.classList.add('show');
        }, 100);
        
        // 自动隐藏
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
    
    /**
     * 显示模态框
     */
    showModal(title, content) {
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>${title}</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    ${content}
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // 显示动画
        setTimeout(() => {
            modal.classList.add('show');
        }, 100);
        
        // 关闭事件
        modal.querySelector('.modal-close').addEventListener('click', () => {
            this.closeModal(modal);
        });
        
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeModal(modal);
            }
        });
    }
    
    /**
     * 关闭模态框
     */
    closeModal(modal) {
        modal.classList.remove('show');
        setTimeout(() => {
            if (modal.parentNode) {
                modal.parentNode.removeChild(modal);
            }
        }, 300);
    }
}

// 页面加载完成后初始化调试控制台
document.addEventListener('DOMContentLoaded', () => {
    window.debugConsole = new DebugConsole();
});

// 添加模态框样式
const modalStyles = `
.modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    opacity: 0;
    transition: opacity 0.3s ease;
}

.modal.show {
    opacity: 1;
}

.modal-content {
    background: var(--debug-surface);
    border-radius: var(--debug-radius);
    padding: 24px;
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    transform: scale(0.9);
    transition: transform 0.3s ease;
}

.modal.show .modal-content {
    transform: scale(1);
}

.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--debug-border);
}

.modal-header h3 {
    margin: 0;
    color: var(--debug-text);
    font-size: 1.2rem;
}

.modal-close {
    background: none;
    border: none;
    color: var(--debug-text-secondary);
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    transition: all 0.3s ease;
}

.modal-close:hover {
    background: var(--debug-border);
    color: var(--debug-text);
}

.info-grid {
    display: grid;
    gap: 12px;
}

.touch-feedback {
    transition: transform 0.2s ease;
}

.touch-feedback:active {
    transform: scale(0.95);
}
`;

// 添加样式到页面
const styleSheet = document.createElement('style');
styleSheet.textContent = modalStyles;
document.head.appendChild(styleSheet);
