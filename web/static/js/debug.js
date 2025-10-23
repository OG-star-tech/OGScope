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
            // 忽略过小的时间差（可能由浏览器缓存/事件合并导致的"超高FPS"）
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
            console.log(`[UI] 输出分辨率${width}x${height}与传感器比例差异较大，使用传感器比例: ${targetAspectRatio.toFixed(3)}`);
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
        this.switchTab('capture');
        
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
            
            this.stopRecordingTimer();
            this.updateRecordingButtons(false);
            this.setRecOverlay(false);
            
            await this.updateCameraStatus();
            this.showNotification('录制已停止', 'info');
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
        this.recordingInterval = setInterval(() => {
            if (this.recordingStartTime) {
                const duration = Date.now() - this.recordingStartTime;
                this.updateRecordingDuration(duration);
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
    }
    
    /**
     * 更新录制时长
     */
    updateRecordingDuration(duration) {
        const durationElement = document.getElementById('recording-duration');
        if (durationElement) {
            const seconds = Math.floor(duration / 1000);
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            durationElement.textContent = `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
        }
        
        // 更新录制徽章
        const recBadgeTime = document.getElementById('rec-badge-time');
        if (recBadgeTime) {
            const seconds = Math.floor(duration / 1000);
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            recBadgeTime.textContent = `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
        }
    }
    
    /**
     * 设置录制覆盖层
     */
    setRecOverlay(recording) {
        const recBadge = document.getElementById('rec-badge');
        if (recBadge) {
            recBadge.style.display = recording ? 'flex' : 'none';
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
     * 更新按钮状态
     */
    updateButtonStates() {
        const startBtn = document.getElementById('start-preview');
        const stopBtn = document.getElementById('stop-preview');
        
        if (startBtn) {
            startBtn.disabled = this.cameraStatus.streaming;
        }
        
        if (stopBtn) {
            stopBtn.disabled = !this.cameraStatus.streaming;
        }
    }
    
    /**
     * 开始状态轮询
     */
    beginStatusPolling() {
        this.endStatusPolling();
        this.statusInterval = setInterval(() => {
            this.updateCameraStatus();
        }, 2000);
    }
    
    /**
     * 结束状态轮询
     */
    endStatusPolling() {
        if (this.statusInterval) {
            clearInterval(this.statusInterval);
            this.statusInterval = null;
        }
    }
    
    /**
     * 更新曝光显示
     */
    updateExposureDisplay(value) {
        document.getElementById('exposure-value').textContent = value;
    }
    
    /**
     * 更新增益显示
     */
    updateGainDisplay(value) {
        document.getElementById('gain-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新数字增益显示
     */
    updateDigitalGainDisplay(value) {
        document.getElementById('digital-gain-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新对比度显示
     */
    updateContrastDisplay(value) {
        document.getElementById('contrast-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新亮度显示
     */
    updateBrightnessDisplay(value) {
        document.getElementById('brightness-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新饱和度显示
     */
    updateSaturationDisplay(value) {
        document.getElementById('saturation-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新锐度显示
     */
    updateSharpnessDisplay(value) {
        document.getElementById('sharpness-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新降噪显示
     */
    updateNoiseReductionDisplay(value) {
        document.getElementById('noise-reduction-value').textContent = value;
    }
    
    /**
     * 更新白平衡模式
     */
    updateWhiteBalanceMode(mode) {
        const gainsContainer = document.getElementById('white-balance-gains');
        if (gainsContainer) {
            gainsContainer.style.display = mode === 'manual' ? 'block' : 'none';
        }
    }
    
    /**
     * 更新白平衡红色增益显示
     */
    updateWhiteBalanceGainR(value) {
        document.getElementById('wb-gain-r-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新白平衡蓝色增益显示
     */
    updateWhiteBalanceGainB(value) {
        document.getElementById('wb-gain-b-value').textContent = value.toFixed(1);
    }
    
    /**
     * 应用设置
     */
    async applySettings() {
        const settings = {
            exposure: parseInt(document.getElementById('exposure-setting').value),
            gain: parseFloat(document.getElementById('gain-setting').value),
            digitalGain: parseFloat(document.getElementById('digital-gain-setting').value),
            contrast: parseFloat(document.getElementById('contrast-setting').value),
            brightness: parseFloat(document.getElementById('brightness-setting').value),
            saturation: parseFloat(document.getElementById('saturation-setting').value),
            sharpness: parseFloat(document.getElementById('sharpness-setting').value),
            noiseReduction: parseInt(document.getElementById('noise-reduction-setting').value),
            whiteBalanceMode: document.getElementById('white-balance-mode').value,
            whiteBalanceGainR: parseFloat(document.getElementById('wb-gain-r').value),
            whiteBalanceGainB: parseFloat(document.getElementById('wb-gain-b').value)
        };

        try {
            const response = await fetch('/api/debug/camera/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });

            if (response.ok) {
                this.showNotification('设置应用成功', 'success');
                await this.updateCameraStatus();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '设置应用失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 应用设置失败:', error);
            this.showNotification(`设置应用失败: ${error.message}`, 'error');
        }
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
                await this.updateCameraStatus();
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
            const response = await fetch(`/api/debug/camera/night-mode?enabled=${enabled}`, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.currentSettings.nightMode = enabled;
                const statusElement = document.getElementById('night-mode-status');
                if (statusElement) {
                    statusElement.textContent = enabled ? '开启' : '关闭';
                }
                this.showNotification(`夜间模式已${enabled ? '开启' : '关闭'}`, 'success');
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
                this.showNotification('当前设置已备份', 'success');
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
        try {
            const response = await fetch('/api/debug/camera/restore-settings', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification('设置已从备份恢复', 'success');
                await this.updateCameraStatus();
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
     * 仅应用尺寸（宽高），不影响帧率
     */
    async applySizeOnly(width, height) {
        try {
            const resp = await fetch(`/api/debug/camera/size?width=${width}&height=${height}`, { method: 'POST' });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || '设置分辨率失败');
            }
            this.showNotification(`分辨率已设置为 ${width}x${height}`, 'success');
            await this.updateCameraStatus();
        } catch (e) {
            console.error(e);
            this.showNotification(`设置分辨率失败: ${e.message}`, 'error');
        }
    }
    
    /**
     * 启动图像质量监控
     */
    startQualityMonitoring() {
        this.stopQualityMonitoring();
        
        this.qualityMonitoringInterval = setInterval(async () => {
            try {
                const response = await fetch('/api/debug/camera/image-quality');
                if (response.ok) {
                    const data = await response.json();
                    this.updateQualityMetrics(data.quality);
                }
            } catch (error) {
                console.error('[QualityMonitoring] 获取图像质量失败:', error);
            }
        }, 3000); // 每3秒更新一次
        
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
     * 更新图像质量指标
     */
    updateQualityMetrics(quality) {
        // 更新噪点水平
        const noiseLevel = quality.noise_level || 0;
        const noiseBar = document.getElementById('noise-level-bar');
        const noiseValue = document.getElementById('noise-level');
        if (noiseBar && noiseValue) {
            noiseBar.style.width = `${Math.min(100, noiseLevel * 10)}%`;
            noiseValue.textContent = `${noiseLevel.toFixed(1)}`;
        }
        
        // 更新曝光充足度
        const exposureLevel = quality.exposure_level || 0;
        const exposureBar = document.getElementById('exposure-bar');
        const exposureValue = document.getElementById('exposure-level');
        if (exposureBar && exposureValue) {
            exposureBar.style.width = `${Math.min(100, exposureLevel * 10)}%`;
            exposureValue.textContent = `${exposureLevel.toFixed(1)}`;
        }
        
        // 更新增益水平
        const gainLevel = quality.gain_level || 0;
        const gainBar = document.getElementById('gain-bar');
        const gainValue = document.getElementById('gain-level');
        if (gainBar && gainValue) {
            gainBar.style.width = `${Math.min(100, gainLevel * 10)}%`;
            gainValue.textContent = `${gainLevel.toFixed(1)}`;
        }
        
        // 更新建议
        this.updateQualityRecommendations(quality);
    }
    
    /**
     * 更新质量建议
     */
    updateQualityRecommendations(quality) {
        const recommendationsContainer = document.getElementById('quality-recommendations');
        if (!recommendationsContainer) return;
        
        const recommendations = [];
        
        if (quality.noise_level > 7) {
            recommendations.push('建议降低增益以减少噪点');
        }
        
        if (quality.exposure_level < 3) {
            recommendations.push('建议增加曝光时间');
        } else if (quality.exposure_level > 8) {
            recommendations.push('建议减少曝光时间');
        }
        
        if (quality.gain_level > 8) {
            recommendations.push('建议降低增益设置');
        }
        
        if (recommendations.length === 0) {
            recommendations.push('图像质量良好');
        }
        
        recommendationsContainer.innerHTML = recommendations.map(rec => 
            `<div class="quality-recommendation">${rec}</div>`
        ).join('');
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
     * 处理键盘快捷键
     */
    handleKeyboardShortcuts(e) {
        // 防止在输入框中触发快捷键
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        
        switch(e.key) {
            case '1':
                this.switchTab('capture');
                break;
            case '2':
                this.switchTab('settings');
                break;
            case '3':
                this.switchTab('presets');
                break;
            case '4':
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