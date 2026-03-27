/**
 * OGScope 调试控制台 JavaScript / OGScope debug console JavaScript
 * 提供相机调试、拍摄控制、参数设置等功能 / Provides camera debugging, shooting control, parameter setting and other functions
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
            autoExposure: true,
            rotation: 180,
            // 新增参数 / New parameters
            contrast: 1.0,
            brightness: 0.0,
            saturation: 1.0,
            sharpness: 1.0,
            noiseReduction: 0,
            whiteBalanceMode: 'auto',
            whiteBalanceGainR: 1.0,
            whiteBalanceGainB: 1.0,
            nightMode: false,
            colorMode: 'color'  // 颜色模式：color | mono
        };
        
        this.presets = [];
        this.files = [];
        this.recordingStartTime = null;
        this.recordingInterval = null;
        this.statusInterval = null;
        this.systemInfoInterval = null;
        this.previewObjectUrl = null;
        this.systemInfo = null;
        
        // 智能头部隐藏 / Intelligent head hiding
        this.lastScrollY = 0;
        this.scrollDirection = 'down';
        this.headerHidden = false;
        this.scrollThreshold = 10; // 滚动阈值 / scroll threshold
        
        // 实时数据流分析 / Real-time data flow analysis
        this.streamStats = {
            requestCount: 0,
            frameCount: 0, // 有效新帧计数（基于 X-Frame-Id） / Valid new frame count (based on X-Frame-Id)
            lastRequestTime: null,
            lastFrameTime: null,
            requestFps: 0.0,
            fpsCalculated: 0.0, // 有效新帧 FPS / Effective new frame FPS
            resolutionDetected: null,
            dataSize: 0,
            avgFrameSize: 0,
            requestTimes: [],
            frameTimes: [],
            lastFrameId: null,
            lastFrameServerTs: null,
            startTime: null
        };

        // 直方图（纯前端计算） / Histogram (pure front-end calculation)
        this.histogramState = {
            enabled: true,
            overlayVisible: false,
            panelVisible: false,
            showRgb: true,
            showLuminance: false,
            showOverexposure: false,
        };
        this.histogramCanvasCtx = null;
        this.histogramOffscreenCanvas = null;
        this.histogramOffscreenCtx = null;

        this.supportedLocales = ['zh', 'en', 'bilingual'];
        this.locale = localStorage.getItem('debugConsole.language') || 'zh';
        if (!this.supportedLocales.includes(this.locale)) {
            this.locale = 'zh';
        }
        this.translations = { zh: {}, en: {} };
        this.dynamicTextPatterns = this.buildDynamicTextPatterns();
        this.rawTextToKeyMap = this.buildRawTextToKeyMap();
        
        this.init();
    }

    buildRawTextToKeyMap() {
        return {
            '请先在设置中启用直方图': 'notify.enableHistogramFirst',
            '请选择分辨率预设': 'notify.selectResolutionPreset',
            '请输入有效的帧率': 'notify.invalidFps',
            '正在设置帧率...': 'notify.settingFps',
            '帧率已应用': 'notify.fpsApplied',
            '正在切换采样模式...': 'notify.settingSampling',
            '采样模式已切换': 'notify.samplingApplied',
            '获取相机状态失败': 'notify.fetchCameraStatusFailed',
            '正在启动相机预览...': 'notify.startingPreview',
            '相机预览已启动': 'notify.previewStarted',
            '相机预览已停止': 'notify.previewStopped',
            '停止预览失败': 'notify.stopPreviewFailed',
            '请先启动相机预览': 'notify.startPreviewRequired',
            '设置应用成功': 'notify.settingsApplied',
            '相机已重置到默认设置': 'notify.resetSettingsDone',
            '夜间模式预设已应用': 'notify.nightPresetApplied',
            '当前设置已备份': 'notify.settingsBackedUp',
            '设置已从备份恢复': 'notify.settingsRestored',
            '加载预设失败': 'notify.loadPresetsFailed',
            '请输入预设名称': 'notify.inputPresetName',
            '预设保存成功': 'notify.presetSaved',
            '加载文件列表失败': 'notify.loadFilesFailed',
            '获取文件信息失败': 'notify.fileInfoFailed',
            '未知的预设类型': 'notify.unknownPresetType',
            '自动曝光模式下无需智能调整，请先切换为手动曝光': 'notify.autoExposureNoAdjust',
            '正在分析图像质量...': 'notify.analyzingImageQuality',
            '当前参数已经很好，无需调整': 'notify.parametersAlreadyGood',
            '相机启动成功': 'server.cameraStarted',
            '相机未运行': 'server.cameraNotRunning',
            '相机停止成功': 'server.cameraStopped',
            '录制已停止': 'server.recordingStopped',
            '分辨率未变化': 'server.resolutionUnchanged',
            '分辨率已更新': 'server.resolutionUpdated',
            '相机设置已更新': 'server.cameraSettingsUpdated',
            '图像增强参数已设置': 'server.imageEnhancementSet'
        };
    }

    buildDynamicTextPatterns() {
        return [
            { regex: /^设置旋转失败:\s*(.+)$/u, key: 'notify.rotateFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^启动预览失败:\s*(.+)$/u, key: 'notify.startPreviewFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^设置帧率失败:\s*(.+)$/u, key: 'notify.setFpsFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^设置采样模式失败:\s*(.+)$/u, key: 'notify.setSamplingFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^拍摄失败:\s*(.+)$/u, key: 'notify.captureFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^开始录制:\s*(.+)$/u, key: 'notify.recordingStarted', map: (m) => ({ filename: m[1] }) },
            { regex: /^开始录制失败:\s*(.+)$/u, key: 'notify.recordingStartFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^设置应用失败:\s*(.+)$/u, key: 'notify.applySettingsFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^正在切换到(黑白|彩色)模式\.\.\.$/u, key: 'notify.switchingColorMode', map: (m) => ({ mode: m[1] }) },
            { regex: /^颜色模式切换失败:\s*(.+)$/u, key: 'notify.colorModeSwitchFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^重置设置失败:\s*(.+)$/u, key: 'notify.resetSettingsFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^应用夜间模式预设失败:\s*(.+)$/u, key: 'notify.applyNightPresetFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^夜间模式已(开启|关闭)$/u, key: 'notify.nightModeToggled', map: (m) => ({ state: m[1] }) },
            { regex: /^切换夜间模式失败:\s*(.+)$/u, key: 'notify.toggleNightModeFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^备份设置失败:\s*(.+)$/u, key: 'notify.backupSettingsFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^恢复设置失败:\s*(.+)$/u, key: 'notify.restoreSettingsFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^分辨率已设置为\s*(\d+)x(\d+)$/u, key: 'notify.resolutionSet', map: (m) => ({ width: m[1], height: m[2] }) },
            { regex: /^设置分辨率失败:\s*(.+)$/u, key: 'notify.setResolutionFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^保存预设失败:\s*(.+)$/u, key: 'notify.savePresetFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^预设\s*'(.+)'\s*已应用$/u, key: 'notify.presetApplied', map: (m) => ({ name: m[1] }) },
            { regex: /^应用预设失败:\s*(.+)$/u, key: 'notify.applyPresetFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^预设\s*'(.+)'\s*已删除$/u, key: 'notify.presetDeleted', map: (m) => ({ name: m[1] }) },
            { regex: /^删除预设失败:\s*(.+)$/u, key: 'notify.deletePresetFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^开始下载:\s*(.+)$/u, key: 'notify.downloadStarted', map: (m) => ({ filename: m[1] }) },
            { regex: /^文件\s+(.+)\s+删除成功$/u, key: 'notify.fileDeleted', map: (m) => ({ filename: m[1] }) },
            { regex: /^删除文件失败:\s*(.+)$/u, key: 'notify.deleteFileFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^智能调整完成:\s*(.+)$/u, key: 'notify.smartAdjustDone', map: (m) => ({ suggestions: m[1] }) },
            { regex: /^智能调整失败:\s*(.+)$/u, key: 'notify.smartAdjustFailed', map: (m) => ({ error: m[1] }) },
            { regex: /^照片已保存:\s*(.+)$/u, key: 'notify.captureSaved', map: (m) => ({ filename: m[1] }) },
            { regex: /^采样模式已设置为\s*(.+)$/u, key: 'server.samplingModeSet', map: (m) => ({ mode: m[1] }) },
            { regex: /^帧率设置为\s*(\d+)$/u, key: 'server.fpsSet', map: (m) => ({ fps: m[1] }) },
            { regex: /^降噪级别设置为:\s*(\d+)$/u, key: 'server.noiseReductionSet', map: (m) => ({ level: m[1] }) },
            { regex: /^白平衡模式设置为:\s*(.+)$/u, key: 'server.whiteBalanceSet', map: (m) => ({ mode: m[1] }) },
            { regex: /^颜色模式已切换为(.+)模式$/u, key: 'server.colorModeSwitched', map: (m) => ({ mode: m[1] }) },
            { regex: /^旋转角度设置为:\s*(\d+)度$/u, key: 'server.rotationSet', map: (m) => ({ rotation: m[1] }) }
        ];
    }

    async initI18n() {
        try {
            const [zhRes, enRes] = await Promise.all([
                fetch('/static/i18n/debug.zh.json', { cache: 'no-store' }),
                fetch('/static/i18n/debug.en.json', { cache: 'no-store' })
            ]);
            this.translations.zh = zhRes.ok ? await zhRes.json() : {};
            this.translations.en = enRes.ok ? await enRes.json() : {};
        } catch (error) {
            console.warn('[I18N] load failed, fallback to raw text:', error);
            this.translations = { zh: {}, en: {} };
        }
    }

    interpolate(template, params = {}) {
        if (typeof template !== 'string') return template;
        return template.replace(/\{(\w+)\}/g, (_, key) => (params[key] ?? `{${key}}`));
    }

    t(key, params = {}, forcedLocale = null) {
        const locale = forcedLocale || this.locale;
        const zhText = this.interpolate(this.translations.zh[key] || key, params);
        const enText = this.interpolate(this.translations.en[key] || zhText, params);
        if (locale === 'en') return enText;
        if (locale === 'bilingual') return zhText === enText ? zhText : `${zhText} / ${enText}`;
        return zhText;
    }

    localizeText(rawText) {
        if (!rawText || typeof rawText !== 'string') return rawText;
        const key = this.rawTextToKeyMap[rawText];
        if (key) return this.t(key);
        for (const item of this.dynamicTextPatterns) {
            const match = rawText.match(item.regex);
            if (match) {
                return this.t(item.key, item.map(match));
            }
        }
        return rawText;
    }

    applyI18nToPage() {
        document.documentElement.lang = this.locale === 'en' ? 'en' : 'zh-CN';
        document.querySelectorAll('[data-i18n]').forEach((el) => {
            const key = el.getAttribute('data-i18n');
            if (key) el.textContent = this.t(key);
        });
        document.querySelectorAll('[data-i18n-title]').forEach((el) => {
            const key = el.getAttribute('data-i18n-title');
            if (key) el.title = this.t(key);
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
            const key = el.getAttribute('data-i18n-placeholder');
            if (key) el.placeholder = this.t(key);
        });
        document.querySelectorAll('[data-i18n-alt]').forEach((el) => {
            const key = el.getAttribute('data-i18n-alt');
            if (key) el.alt = this.t(key);
        });
        const languageSelect = document.getElementById('language-select');
        if (languageSelect) languageSelect.value = this.locale;
    }

    setLanguage(locale) {
        if (!this.supportedLocales.includes(locale)) return;
        this.locale = locale;
        localStorage.setItem('debugConsole.language', locale);
        this.applyI18nToPage();
        this.updateStatusUI();
        this.updateColorMode(this.currentSettings.colorMode || 'color');
        this.renderPresets();
        this.renderFiles();
        this.updateSystemInfoUI();
    }

    extractApiMessage(payload, fallbackKey = 'notify.colorModeSwitched') {
        if (!payload || typeof payload !== 'object') return this.t(fallbackKey);
        if (payload.message_key) return this.t(payload.message_key, payload.message_params || {});
        if (payload.message) return this.localizeText(payload.message);
        return this.t(fallbackKey);
    }
    
    /**
     * 分析实时数据流 / Analyze real-time data streams
     */
    analyzeStreamData(imageElement, frameMeta = {}) {
        const currentTime = performance.now();
        
        // 记录开始时间 / Recording start time
        if (this.streamStats.startTime === null) {
            this.streamStats.startTime = currentTime;
        }
        
        // 每次请求都计数（请求吞吐） / Each request is counted (request throughput)
        this.streamStats.requestCount++;

        // 计算请求 FPS / Calculate request FPS
        if (this.streamStats.lastRequestTime !== null) {
            const requestDiff = currentTime - this.streamStats.lastRequestTime;
            if (requestDiff > 10) {
                const requestFps = 1000 / requestDiff;
                this.streamStats.requestTimes.push(requestFps);
                if (this.streamStats.requestTimes.length > 10) {
                    this.streamStats.requestTimes.shift();
                }
                this.streamStats.requestFps =
                    this.streamStats.requestTimes.reduce((a, b) => a + b, 0) /
                    this.streamStats.requestTimes.length;
            }
        }
        this.streamStats.lastRequestTime = currentTime;
        
        // 检测分辨率并调整容器宽高比 / Detect resolution and adjust container aspect ratio
        if (imageElement && imageElement.naturalWidth && imageElement.naturalHeight) {
            const detectedRes = `${imageElement.naturalWidth}x${imageElement.naturalHeight}`;
            if (this.streamStats.resolutionDetected !== detectedRes) {
                this.streamStats.resolutionDetected = detectedRes;
                console.log(`[Stream] 检测到分辨率: ${detectedRes}`);
                this.updateVideoContainerAspectRatio(imageElement.naturalWidth, imageElement.naturalHeight);
            }
        }
        
        const hasFrameId = frameMeta.frameId !== null && frameMeta.frameId !== undefined;
        const isNewFrame = hasFrameId
            ? frameMeta.frameId !== this.streamStats.lastFrameId
            : true;

        // 仅在检测到新帧时更新“有效新帧 FPS” / Only update "Valid New Frame FPS" when a new frame is detected
        if (isNewFrame) {
            this.streamStats.frameCount++;

            if (this.streamStats.lastFrameTime !== null) {
                const timeDiff = currentTime - this.streamStats.lastFrameTime;
                if (timeDiff > 10) {
                    let fps = 1000 / timeDiff;
                    const reported = (this.cameraStatus?.info?.fps) || 5;
                    const fpsCap = Math.max(10, reported * 2);
                    if (fps > fpsCap) fps = fpsCap;
                    this.streamStats.frameTimes.push(fps);

                    if (this.streamStats.frameTimes.length > 10) {
                        this.streamStats.frameTimes.shift();
                    }

                    const avgFps = this.streamStats.frameTimes.reduce((a, b) => a + b, 0) / this.streamStats.frameTimes.length;
                    this.streamStats.fpsCalculated = avgFps;
                }
            }

            this.streamStats.lastFrameTime = currentTime;
            if (hasFrameId) {
                this.streamStats.lastFrameId = frameMeta.frameId;
            }
            if (typeof frameMeta.frameTs === 'number' && Number.isFinite(frameMeta.frameTs)) {
                this.streamStats.lastFrameServerTs = frameMeta.frameTs;
            }
        }

        // 统计接收数据量（按请求流量） / Statistics of received data volume (according to request traffic)
        if (typeof frameMeta.sizeBytes === 'number' && Number.isFinite(frameMeta.sizeBytes)) {
            this.streamStats.dataSize += frameMeta.sizeBytes;
            if (this.streamStats.requestCount > 0) {
                this.streamStats.avgFrameSize = this.streamStats.dataSize / this.streamStats.requestCount;
            }
        }
        
        // 更新UI显示 / Update UI display
        this.updateStreamStatsDisplay();
    }
    
    /**
     * 根据相机分辨率动态调整视频容器的宽高比 / Dynamically adjust the video container's aspect ratio based on camera resolution
     * 考虑传感器原生宽高比，避免画面被压缩 / Consider the sensor's native aspect ratio to avoid image compression
     */
    updateVideoContainerAspectRatio(width, height) {
        const videoContainer = document.querySelector('.video-container');
        if (!videoContainer) return;
        
        // 固定使用16:9比例，避免画面变形 / Fixed use of 16:9 ratio to avoid image distortion
        const targetAspectRatio = 16 / 9; // 1.778
        
        // 设置CSS自定义属性 / Set CSS custom properties
        videoContainer.style.aspectRatio = `${targetAspectRatio}`;
        
        console.log(`[UI] 固定使用16:9比例显示视频 (${width}x${height})`);
        
        // 添加视觉反馈 / Add visual feedback
        videoContainer.classList.add('aspect-ratio-changing');
        setTimeout(() => {
            videoContainer.classList.remove('aspect-ratio-changing');
        }, 300);
    }
    
    /**
     * 初始化智能头部隐藏功能 / Initialize the intelligent head hiding function
     */
    initSmartHeader() {
        const header = document.querySelector('.debug-header');
        if (!header) return;
        
        let ticking = false;
        
        const handleScroll = () => {
            if (!ticking) {
                requestAnimationFrame(() => {
                    this.handleHeaderScroll();
                    ticking = false;
                });
                ticking = true;
            }
        };
        
        // 监听滚动事件 / Listen for scroll events
        window.addEventListener('scroll', handleScroll, { passive: true });
        
        // 监听触摸滚动（移动端） / Monitor touch scrolling (mobile)
        let touchStartY = 0;
        let touchEndY = 0;
        
        document.addEventListener('touchstart', (e) => {
            touchStartY = e.touches[0].clientY;
        }, { passive: true });
        
        document.addEventListener('touchmove', (e) => {
            touchEndY = e.touches[0].clientY;
            const deltaY = touchStartY - touchEndY;
            
            // 模拟滚动方向检测 / Simulate scroll direction detection
            if (Math.abs(deltaY) > 10) {
                this.scrollDirection = deltaY > 0 ? 'up' : 'down';
                this.handleHeaderVisibility();
                touchStartY = touchEndY;
            }
        }, { passive: true });
        
        // 唤醒区域事件监听 / Wake up area event monitoring
        const revealZone = document.getElementById('header-reveal-zone');
        if (revealZone) {
            revealZone.addEventListener('click', () => {
                this.forceShowHeader();
            });
            
            revealZone.addEventListener('touchend', (e) => {
                e.preventDefault();
                this.forceShowHeader();
            });
        }
        
        console.log('[SmartHeader] 智能头部隐藏已初始化');
    }
    
    /**
     * 处理头部滚动 / Handling head scrolling
     */
    handleHeaderScroll() {
        const currentScrollY = window.scrollY;
        
        // 检测滚动方向 / Detect scroll direction
        if (currentScrollY > this.lastScrollY && currentScrollY > this.scrollThreshold) {
            // 向下滚动，隐藏头部 / Scroll down to hide header
            this.scrollDirection = 'down';
        } else if (currentScrollY < this.lastScrollY) {
            // 向上滚动，显示头部 / Scroll up to show header
            this.scrollDirection = 'up';
        }
        
        this.lastScrollY = currentScrollY;
        this.handleHeaderVisibility();
    }
    
    /**
     * 处理头部可见性 / Handling header visibility
     */
    handleHeaderVisibility() {
        const header = document.querySelector('.debug-header');
        const revealZone = document.getElementById('header-reveal-zone');
        if (!header) return;
        
        const shouldHide = this.scrollDirection === 'down' && this.lastScrollY > this.scrollThreshold;
        
        if (shouldHide && !this.headerHidden) {
            // 隐藏头部 / Hide header
            header.classList.add('hidden');
            this.headerHidden = true;
            
            // 显示唤醒区域 / Show wake area
            if (revealZone) {
                revealZone.classList.add('active');
            }
            
            console.log('[SmartHeader] 头部已隐藏');
        } else if (!shouldHide && this.headerHidden) {
            // 显示头部 / Show header
            header.classList.remove('hidden');
            this.headerHidden = false;
            
            // 隐藏唤醒区域 / Hide wake area
            if (revealZone) {
                revealZone.classList.remove('active');
            }
            
            console.log('[SmartHeader] 头部已显示');
        }
    }
    
    /**
     * 强制显示头部（用于某些交互场景） / Force display of head (used in certain interactive scenarios)
     */
    forceShowHeader() {
        const header = document.querySelector('.debug-header');
        const revealZone = document.getElementById('header-reveal-zone');
        
        if (header && this.headerHidden) {
            header.classList.remove('hidden');
            this.headerHidden = false;
            
            // 隐藏唤醒区域 / Hide wake area
            if (revealZone) {
                revealZone.classList.remove('active');
            }
            
            console.log('[SmartHeader] 强制显示头部');
        }
    }
    
    /**
     * 初始化全屏预览功能 / Initialize full screen preview function
     */
    initFullscreenPreview() {
        const fullscreenToggle = document.getElementById('fullscreen-toggle');
        const fullscreenPreview = document.getElementById('fullscreen-preview');
        const fullscreenImage = document.getElementById('fullscreen-image');
        const fullscreenClose = document.getElementById('fullscreen-close');
        const previewImage = document.getElementById('preview-image');
        
        if (!fullscreenToggle || !fullscreenPreview || !fullscreenImage) return;
        
        // 打开全屏预览 / Open full screen preview
        fullscreenToggle.addEventListener('click', () => {
            if (previewImage && previewImage.src) {
                fullscreenImage.src = previewImage.src;
                fullscreenPreview.classList.add('active');
                document.body.style.overflow = 'hidden';
                console.log('[Debug] 全屏预览已打开');
            } else {
                console.warn('[Debug] 没有可预览的图像');
            }
        });
        
        // 关闭全屏预览 / Turn off full screen preview
        if (fullscreenClose) {
            fullscreenClose.addEventListener('click', () => {
                fullscreenPreview.classList.remove('active');
                document.body.style.overflow = '';
                console.log('[Debug] 全屏预览已关闭');
            });
        }
        
        // 点击背景关闭全屏 / Click on the background to close full screen
        fullscreenPreview.addEventListener('click', (e) => {
            if (e.target === fullscreenPreview) {
                fullscreenPreview.classList.remove('active');
                document.body.style.overflow = '';
                console.log('[Debug] 全屏预览已关闭');
            }
        });
        
        // ESC键关闭全屏 / ESC key to close full screen
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && fullscreenPreview.classList.contains('active')) {
                fullscreenPreview.classList.remove('active');
                document.body.style.overflow = '';
                console.log('[Debug] 全屏预览已关闭 (ESC键)');
            }
        });
    }

    /**
     * 应用直方图可见性与按钮状态 / Apply histogram visibility and button states
     */
    applyHistogramVisibility() {
        const overlay = document.getElementById('histogram-overlay');
        const panel = document.getElementById('histogram-panel');
        const toggleBtn = document.getElementById('histogram-toggle');
        const settingsBtn = document.getElementById('histogram-settings');
        const infoEl = document.getElementById('histogram-info');

        if (overlay) {
            overlay.classList.toggle(
                'visible',
                this.histogramState.enabled && this.histogramState.overlayVisible,
            );
        }
        if (panel) {
            panel.classList.toggle('visible', this.histogramState.panelVisible);
        }
        if (toggleBtn) {
            toggleBtn.classList.toggle(
                'active',
                this.histogramState.enabled && this.histogramState.overlayVisible,
            );
        }
        if (settingsBtn) {
            settingsBtn.classList.toggle('active', this.histogramState.panelVisible);
        }
        if (infoEl) {
            const channels = [];
            if (this.histogramState.showRgb) channels.push('RGB');
            if (this.histogramState.showLuminance) channels.push(this.t('histogram.luminanceShort'));
            if (channels.length === 0) channels.push(this.t('histogram.noChannelSelected'));
            infoEl.innerHTML = `<div>${channels.join(' + ')} ${this.t('histogram.name')}</div><div>${this.t('histogram.frontendOnly')}</div>`;
        }
    }

    /**
     * 绘制直方图（纯前端像素计算） / Draw a histogram (pure front-end pixel calculation)
     */
    updateHistogramFromImage(imageElement) {
        if (!this.histogramState.enabled || !imageElement?.naturalWidth || !imageElement?.naturalHeight) {
            return;
        }

        const histogramCanvas = document.getElementById('histogram-canvas');
        if (!histogramCanvas) return;

        if (!this.histogramCanvasCtx) {
            this.histogramCanvasCtx = histogramCanvas.getContext('2d');
        }
        if (!this.histogramCanvasCtx) return;

        // 使用离屏 canvas 采样，降低主线程压力 / Use off-screen canvas sampling to reduce main thread pressure
        if (!this.histogramOffscreenCanvas) {
            this.histogramOffscreenCanvas = document.createElement('canvas');
            this.histogramOffscreenCtx = this.histogramOffscreenCanvas.getContext('2d', { willReadFrequently: true });
        }
        if (!this.histogramOffscreenCtx) return;

        const maxSampleWidth = 320;
        const scale = Math.min(1, maxSampleWidth / imageElement.naturalWidth);
        const sampleWidth = Math.max(1, Math.round(imageElement.naturalWidth * scale));
        const sampleHeight = Math.max(1, Math.round(imageElement.naturalHeight * scale));
        this.histogramOffscreenCanvas.width = sampleWidth;
        this.histogramOffscreenCanvas.height = sampleHeight;
        this.histogramOffscreenCtx.drawImage(imageElement, 0, 0, sampleWidth, sampleHeight);

        const imageData = this.histogramOffscreenCtx.getImageData(0, 0, sampleWidth, sampleHeight).data;

        const histR = new Array(256).fill(0);
        const histG = new Array(256).fill(0);
        const histB = new Array(256).fill(0);
        const histLum = new Array(256).fill(0);

        let luminanceSum = 0;
        let luminanceSquareSum = 0;
        let overexposedPixels = 0;
        const pixelsCount = sampleWidth * sampleHeight;

        for (let i = 0; i < imageData.length; i += 4) {
            const r = imageData[i];
            const g = imageData[i + 1];
            const b = imageData[i + 2];
            const lum = Math.round(0.2126 * r + 0.7152 * g + 0.0722 * b);

            histR[r] += 1;
            histG[g] += 1;
            histB[b] += 1;
            histLum[lum] += 1;

            luminanceSum += lum;
            luminanceSquareSum += lum * lum;

            if (lum >= 250) {
                overexposedPixels += 1;
            }
        }

        const mean = pixelsCount > 0 ? luminanceSum / pixelsCount : 0;
        const variance = pixelsCount > 0 ? (luminanceSquareSum / pixelsCount) - (mean * mean) : 0;
        const std = Math.sqrt(Math.max(0, variance));
        const overexposedRatio = pixelsCount > 0 ? (overexposedPixels / pixelsCount) * 100 : 0;

        this.drawHistogramCanvas(histogramCanvas, this.histogramCanvasCtx, {
            histR,
            histG,
            histB,
            histLum,
        });
        this.updateHistogramStats(mean, std, overexposedRatio);
    }

    drawHistogramCanvas(canvas, ctx, histData) {
        const dpr = window.devicePixelRatio || 1;
        const targetWidth = Math.max(1, canvas.clientWidth || 200);
        const targetHeight = Math.max(1, canvas.clientHeight || 100);
        canvas.width = Math.floor(targetWidth * dpr);
        canvas.height = Math.floor(targetHeight * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, targetWidth, targetHeight);

        const { histR, histG, histB, histLum } = histData;
        const peak = Math.max(
            1,
            ...(this.histogramState.showRgb ? [Math.max(...histR), Math.max(...histG), Math.max(...histB)] : [0]),
            ...(this.histogramState.showLuminance ? [Math.max(...histLum)] : [0]),
        );

        const drawLine = (hist, color) => {
            ctx.beginPath();
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.2;
            for (let i = 0; i < 256; i += 1) {
                const x = (i / 255) * targetWidth;
                const y = targetHeight - (hist[i] / peak) * targetHeight;
                if (i === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            }
            ctx.stroke();
        };

        if (this.histogramState.showRgb) {
            drawLine(histR, 'rgba(255, 80, 80, 0.85)');
            drawLine(histG, 'rgba(80, 255, 80, 0.85)');
            drawLine(histB, 'rgba(80, 160, 255, 0.85)');
        }
        if (this.histogramState.showLuminance) {
            drawLine(histLum, 'rgba(255, 255, 255, 0.95)');
        }

        if (this.histogramState.showOverexposure) {
            const warningX = (250 / 255) * targetWidth;
            ctx.fillStyle = 'rgba(255, 100, 100, 0.12)';
            ctx.fillRect(warningX, 0, targetWidth - warningX, targetHeight);
        }
    }

    updateHistogramStats(mean, std, overexposedRatio) {
        const meanEl = document.getElementById('histogram-mean');
        const stdEl = document.getElementById('histogram-std');
        const overEl = document.getElementById('histogram-overexposed');

        if (meanEl) meanEl.textContent = mean.toFixed(1);
        if (stdEl) stdEl.textContent = std.toFixed(1);
        if (overEl) overEl.textContent = `${overexposedRatio.toFixed(2)}%`;
    }

    clearHistogramCanvas() {
        const canvas = document.getElementById('histogram-canvas');
        if (canvas && this.histogramCanvasCtx) {
            this.histogramCanvasCtx.clearRect(0, 0, canvas.width, canvas.height);
        }
        this.updateHistogramStats(0, 0, 0);
    }
    
    /**
     * 更新数据流统计显示 / Update data flow statistics display
     */
    updateStreamStatsDisplay() {
        // 更新分辨率显示 / Update resolution display
        if (this.streamStats.resolutionDetected) {
            const resolutionElement = document.getElementById('detected-resolution');
            if (resolutionElement) {
                resolutionElement.textContent = this.streamStats.resolutionDetected;
            }
        }
        
        // 更新FPS显示 / Update FPS display
        const effectiveFpsElement = document.getElementById('calculated-fps');
        if (effectiveFpsElement) {
            effectiveFpsElement.textContent = this.streamStats.fpsCalculated.toFixed(2);
        }

        const requestFpsElement = document.getElementById('request-fps');
        if (requestFpsElement) {
            requestFpsElement.textContent = this.streamStats.requestFps.toFixed(2);
        }
        
        // 更新帧计数显示 / Update frame count display
        const frameCountElement = document.getElementById('frame-count');
        if (frameCountElement) {
            frameCountElement.textContent = this.streamStats.frameCount;
        }

        const requestCountElement = document.getElementById('request-count');
        if (requestCountElement) {
            requestCountElement.textContent = this.streamStats.requestCount;
        }
        
        // 更新数据大小显示 / Update data size display
        const dataSizeElement = document.getElementById('data-size');
        if (dataSizeElement) {
            const dataSizeMB = (this.streamStats.dataSize / (1024 * 1024)).toFixed(2);
            dataSizeElement.textContent = `${dataSizeMB} MB`;
        }

        // 更新平均帧大小显示 / Update average frame size display
        const avgFrameSizeElement = document.getElementById('avg-frame-size');
        if (avgFrameSizeElement) {
            avgFrameSizeElement.textContent = this.streamStats.requestCount > 0
                ? this.formatFileSize(this.streamStats.avgFrameSize)
                : '--';
        }

        // 更新下行速率显示（按累计流量 / Update the downstream rate display (by cumulative traffic
        const transferRateElement = document.getElementById('transfer-rate');
        if (transferRateElement) {
            if (this.streamStats.startTime !== null) {
                const runtimeSec = (performance.now() - this.streamStats.startTime) / 1000;
                if (runtimeSec > 0.2) {
                    const bytesPerSec = this.streamStats.dataSize / runtimeSec;
                    transferRateElement.textContent = `${this.formatFileSize(bytesPerSec)}/s`;
                } else {
                    transferRateElement.textContent = '--';
                }
            } else {
                transferRateElement.textContent = '--';
            }
        }
        
        // 更新流状态显示 / Update flow status display
        const streamStatusElement = document.getElementById('stream-status');
        if (streamStatusElement) {
            const isActive = this.streamStats.lastRequestTime !== null &&
                           (performance.now() - this.streamStats.lastRequestTime) < 5000;
            streamStatusElement.textContent = isActive ? this.t('status.active') : this.t('status.inactive');
            streamStatusElement.className = isActive ? 'status-active' : 'status-inactive';
        }
        
        // 更新运行时长显示 / Update running time display
        const runtimeElement = document.getElementById('runtime');
        if (runtimeElement && this.streamStats.startTime !== null) {
            const runtime = (performance.now() - this.streamStats.startTime) / 1000;
            runtimeElement.textContent = `${runtime.toFixed(1)}s`;
        }

        // 更新调试信息显示 / Update debugging information display
        const debugInfoElement = document.getElementById('debug-info');
        if (debugInfoElement) {
            const frameIdText = this.streamStats.lastFrameId !== null
                ? `frameId=${this.streamStats.lastFrameId}`
                : 'frameId=--';
            const frameAgeText = this.streamStats.lastFrameServerTs
                ? `age=${Math.max(0, Date.now() - this.streamStats.lastFrameServerTs * 1000).toFixed(0)}ms`
                : 'age=--';
            const reqText = `req=${this.streamStats.requestCount}`;
            const effText = `new=${this.streamStats.frameCount}`;
            debugInfoElement.textContent = `${frameIdText}, ${frameAgeText}, ${reqText}, ${effText}`;
        }
    }
    
    /**
     * 重置数据流统计 / Reset traffic statistics
     */
    resetStreamStats() {
        this.streamStats = {
            requestCount: 0,
            frameCount: 0,
            lastRequestTime: null,
            lastFrameTime: null,
            requestFps: 0.0,
            fpsCalculated: 0.0,
            resolutionDetected: null,
            dataSize: 0,
            avgFrameSize: 0,
            requestTimes: [],
            frameTimes: [],
            lastFrameId: null,
            lastFrameServerTs: null,
            startTime: null
        };
        this.updateStreamStatsDisplay();
    }
    
    /**
     * 设置画面旋转角度 / Set screen rotation angle
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
                this.showNotification(this.extractApiMessage(result, 'notify.rotationSetSuccess'), 'success');
            } else {
                throw new Error(result.message || '设置旋转失败');
            }
        } catch (error) {
            console.error('设置旋转失败:', error);
            this.showNotification(`设置旋转失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 更新旋转角度显示 / Update rotation angle display
     */
    updateRotationDisplay() {
        // 更新当前角度显示 / Update current angle display
        const rotationElement = document.getElementById('current-rotation');
        if (rotationElement) {
            rotationElement.textContent = `${this.currentSettings.rotation}°`;
        }
        
        // 更新按钮状态 / Update button state
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
     * 初始化调试控制台 / Initialize the debug console
     */
    async init() {
        console.log('[DebugConsole] 初始化调试控制台...');
        await this.initI18n();
        this.applyI18nToPage();
        
        // 设置事件监听器 / Set event listener
        this.setupEventListeners();
        
        // 初始化UI / Initialize UI
        this.initUI();
        
        // 加载数据 / Load data
        await this.loadPresets();
        await this.loadFiles();
        
        // 更新相机状态 / Update camera status
        await this.updateCameraStatus();

        // 更新系统信息 / Update system information
        await this.updateSystemInfo();
        this.startSystemInfoPolling();
        
        // 启动图像质量监控 / Start image quality monitoring
        this.startQualityMonitoring();
        
        // 初始化智能头部隐藏 / Initialize smart head hiding
        this.initSmartHeader();
        
        console.log('[DebugConsole] 调试控制台初始化完成');
    }
    
    /**
     * 设置事件监听器 / Set event listener
     */
    setupEventListeners() {
        document.getElementById('language-select')?.addEventListener('change', (e) => {
            this.setLanguage(e.target.value);
        });

        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.updateSystemInfo();
            }
        });

        window.addEventListener('beforeunload', () => {
            this.stopSystemInfoPolling();
            this.stopQualityMonitoring();
            this.endStatusPolling();
        });

        // 标签页切换 / Tab switching
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });
        
        // 相机控制 / camera control
        document.getElementById('start-preview')?.addEventListener('click', () => {
            this.startPreview();
        });
        
        document.getElementById('stop-preview')?.addEventListener('click', () => {
            this.stopPreview();
        });
        
        // 拍摄控制 / Shooting control
        document.getElementById('capture-image')?.addEventListener('click', () => {
            this.captureImage();
        });
        
        document.getElementById('start-recording')?.addEventListener('click', () => {
            this.startRecording();
        });
        
        document.getElementById('stop-recording')?.addEventListener('click', () => {
            this.stopRecording();
        });
        
        // 参数设置 / Parameter settings
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
        
        // 预设管理 / Default management
        document.getElementById('save-preset')?.addEventListener('click', () => {
            this.savePreset();
        });
        
        // 文件管理 / File management
        document.getElementById('refresh-files')?.addEventListener('click', () => {
            this.loadFiles();
        });
        
        // 设置重置统计按钮事件监听器 / Set the reset statistics button event listener
        document.getElementById('reset-stats')?.addEventListener('click', () => {
            this.resetStreamStats();
        });
        
        // 设置旋转控制按钮事件监听器 / Set up the rotation control button event listener
        document.querySelectorAll('[data-rotation]').forEach(button => {
            button.addEventListener('click', (e) => {
                const rotation = parseInt(e.target.dataset.rotation);
                this.setRotation(rotation);
            });
        });
        
        // 新增参数控制事件监听器 / Add new parameter to control event listener
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

        document.getElementById('auto-exposure-mode')?.addEventListener('change', () => {
            this.refreshModeApplyStates();
        });
        
        document.getElementById('color-mode')?.addEventListener('change', (e) => {
            this.updateColorMode(e.target.value);
            this.refreshModeApplyStates();
        });
        
        document.getElementById('white-balance-mode')?.addEventListener('change', (e) => {
            this.updateWhiteBalanceMode(e.target.value);
            this.refreshModeApplyStates();
        });

        document.getElementById('apply-auto-exposure-mode')?.addEventListener('click', async () => {
            const modeSelect = document.getElementById('auto-exposure-mode');
            if (!modeSelect) {
                return;
            }
            await this.applyAutoExposureMode(modeSelect.value === 'auto');
        });

        document.getElementById('apply-color-mode')?.addEventListener('click', async () => {
            const colorModeSelect = document.getElementById('color-mode');
            if (!colorModeSelect) {
                return;
            }
            await this.switchColorMode(colorModeSelect.value);
        });

        document.getElementById('apply-white-balance-mode')?.addEventListener('click', async () => {
            await this.applyWhiteBalanceMode();
        });
        
        document.getElementById('wb-gain-r')?.addEventListener('input', (e) => {
            this.updateWhiteBalanceGainR(parseFloat(e.target.value));
            this.refreshModeApplyStates();
        });
        
        document.getElementById('wb-gain-b')?.addEventListener('input', (e) => {
            this.updateWhiteBalanceGainB(parseFloat(e.target.value));
            this.refreshModeApplyStates();
        });
        
        // 夜间模式控制 / Night mode control
        document.getElementById('night-mode-preset')?.addEventListener('click', () => {
            this.applyNightModePreset();
        });
        
        document.getElementById('toggle-night-mode')?.addEventListener('click', () => {
            this.toggleNightMode();
        });
        
        // 安全机制 / security mechanism
        document.getElementById('backup-settings')?.addEventListener('click', () => {
            this.backupSettings();
        });
        
        document.getElementById('restore-settings')?.addEventListener('click', () => {
            this.restoreSettings();
        });

        // 直方图控制（纯前端） / Histogram control (pure front-end)
        document.getElementById('histogram-toggle')?.addEventListener('click', () => {
            if (!this.histogramState.enabled) {
                this.showNotification('请先在设置中启用直方图', 'info');
                return;
            }
            this.histogramState.overlayVisible = !this.histogramState.overlayVisible;
            this.applyHistogramVisibility();
        });

        document.getElementById('histogram-settings')?.addEventListener('click', () => {
            this.histogramState.panelVisible = !this.histogramState.panelVisible;
            this.applyHistogramVisibility();
        });

        document.getElementById('show-histogram')?.addEventListener('change', (e) => {
            this.histogramState.enabled = !!e.target.checked;
            if (!this.histogramState.enabled) {
                this.histogramState.overlayVisible = false;
            }
            this.applyHistogramVisibility();
            if (!this.histogramState.enabled) {
                this.clearHistogramCanvas();
            }
        });

        document.getElementById('show-rgb')?.addEventListener('change', (e) => {
            this.histogramState.showRgb = !!e.target.checked;
        });

        document.getElementById('show-luminance')?.addEventListener('change', (e) => {
            this.histogramState.showLuminance = !!e.target.checked;
        });

        document.getElementById('show-overexposure')?.addEventListener('change', (e) => {
            this.histogramState.showOverexposure = !!e.target.checked;
        });
        
        // 分辨率预设选择 / Resolution preset selection
        document.querySelectorAll('[data-res]').forEach(button => {
            button.addEventListener('click', (e) => {
                document.querySelectorAll('[data-res]').forEach(b=>b.classList.remove('btn-primary'));
                e.currentTarget.classList.add('btn-primary');
            });
        });
        // 应用分辨率（仅宽高，不影响帧率） / Apply resolution (width and height only, does not affect frame rate)
        document.getElementById('apply-resolution')?.addEventListener('click', () => {
            const activeBtn = document.querySelector('[data-res].btn-primary');
            if (!activeBtn) {
                this.showNotification('请选择分辨率预设', 'warning');
                return;
            }
            const [w, h] = activeBtn.dataset.res.split('x').map(v=>parseInt(v));
            this.applySizeOnly(w, h);
        });

        // 应用单独帧率 / Apply individual frame rates
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
                
                // 尽量不中断预览直接应用 / Try to apply it directly without interrupting the preview
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

        // 应用采样模式 / Apply sampling mode
        document.getElementById('apply-sampling')?.addEventListener('click', async () => {
            const sel = document.getElementById('sampling-select');
            const mode = sel?.value || 'supersample';
            const btn = document.getElementById('apply-sampling');
            
            try {
                if (btn) btn.disabled = true;
                this.showNotification('正在切换采样模式...', 'info');
                
                // 停止预览以避免旧源卡住 / Stop preview to avoid getting stuck on old source
                try { await this.stopPreview(); } catch(_){}
                const params = new URLSearchParams({ mode });
                const resp = await fetch(`/api/debug/camera/sampling?${params.toString()}`, { method: 'POST' });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || '设置采样模式失败');
                }
                this.showNotification('采样模式已切换', 'success');
                // 刷新状态并重启预览 / Refresh status and restart preview
                await this.updateCameraStatus();
                await this.startPreview();
            } catch (e) {
                console.error(e);
                this.showNotification(`设置采样模式失败: ${e.message}`, 'error');
                // 尝试恢复预览 / Try to restore preview
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
        
        // 键盘快捷键 / keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            this.handleKeyboardShortcuts(e);
        });

        // 启动时同步一次边框状态 / Synchronize the border state once at startup
        this.setRecOverlay(this.cameraStatus.recording);
        this.applyHistogramVisibility();
        
        // 快速预设按钮事件监听器 / Quickly preset button event listeners
        document.getElementById('daylight-preset')?.addEventListener('click', () => {
            this.applyQuickPreset('daylight');
        });
        
        document.getElementById('night-preset')?.addEventListener('click', () => {
            this.applyQuickPreset('night');
        });
        
        document.getElementById('deep-sky-preset')?.addEventListener('click', () => {
            this.applyQuickPreset('deep-sky');
        });
        
        document.getElementById('planetary-preset')?.addEventListener('click', () => {
            this.applyQuickPreset('planetary');
        });
        
        // 智能调整按钮 / Smart adjustment button
        document.getElementById('auto-adjust')?.addEventListener('click', () => {
            this.performAutoAdjust();
        });
    }
    
    /**
     * 初始化UI / Initialize UI
     */
    initUI() {
        // 设置默认标签页 / Set default tab
        this.switchTab('capture');
        
        // 初始化参数显示 / Initialization parameter display
        this.updateExposureDisplay(this.currentSettings.exposure);
        this.updateGainDisplay(this.currentSettings.gain);
        this.updateDigitalGainDisplay(this.currentSettings.digitalGain);
        this.updateContrastDisplay(this.currentSettings.contrast);
        this.updateBrightnessDisplay(this.currentSettings.brightness);
        this.updateSaturationDisplay(this.currentSettings.saturation);
        this.updateSharpnessDisplay(this.currentSettings.sharpness);
        this.updateNoiseReductionDisplay(this.currentSettings.noiseReduction);
        this.updateAutoExposureMode(this.currentSettings.autoExposure);
        this.updateColorMode(this.currentSettings.colorMode);
        this.updateWhiteBalanceMode(this.currentSettings.whiteBalanceMode);
        this.updateWhiteBalanceGainR(this.currentSettings.whiteBalanceGainR);
        this.updateWhiteBalanceGainB(this.currentSettings.whiteBalanceGainB);
        this.updateModeCurrentDisplays();
        this.refreshModeApplyStates();
        
        // 初始化全屏预览功能 / Initialize full screen preview function
        this.initFullscreenPreview();
        
        // 添加触摸反馈 / Add touch feedback
        document.querySelectorAll('.btn, .tab-button, .control-row input').forEach(element => {
            element.classList.add('touch-feedback');
        });
    }
    
    /**
     * 切换标签页 / Switch tabs
     */
    switchTab(tabName) {
        // 强制显示头部（用户正在导航） / Force display of header (user is navigating)
        this.forceShowHeader();
        
        // 更新按钮状态 / Update button state
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        
        // 更新内容显示 / Update content display
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `tab-${tabName}`);
        });
        
        // 特殊处理 / special handling
        if (tabName === 'files') {
            this.loadFiles();
        } else if (tabName === 'presets') {
            this.loadPresets();
        }
    }
    
    /**
     * 更新相机状态 / Update camera status
     */
    async updateCameraStatus() {
        try {
            const response = await fetch('/api/debug/camera/status');
            const status = await response.json();
            
            this.cameraStatus = status;

            // 同步关键参数状态，避免UI与相机真实状态脱节 / Synchronize the status of key parameters to avoid the disconnection between the UI and the real status of the camera
            const info = status.info || {};
            this.applyControlRanges(info.control_ranges || {});
            if (typeof info.auto_exposure === 'boolean') {
                this.currentSettings.autoExposure = info.auto_exposure;
                this.updateAutoExposureMode(info.auto_exposure, false);
            }
            if (typeof info.color_mode === 'string') {
                this.currentSettings.colorMode = info.color_mode;
                this.updateColorMode(info.color_mode, false);
            }
            if (typeof info.white_balance_mode === 'string') {
                this.currentSettings.whiteBalanceMode = info.white_balance_mode;
                this.updateWhiteBalanceMode(info.white_balance_mode, false);
            }
            if (typeof info.white_balance_gain_r === 'number') {
                this.currentSettings.whiteBalanceGainR = info.white_balance_gain_r;
            }
            if (typeof info.white_balance_gain_b === 'number') {
                this.currentSettings.whiteBalanceGainB = info.white_balance_gain_b;
            }
            this.updateModeCurrentDisplays();
            this.refreshModeApplyStates();

            this.updateStatusUI();
            this.updateInfoUI();
            
            // 如果相机正在运行，且预览未激活，则启动预览循环（避免重复重置统计） / If the camera is running and preview is not active, start a preview loop (to avoid repeatedly resetting statistics)
            if (status.streaming && !this.previewActive) {
                this.startPreviewUpdate();
            }
            // 同步录制状态与计时 / Synchronize recording status and timing
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
     * 更新状态UI / Update status UI
     */
    updateStatusUI() {
        const statusIndicator = document.getElementById('camera-status');
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('.status-text');
        
        if (this.cameraStatus.recording) {
            statusDot.className = 'status-dot recording';
            statusText.textContent = this.t('status.recording');
        } else if (this.cameraStatus.streaming) {
            statusDot.className = 'status-dot online';
            statusText.textContent = this.t('status.previewing');
        } else if (this.cameraStatus.connected) {
            statusDot.className = 'status-dot online';
            statusText.textContent = this.t('status.connected');
        } else {
            statusDot.className = 'status-dot offline';
            statusText.textContent = this.t('status.cameraOffline');
        }
        
        // 更新预览状态 / Update preview status
        document.getElementById('preview-status').textContent = 
            this.cameraStatus.streaming ? this.t('status.running') : this.t('status.notStarted');
        
        // 更新录制状态 / Update recording status
        document.getElementById('recording-status').textContent = 
            this.cameraStatus.recording ? this.t('status.recording') : this.t('status.notRecording');
        
        // 更新按钮状态 / Update button state
        this.updateButtonStates();
    }

    /**
     * 更新分辨率 / Update resolution
     */
    updateInfoUI() {
        const resEl = document.getElementById('resolution');
        const fpsEl = document.getElementById('fps');
        const info = this.cameraStatus.info || {};
        const width = info.width || (info.resolution ? parseInt(String(info.resolution).split('x')[0]) : null);
        const height = info.height || (info.resolution ? parseInt(String(info.resolution).split('x')[1]) : null);
        const captureWidth = info.capture_width || null;
        const captureHeight = info.capture_height || null;
        if (width && height) {
            const outputPixels = width * height;
            const outputMP = (outputPixels / 1_000_000).toFixed(2);
            if (captureWidth && captureHeight) {
                const capturePixels = captureWidth * captureHeight;
                const scaleRatio = outputPixels / capturePixels;
                const scalePercent = (scaleRatio * 100).toFixed(1);
                resEl.textContent = `${width}x${height} (${outputMP}MP, 全视野:${captureWidth}x${captureHeight}, ${scalePercent}%)`;
            } else {
                resEl.textContent = `${width}x${height} (${outputMP}MP)`;
            }
        } else {
            resEl.textContent = '--';
        }
        fpsEl.textContent = (info.fps || this.cameraStatus.fps || 0) ? `${info.fps || this.cameraStatus.fps}` : '--';
        const samplingEl = document.getElementById('sampling-mode');
        if (samplingEl) samplingEl.textContent = info.sampling_mode || '--';
    }
    
    /**
     * 启动预览 / Start preview
     */
    async startPreview() {
        try {
            // 显示启动状态 / Show startup status
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
     * 停止预览 / Stop preview
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
     * 开始预览更新 / Start previewing updates
     */
    startPreviewUpdate() {
        this.stopPreviewUpdate(); // 清除现有定时器 / Clear existing timer
        const previewImg = document.getElementById('preview-image');
        const overlay = document.getElementById('preview-overlay');
        if (!previewImg || !overlay) return;

        // 启动前立即隐藏覆盖层，并重置统计，避免提示一直停留 / Hide the overlay immediately before starting and reset statistics to avoid prompts remaining
        overlay.classList.add('hidden');
        this.resetStreamStats();

        // 使用单次请求循环（避免并发取消）：每次等上一帧 onload / Use a single request loop (to avoid concurrent cancellation): wait for the previous frame onload each time
        this.previewActive = true;
        // 提高预览帧率到15fps以获得更流畅的体验 / Increase the preview frame rate to 15fps for a smoother experience
        const fps = 15;
        const intervalMs = Math.max(1000 / fps, 50);
        let consecutiveFailures = 0;
        let frameToken = 0;
        let firstFrameAttempts = 0;
        const maxFirstFrameAttempts = 10;  // 前10次请求使用更短间隔 / Use shorter intervals for the first 10 requests

        const loop = async () => {
            if (!this.previewActive) return;
            const startedAt = performance.now();
            const myToken = ++frameToken;
            
            // 增加第一帧尝试计数 / Increase first frame attempt count
            if (firstFrameAttempts < maxFirstFrameAttempts) {
                firstFrameAttempts++;
            }

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 1000);

            try {
                const response = await fetch(`/api/debug/camera/preview?t=${Date.now()}`, {
                    cache: 'no-store',
                    signal: controller.signal,
                });
                if (!response.ok) {
                    throw new Error(`preview status=${response.status}`);
                }

                const frameIdRaw = response.headers.get('X-Frame-Id');
                const frameId = frameIdRaw !== null ? parseInt(frameIdRaw, 10) : null;
                const frameTsRaw = response.headers.get('X-Frame-Ts');
                const frameTs = frameTsRaw !== null ? parseFloat(frameTsRaw) : null;
                const blob = await response.blob();

                const objectUrl = URL.createObjectURL(blob);
                const loader = new Image();
                loader.onload = () => {
                    if (!this.previewActive || myToken !== frameToken) {
                        URL.revokeObjectURL(objectUrl);
                        return;
                    }

                    if (this.previewObjectUrl) {
                        URL.revokeObjectURL(this.previewObjectUrl);
                    }
                    this.previewObjectUrl = objectUrl;
                    previewImg.src = objectUrl;

                    this.analyzeStreamData(loader, {
                        frameId: Number.isFinite(frameId) ? frameId : null,
                        frameTs: Number.isFinite(frameTs) ? frameTs : null,
                        sizeBytes: blob.size,
                    });
                    this.updateHistogramFromImage(loader);

                    consecutiveFailures = 0;

                    if (firstFrameAttempts < maxFirstFrameAttempts) {
                        firstFrameAttempts = maxFirstFrameAttempts;
                        console.log(`[Preview] 第一帧获取成功，耗时 ${(performance.now() - startedAt).toFixed(1)}ms`);
                    }

                    const elapsed = performance.now() - startedAt;
                    const currentInterval = firstFrameAttempts < maxFirstFrameAttempts ? 100 : intervalMs;
                    const delay = Math.max(0, currentInterval - elapsed);
                    this.previewTimer = setTimeout(loop, delay);
                };
                loader.onerror = () => {
                    URL.revokeObjectURL(objectUrl);
                    consecutiveFailures++;
                    const retryDelay = Math.min(1000, 200 + consecutiveFailures * 200);
                    this.previewTimer = setTimeout(loop, retryDelay);
                };
                loader.src = objectUrl;
            } catch (error) {
                consecutiveFailures++;
                const retryDelay = Math.min(1000, 200 + consecutiveFailures * 200);
                this.previewTimer = setTimeout(loop, retryDelay);
            } finally {
                clearTimeout(timeoutId);
            }
        };
        loop();

        // 看门狗：若2秒未收到帧，强制刷新状态（更敏感的检测） / Watchdog: If no frame is received for 2 seconds, force refresh status (more sensitive detection)
        this.previewWatchdog = setInterval(() => {
            if (this.streamStats.lastFrameTime === null) return;
            const since = performance.now() - this.streamStats.lastFrameTime;
            if (since > 2000) {
                this.updateCameraStatus();
            }
        }, 1000);
    }
    
    /**
     * 停止预览更新 / Stop preview updates
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
        if (this.previewObjectUrl) {
            URL.revokeObjectURL(this.previewObjectUrl);
            this.previewObjectUrl = null;
        }
        // 复位预览图片 / Reset preview image
        const previewImg = document.getElementById('preview-image');
        if (previewImg) {
            try { previewImg.onload = null; previewImg.onerror = null; } catch(_){}
            previewImg.src = '/static/images/placeholder-camera.png';
        }
        // 显示覆盖层 / Show overlay
        document.getElementById('preview-overlay').classList.remove('hidden');
    }
    
    /**
     * 拍摄图片 / Take pictures
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
                
                // 更新最后拍摄时间 / Update last shooting time
                const now = new Date();
                document.getElementById('last-capture').textContent = 
                    now.toLocaleTimeString();
                
                // 刷新文件列表 / Refresh file list
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
     * 开始录制 / Start recording
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
                
                // 开始计时 / Start timing
                this.recordingStartTime = Date.now();
                this.startRecordingTimer();
                
                // 更新按钮状态 / Update button state
                this.updateRecordingButtons(true);
                this.setRecOverlay(true);
                
                // 更新状态 / update status
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
     * 停止录制 / Stop recording
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
     * 开始录制计时器 / Start recording timer
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
     * 停止录制计时器 / Stop recording timer
     */
    stopRecordingTimer() {
        if (this.recordingInterval) {
            clearInterval(this.recordingInterval);
            this.recordingInterval = null;
        }
    }
    
    /**
     * 更新录制时长 / Update recording duration
     */
    updateRecordingDuration(duration) {
        const durationElement = document.getElementById('recording-duration');
        if (durationElement) {
            const seconds = Math.floor(duration / 1000);
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            durationElement.textContent = `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
        }
        
        // 更新录制徽章 / Update recording badge
        const recBadgeTime = document.getElementById('rec-badge-time');
        if (recBadgeTime) {
            const seconds = Math.floor(duration / 1000);
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            recBadgeTime.textContent = `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
        }
    }
    
    /**
     * 设置录制覆盖层 / 设置录制覆盖层
     */
    setRecOverlay(recording) {
        const recBadge = document.getElementById('rec-badge');
        if (recBadge) {
            recBadge.style.display = recording ? 'flex' : 'none';
        }
    }
    
    /**
     * 更新录制按钮状态 / Update record button state
     */
    updateRecordingButtons(isRecording) {
        const startBtn = document.getElementById('start-recording');
        const stopBtn = document.getElementById('stop-recording');
        
        if (startBtn) startBtn.disabled = isRecording;
        if (stopBtn) stopBtn.disabled = !isRecording;
    }
    
    /**
     * 更新按钮状态 / Update button state
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
     * 开始状态轮询 / Start status polling
     */
    beginStatusPolling() {
        this.endStatusPolling();
        this.statusInterval = setInterval(() => {
            this.updateCameraStatus();
        }, 2000);
    }
    
    /**
     * 结束状态轮询 / End status polling
     */
    endStatusPolling() {
        if (this.statusInterval) {
            clearInterval(this.statusInterval);
            this.statusInterval = null;
        }
    }

    /**
     * 更新系统信息 / Update system information
     */
    async updateSystemInfo() {
        try {
            const response = await fetch('/api/system/info');
            if (!response.ok) {
                return;
            }
            this.systemInfo = await response.json();
            this.updateSystemInfoUI();
        } catch (error) {
            console.warn('[DebugConsole] 获取系统信息失败:', error);
        }
    }

    /**
     * 开始系统信息轮询 / Start system info polling
     */
    startSystemInfoPolling() {
        this.stopSystemInfoPolling();
        this.systemInfoInterval = setInterval(() => {
            if (document.hidden) {
                return;
            }
            this.updateSystemInfo();
        }, 10000);
    }

    /**
     * 停止系统信息轮询 / Stop system info polling
     */
    stopSystemInfoPolling() {
        if (this.systemInfoInterval) {
            clearInterval(this.systemInfoInterval);
            this.systemInfoInterval = null;
        }
    }

    /**
     * 更新系统信息UI / Update system info UI
     */
    updateSystemInfoUI() {
        const info = this.systemInfo || {};

        const setText = (id, value) => {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = value;
            }
        };

        setText('system-platform', info.platform || '--');
        setText('system-os', info.os || '--');
        setText('system-cpu-usage', this.formatPercent(info.cpu_usage));
        setText('system-memory-usage', this.formatPercent(info.memory_usage));
        setText('system-temperature', this.formatTemperature(info.temperature));
        setText('system-wifi-quality', this.formatPercent(info.wifi_quality));
        setText('system-wifi-signal', this.formatWifiSignal(info.wifi_signal_dbm, info.wifi_interface));
        setText('system-uptime', this.formatUptime(info.uptime_seconds));
        setText('system-loadavg', this.formatLoadAverage(info.load_average_1m));
    }

    formatPercent(value) {
        if (typeof value !== 'number' || Number.isNaN(value)) {
            return '--';
        }
        return `${value.toFixed(1)}%`;
    }

    formatTemperature(value) {
        if (typeof value !== 'number' || Number.isNaN(value) || value <= 0) {
            return '--';
        }
        return `${value.toFixed(1)}°C`;
    }

    formatWifiSignal(signal, iface) {
        const hasSignal = typeof signal === 'number' && !Number.isNaN(signal);
        const suffix = iface ? ` (${iface})` : '';
        if (!hasSignal) {
            return `--${suffix}`;
        }
        return `${signal.toFixed(1)} dBm${suffix}`;
    }

    formatUptime(seconds) {
        if (typeof seconds !== 'number' || Number.isNaN(seconds) || seconds <= 0) {
            return '--';
        }
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        if (days > 0) {
            return `${days}d ${hours}h`;
        }
        return `${hours}h ${minutes}m`;
    }

    formatLoadAverage(value) {
        if (typeof value !== 'number' || Number.isNaN(value)) {
            return '--';
        }
        return value.toFixed(2);
    }
    
    /**
     * 应用相机控制范围 / Apply camera control ranges
     */
    applyControlRanges(controlRanges) {
        if (!controlRanges || typeof controlRanges !== 'object') {
            return;
        }

        this.applySingleControlRange(
            'exposure-setting',
            controlRanges.exposure_us,
            {
                decimals: 0,
                onUpdate: (value) => this.updateExposureDisplay(parseInt(value, 10)),
            }
        );
        this.applySingleControlRange(
            'gain-setting',
            controlRanges.analogue_gain,
            {
                decimals: 1,
                onUpdate: (value) => this.updateGainDisplay(parseFloat(value)),
            }
        );
        this.applySingleControlRange(
            'digital-gain-setting',
            controlRanges.digital_gain,
            {
                decimals: 1,
                onUpdate: (value) => this.updateDigitalGainDisplay(parseFloat(value)),
            }
        );
    }

    applySingleControlRange(elementId, rangeInfo, options = {}) {
        if (!rangeInfo || typeof rangeInfo !== 'object') {
            return;
        }
        const slider = document.getElementById(elementId);
        if (!slider) {
            return;
        }

        const min = Number(rangeInfo.min);
        const max = Number(rangeInfo.max);
        const defaultValue = Number(rangeInfo.default);
        let step = Number(rangeInfo.step);
        if (!Number.isFinite(min) || !Number.isFinite(max) || min >= max) {
            return;
        }
        if (!Number.isFinite(step) || step <= 0) {
            step = slider.step && Number(slider.step) > 0 ? Number(slider.step) : 1;
        }

        slider.min = String(min);
        slider.max = String(max);
        slider.step = String(step);

        const current = Number(slider.value);
        const fallback = Number.isFinite(defaultValue) ? defaultValue : min;
        const baseValue = Number.isFinite(current) ? current : fallback;
        const clamped = Math.max(min, Math.min(max, baseValue));
        const decimals = Number.isInteger(options.decimals) ? options.decimals : 0;
        const normalized =
            decimals > 0 ? Number(clamped.toFixed(decimals)) : Math.round(clamped);
        slider.value = String(normalized);

        if (typeof options.onUpdate === 'function') {
            options.onUpdate(slider.value);
        }
    }

    /**
     * 更新曝光显示 / Update exposure display
     */
    updateExposureDisplay(value) {
        document.getElementById('exposure-value').textContent = value;
    }
    
    /**
     * 更新增益显示 / Update gain display
     */
    updateGainDisplay(value) {
        document.getElementById('gain-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新数字增益显示 / Updated digital gain display
     */
    updateDigitalGainDisplay(value) {
        document.getElementById('digital-gain-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新对比度显示 / Update contrast display
     */
    updateContrastDisplay(value) {
        document.getElementById('contrast-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新亮度显示 / Update brightness display
     */
    updateBrightnessDisplay(value) {
        document.getElementById('brightness-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新饱和度显示 / Update saturation display
     */
    updateSaturationDisplay(value) {
        document.getElementById('saturation-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新锐度显示 / Update sharpness display
     */
    updateSharpnessDisplay(value) {
        document.getElementById('sharpness-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新降噪显示 / Update noise reduction display
     */
    updateNoiseReductionDisplay(value) {
        document.getElementById('noise-reduction-value').textContent = value;
    }

    /**
     * 更新自动曝光模式 / Update auto-exposure mode
     */
    updateAutoExposureMode(isAuto, syncSelect = true) {
        this.currentSettings.autoExposure = isAuto;

        const modeSelect = document.getElementById('auto-exposure-mode');
        if (modeSelect && syncSelect) {
            modeSelect.value = isAuto ? 'auto' : 'manual';
        }

        // 自动曝光时禁用手动曝光参数，避免控制冲突 / Disable manual exposure parameters during automatic exposure to avoid control conflicts
        const manualControls = ['exposure-setting', 'gain-setting', 'digital-gain-setting'];
        manualControls.forEach((id) => {
            const element = document.getElementById(id);
            if (element) {
                element.disabled = isAuto;
                if (element.parentElement) {
                    element.parentElement.style.opacity = isAuto ? '0.5' : '1';
                }
            }
        });

        const autoAdjustBtn = document.getElementById('auto-adjust');
        if (autoAdjustBtn) {
            autoAdjustBtn.disabled = isAuto;
            autoAdjustBtn.title = isAuto ? this.t('hint.autoAdjustManualRequired') : '';
        }
    }
    
    /**
     * 更新颜色模式显示 / Update color mode display
     */
    updateColorMode(mode, syncSelect = true) {
        const colorModeSelect = document.getElementById('color-mode');
        if (colorModeSelect && syncSelect) {
            colorModeSelect.value = mode;
        }
        
        // 黑白模式时禁用某些颜色相关设置 / Disable certain color-related settings when in black and white mode
        const colorRelatedControls = ['saturation-setting', 'white-balance-mode'];
        colorRelatedControls.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.disabled = (mode === 'mono');
                element.parentElement.style.opacity = (mode === 'mono') ? '0.5' : '1';
            }
        });
        
        // 更新提示信息 / Update prompt information
        const hint = colorModeSelect?.parentElement?.nextElementSibling;
        if (hint && hint.classList.contains('param-hint')) {
            if (mode === 'mono') {
                hint.textContent = this.t('hint.colorModeMono');
                hint.style.color = 'var(--debug-success)';
            } else {
                hint.textContent = this.t('hint.colorModeColor');
                hint.style.color = 'var(--debug-text-secondary)';
            }
        }
    }
    
    /**
     * 更新白平衡模式 / Update white balance mode
     */
    updateWhiteBalanceMode(mode, syncSelect = true) {
        const whiteBalanceModeSelect = document.getElementById('white-balance-mode');
        if (whiteBalanceModeSelect && syncSelect) {
            whiteBalanceModeSelect.value = mode;
        }

        const gainsContainer = document.getElementById('white-balance-gains');
        if (gainsContainer) {
            gainsContainer.style.display = mode === 'manual' ? 'block' : 'none';
        }
    }

    /**
     * 更新模式类参数的当前生效值显示 / Update current applied values for mode settings
     */
    updateModeCurrentDisplays() {
        const exposureCurrent = document.getElementById('auto-exposure-current');
        if (exposureCurrent) {
            const modeSelect = document.getElementById('auto-exposure-mode');
            const effectiveAutoExposure = typeof this.currentSettings.autoExposure === 'boolean'
                ? this.currentSettings.autoExposure
                : (modeSelect ? modeSelect.value === 'auto' : true);
            exposureCurrent.textContent = effectiveAutoExposure
                ? this.t('settings.exposureModeAuto')
                : this.t('settings.exposureModeManual');
        }

        const colorCurrent = document.getElementById('color-mode-current');
        if (colorCurrent) {
            const colorModeSelect = document.getElementById('color-mode');
            const effectiveColorMode = this.currentSettings.colorMode
                || (colorModeSelect ? colorModeSelect.value : 'color');
            colorCurrent.textContent = effectiveColorMode === 'mono'
                ? this.t('settings.colorModeMono')
                : this.t('settings.colorModeColor');
        }

        const whiteBalanceCurrent = document.getElementById('white-balance-mode-current');
        if (whiteBalanceCurrent) {
            const whiteBalanceModeSelect = document.getElementById('white-balance-mode');
            const mode = this.currentSettings.whiteBalanceMode
                || (whiteBalanceModeSelect ? whiteBalanceModeSelect.value : 'auto');
            const modeTextMap = {
                auto: this.t('settings.whiteBalanceAuto'),
                manual: this.t('settings.whiteBalanceManual'),
                night: this.t('settings.whiteBalanceNight')
            };
            whiteBalanceCurrent.textContent = modeTextMap[mode] || mode || '--';
        }
    }

    /**
     * 刷新模式应用按钮状态 / Refresh apply button state for mode settings
     */
    refreshModeApplyStates() {
        const autoExposureSelect = document.getElementById('auto-exposure-mode');
        const colorModeSelect = document.getElementById('color-mode');
        const whiteBalanceModeSelect = document.getElementById('white-balance-mode');

        this.refreshSingleModeApplyState(
            'apply-auto-exposure-mode',
            'auto-exposure-dirty-hint',
            autoExposureSelect ? (autoExposureSelect.value === 'auto') !== this.currentSettings.autoExposure : false
        );
        this.refreshSingleModeApplyState(
            'apply-color-mode',
            'color-mode-dirty-hint',
            colorModeSelect ? colorModeSelect.value !== this.currentSettings.colorMode : false
        );
        this.refreshSingleModeApplyState(
            'apply-white-balance-mode',
            'white-balance-mode-dirty-hint',
            (() => {
                if (!whiteBalanceModeSelect) {
                    return false;
                }
                const modeChanged = whiteBalanceModeSelect.value !== this.currentSettings.whiteBalanceMode;
                if (modeChanged) {
                    return true;
                }
                if (whiteBalanceModeSelect.value !== 'manual') {
                    return false;
                }
                const gainR = parseFloat(document.getElementById('wb-gain-r')?.value || '1.0');
                const gainB = parseFloat(document.getElementById('wb-gain-b')?.value || '1.0');
                const sameGainR = Math.abs(gainR - (this.currentSettings.whiteBalanceGainR ?? 1.0)) < 1e-6;
                const sameGainB = Math.abs(gainB - (this.currentSettings.whiteBalanceGainB ?? 1.0)) < 1e-6;
                return !(sameGainR && sameGainB);
            })()
        );
    }

    /**
     * 单项模式按钮状态刷新 / Refresh single mode apply button state
     */
    refreshSingleModeApplyState(buttonId, hintId, hasPendingChange) {
        const applyButton = document.getElementById(buttonId);
        if (applyButton) {
            // 保持可点击，避免“按钮无反应”的误判；无变更时由点击逻辑给出提示 / Keep clickable to avoid "button no response"; show hint in click logic when unchanged
            applyButton.disabled = false;
        }

        const hint = document.getElementById(hintId);
        if (hint) {
            hint.textContent = hasPendingChange
                ? this.t('settings.pendingUnsynced')
                : this.t('settings.pendingSync');
            hint.style.color = hasPendingChange ? 'var(--debug-warning)' : 'var(--debug-text-secondary)';
        }
    }
    
    /**
     * 更新白平衡红色增益显示 / Updated white balance red gain display
     */
    updateWhiteBalanceGainR(value) {
        document.getElementById('wb-gain-r-value').textContent = value.toFixed(1);
    }
    
    /**
     * 更新白平衡蓝色增益显示 / Updated white balance blue gain display
     */
    updateWhiteBalanceGainB(value) {
        document.getElementById('wb-gain-b-value').textContent = value.toFixed(1);
    }

    /**
     * 仅应用曝光模式切换 / Apply exposure mode switch only
     */
    async applyAutoExposureMode(isAuto) {
        if (isAuto === this.currentSettings.autoExposure) {
            this.showNotification('曝光模式未变化', 'info');
            this.refreshModeApplyStates();
            return;
        }

        try {
            const response = await fetch(`/api/debug/camera/auto-exposure?enabled=${isAuto}`, {
                method: 'POST'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '曝光模式更新失败');
            }

            this.currentSettings.autoExposure = isAuto;
            await this.updateCameraStatus();
            this.refreshModeApplyStates();
        } catch (error) {
            console.error('[DebugConsole] 曝光模式切换失败:', error);
            this.showNotification(`曝光模式切换失败: ${error.message}`, 'error');
            // 回滚到相机真实状态，避免 UI 与设备状态不一致 / Roll back to actual camera state to avoid inconsistency between UI and device state
            await this.updateCameraStatus();
            this.refreshModeApplyStates();
        }
    }

    /**
     * 仅应用白平衡模式切换 / Apply white-balance mode switch only
     */
    async applyWhiteBalanceMode() {
        const modeSelect = document.getElementById('white-balance-mode');
        if (!modeSelect) {
            return;
        }

        const mode = modeSelect.value;
        const gainR = parseFloat(document.getElementById('wb-gain-r')?.value || '1.0');
        const gainB = parseFloat(document.getElementById('wb-gain-b')?.value || '1.0');
        const sameMode = mode === this.currentSettings.whiteBalanceMode;
        const sameGainR = Math.abs(gainR - (this.currentSettings.whiteBalanceGainR ?? 1.0)) < 1e-6;
        const sameGainB = Math.abs(gainB - (this.currentSettings.whiteBalanceGainB ?? 1.0)) < 1e-6;
        if (sameMode && (mode !== 'manual' || (sameGainR && sameGainB))) {
            this.showNotification('白平衡参数未变化', 'info');
            this.refreshModeApplyStates();
            return;
        }

        try {
            const response = await fetch(
                `/api/debug/camera/white-balance?mode=${encodeURIComponent(mode)}&gain_r=${gainR}&gain_b=${gainB}`,
                { method: 'POST' }
            );
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '白平衡模式切换失败');
            }

            this.currentSettings.whiteBalanceMode = mode;
            await this.updateCameraStatus();
            this.refreshModeApplyStates();
        } catch (error) {
            console.error('[DebugConsole] 白平衡模式切换失败:', error);
            this.showNotification(`白平衡模式切换失败: ${error.message}`, 'error');
            await this.updateCameraStatus();
            this.refreshModeApplyStates();
        }
    }
    
    /**
     * 应用设置 / Apply settings
     */
    async applySettings() {
        const modeSelect = document.getElementById('auto-exposure-mode');
        const requestedAutoExposure = modeSelect
            ? modeSelect.value === 'auto'
            : !!this.currentSettings.autoExposure;
        const settings = {
            autoExposure: requestedAutoExposure,
            exposure: parseInt(document.getElementById('exposure-setting').value),
            gain: parseFloat(document.getElementById('gain-setting').value),
            digitalGain: parseFloat(document.getElementById('digital-gain-setting').value),
            contrast: parseFloat(document.getElementById('contrast-setting').value),
            brightness: parseFloat(document.getElementById('brightness-setting').value),
            saturation: parseFloat(document.getElementById('saturation-setting').value),
            sharpness: parseFloat(document.getElementById('sharpness-setting').value),
            noiseReduction: parseInt(document.getElementById('noise-reduction-setting').value)
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
                this.currentSettings = {...this.currentSettings, ...settings};
                this.updateAutoExposureMode(!!settings.autoExposure, false);
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
     * 切换颜色模式 / Switch color mode
     */
    async switchColorMode(colorMode) {
        if (colorMode === this.currentSettings.colorMode) {
            this.showNotification('颜色模式未变化', 'info');
            this.refreshModeApplyStates();
            return;
        }
        try {
            this.showNotification(`正在切换到${colorMode === 'mono' ? '黑白' : '彩色'}模式...`, 'info');
            
            const response = await fetch(`/api/debug/camera/color-mode?color_mode=${colorMode}`, {
                method: 'POST'
            });
            
            if (response.ok) {
                const result = await response.json();
                this.currentSettings.colorMode = colorMode;
                this.updateColorMode(colorMode);
                this.showNotification(this.extractApiMessage(result, 'notify.colorModeSwitched'), 'success');
                
                // 刷新相机状态 / Refresh camera status
                await this.updateCameraStatus();
                this.refreshModeApplyStates();
                
                // 给用户一些性能提示 / Give users some performance tips
                if (colorMode === 'mono') {
                    setTimeout(() => {
                        this.showNotification('黑白模式已启用，帧率和灵敏度将得到提升', 'info');
                    }, 1000);
                }
            } else {
                const error = await response.json();
                throw new Error(error.detail || '颜色模式切换失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 颜色模式切换失败:', error);
            this.showNotification(`颜色模式切换失败: ${error.message}`, 'error');
            
            // 恢复UI状态 / Restore UI state
            this.updateColorMode(this.currentSettings.colorMode);
            this.refreshModeApplyStates();
        }
    }
    
    /**
     * 重置设置 / Reset settings
     */
    async resetSettings() {
        try {
            const response = await fetch('/api/debug/camera/reset', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification('相机已重置到默认设置', 'success');
                
                // 重新加载相机状态以获取默认值 / Reload camera state to get default values
                await this.updateCameraStatus();
                
                // 更新UI显示 / Update UI display
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
     * 应用夜间模式预设 / Apply night mode preset
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
     * 切换夜间模式 / Switch to night mode
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
     * 备份设置 / Backup settings
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
     * 恢复设置 / Restore settings
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
     * 仅应用尺寸（宽高），不影响帧率 / Applies only dimensions (width and height), does not affect frame rate
     */
    async applySizeOnly(width, height) {
        try {
            const resp = await fetch(`/api/debug/camera/size?width=${width}&height=${height}`, { method: 'POST' });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || '设置分辨率失败');
            }
            const body = await resp.json();
            const info = body.info || {};
            const appliedW = info.width || width;
            const appliedH = info.height || height;
            const captureW = info.capture_width || null;
            const captureH = info.capture_height || null;
            const suffix = (captureW && captureH) ? `，全视野采集 ${captureW}x${captureH}` : '';
            this.showNotification(`分辨率请求 ${width}x${height}，实际生效 ${appliedW}x${appliedH}${suffix}`, 'success');
            await this.updateCameraStatus();
        } catch (e) {
            console.error(e);
            this.showNotification(`设置分辨率失败: ${e.message}`, 'error');
        }
    }
    
    /**
     * 启动图像质量监控 / Start image quality monitoring
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
        }, 3000); // 每3秒更新一次 / Updates every 3 seconds
        
        console.log('[QualityMonitoring] 图像质量监控已启动');
    }
    
    /**
     * 停止图像质量监控 / Stop image quality monitoring
     */
    stopQualityMonitoring() {
        if (this.qualityMonitoringInterval) {
            clearInterval(this.qualityMonitoringInterval);
            this.qualityMonitoringInterval = null;
            console.log('[QualityMonitoring] 图像质量监控已停止');
        }
    }
    
    /**
     * 更新图像质量指标 / Update image quality metrics
     */
    updateQualityMetrics(quality) {
        const normalizedQuality = this.normalizeQualityMetrics(quality);

        // 更新噪点水平 / Update noise level
        const noiseBar = document.getElementById('noise-level-bar');
        const noiseValue = document.getElementById('noise-level');
        if (noiseBar && noiseValue) {
            noiseBar.style.width = `${Math.min(100, normalizedQuality.noiseLevel10 * 10)}%`;
            noiseValue.textContent = `${normalizedQuality.noiseLevel10.toFixed(1)}`;
        }
        
        // 更新曝光充足度 / Update exposure adequacy
        const exposureBar = document.getElementById('exposure-bar');
        const exposureValue = document.getElementById('exposure-level');
        if (exposureBar && exposureValue) {
            exposureBar.style.width = `${Math.min(100, normalizedQuality.exposureLevel10 * 10)}%`;
            exposureValue.textContent = `${normalizedQuality.exposureLevel10.toFixed(1)}`;
        }
        
        // 更新增益水平 / Update gain level
        const gainBar = document.getElementById('gain-bar');
        const gainValue = document.getElementById('gain-level');
        if (gainBar && gainValue) {
            gainBar.style.width = `${Math.min(100, normalizedQuality.gainLevel * 10)}%`;
            gainValue.textContent = `${normalizedQuality.gainLevel.toFixed(1)}`;
        }
        
        // 更新建议 / Update suggestions
        this.updateQualityRecommendations(normalizedQuality);
    }
    
    /**
     * 归一化质量指标（兼容 exposure_adequacy 与 exposure_level） / Normalized quality index (compatible with exposure_adequacy and exposure_level)
     */
    normalizeQualityMetrics(quality = {}) {
        const hasExposureAdequacy = typeof quality.exposure_adequacy === 'number';
        const hasExposureLevel = typeof quality.exposure_level === 'number';

        let exposureAdequacy = 0;
        if (hasExposureAdequacy) {
            exposureAdequacy = quality.exposure_adequacy;
        } else if (hasExposureLevel) {
            exposureAdequacy = quality.exposure_level / 10.0;
        }
        exposureAdequacy = Math.min(1.0, Math.max(0.0, exposureAdequacy));

        const rawNoiseLevel = typeof quality.noise_level === 'number' ? quality.noise_level : 0;
        const noiseLevel10 = rawNoiseLevel <= 1 ? rawNoiseLevel * 10 : rawNoiseLevel;

        const gainLevel = typeof quality.gain_level === 'number' ? quality.gain_level : 0;

        return {
            exposureAdequacy,
            exposureLevel10: exposureAdequacy * 10,
            noiseLevel10: Math.min(10, Math.max(0, noiseLevel10)),
            gainLevel: Math.max(0, gainLevel),
        };
    }

    /**
     * 更新质量建议 / Update quality recommendations
     */
    updateQualityRecommendations(quality) {
        const recommendationsContainer = document.getElementById('quality-recommendations');
        if (!recommendationsContainer) return;
        
        const recommendations = [];
        
        if (quality.noiseLevel10 > 7) {
            recommendations.push(this.t('quality.rec.reduceGain'));
        }
        
        if (quality.exposureLevel10 < 3) {
            recommendations.push(this.t('quality.rec.increaseExposure'));
        } else if (quality.exposureLevel10 > 8) {
            recommendations.push(this.t('quality.rec.decreaseExposure'));
        }
        
        if (quality.gainLevel > 8) {
            recommendations.push(this.t('quality.rec.lowerGain'));
        }
        
        if (recommendations.length === 0) {
            recommendations.push(this.t('quality.rec.good'));
        }
        
        recommendationsContainer.innerHTML = recommendations.map(rec => 
            `<div class="quality-recommendation">${rec}</div>`
        ).join('');
    }
    
    /**
     * 加载预设 / Load preset
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
     * 渲染预设列表 / Render preset list
     */
    renderPresets() {
        const presetsGrid = document.getElementById('presets-grid');
        
        if (this.presets.length === 0) {
            presetsGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">💾</div>
                    <div class="empty-state-text">${this.t('presets.emptyTitle')}</div>
                    <div class="empty-state-subtext">${this.t('presets.emptyHint')}</div>
                </div>
            `;
            return;
        }
        
        presetsGrid.innerHTML = this.presets.map(preset => `
            <div class="preset-item">
                <div class="preset-name">${preset.name}</div>
                <div class="preset-description">${preset.description || this.t('presets.noDescription')}</div>
                <div class="preset-params">
                    <div class="param-line">
                        <strong>${this.t('presets.basic')}</strong> ${this.t('presets.exposure')}${preset.exposure_us}μs | ${this.t('presets.gain')}${preset.analogue_gain}x
                        ${preset.digital_gain !== undefined ? ` | ${this.t('presets.digitalGain')}${preset.digital_gain}x` : ''}
                    </div>
                    ${[preset.contrast, preset.brightness, preset.saturation, preset.sharpness].some(v => v !== undefined) ? `
                    <div class="param-line">
                        <strong>${this.t('presets.enhancement')}</strong>
                        ${preset.contrast !== undefined ? ` ${this.t('presets.contrast')}${preset.contrast}` : ''}
                        ${preset.brightness !== undefined ? ` ${this.t('presets.brightness')}${preset.brightness}` : ''}
                        ${preset.saturation !== undefined ? ` ${this.t('presets.saturation')}${preset.saturation}` : ''}
                        ${preset.sharpness !== undefined ? ` ${this.t('presets.sharpness')}${preset.sharpness}` : ''}
                    </div>
                    ` : ''}
                    ${preset.auto_exposure !== undefined || preset.noise_reduction !== undefined || preset.white_balance_mode !== undefined || preset.color_mode !== undefined ? `
                    <div class="param-line">
                        <strong>${this.t('presets.advanced')}</strong>
                        ${preset.auto_exposure !== undefined ? ` ${preset.auto_exposure ? this.t('presets.autoExposure') : this.t('presets.manualExposure')}` : ''}
                        ${preset.color_mode !== undefined ? ` ${preset.color_mode === 'mono' ? this.t('presets.monoMode') : this.t('presets.colorMode')}` : ''}
                        ${preset.noise_reduction !== undefined ? ` ${this.t('presets.noiseReduction')}${preset.noise_reduction}${this.t('presets.levelSuffix')}` : ''}
                        ${preset.white_balance_mode !== undefined ? ` ${this.t('presets.whiteBalance')}${preset.white_balance_mode}` : ''}
                        ${preset.rotation !== undefined ? ` ${this.t('presets.rotation')}${preset.rotation}°` : ''}
                    </div>
                    ` : ''}
                </div>
                <div class="preset-actions">
                    <button class="btn btn-primary" onclick="window.debugConsole.applyPreset('${preset.name}')">
                        ${this.t('presets.apply')}
                    </button>
                    <button class="btn btn-error" onclick="window.debugConsole.deletePreset('${preset.name}')">
                        ${this.t('presets.delete')}
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    /**
     * 保存预设 / save preset
     */
    async savePreset() {
        const name = document.getElementById('preset-name').value.trim();
        const description = document.getElementById('preset-description').value.trim();
        
        if (!name) {
            this.showNotification('请输入预设名称', 'warning');
            return;
        }
        
        try {
            // 优先保存“当前已生效状态”，避免 UI 暂存值与真实设备状态冲突 / Prefer saving the currently applied state to avoid conflicts between pending UI values and actual device state
            const effectiveAutoExposure = typeof this.currentSettings.autoExposure === 'boolean'
                ? this.currentSettings.autoExposure
                : (document.getElementById('auto-exposure-mode')?.value === 'auto');
            const response = await fetch('/api/debug/camera/presets', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: name,
                    description: description,
                    exposure_us: parseInt(document.getElementById('exposure-setting').value),
                    analogue_gain: parseFloat(document.getElementById('gain-setting').value),
                    digital_gain: parseFloat(document.getElementById('digital-gain-setting').value),
                    auto_exposure: effectiveAutoExposure,
                    // 图像增强参数 / Image enhancement parameters
                    contrast: parseFloat(document.getElementById('contrast-setting').value),
                    brightness: parseFloat(document.getElementById('brightness-setting').value),
                    saturation: parseFloat(document.getElementById('saturation-setting').value),
                    sharpness: parseFloat(document.getElementById('sharpness-setting').value),
                    // 高级参数 / Advanced parameters
                    noise_reduction: parseInt(document.getElementById('noise-reduction-setting').value),
                    white_balance_mode: document.getElementById('white-balance-mode').value,
                    white_balance_gain_r: parseFloat(document.getElementById('wb-gain-r').value),
                    white_balance_gain_b: parseFloat(document.getElementById('wb-gain-b').value),
                    // 其他参数 / Other parameters
                    rotation: this.currentSettings.rotation,
                    color_mode: document.getElementById('color-mode').value
                })
            });
            
            if (response.ok) {
                this.showNotification('预设保存成功', 'success');
                
                // 清空表单 / Clear form
                document.getElementById('preset-name').value = '';
                document.getElementById('preset-description').value = '';
                
                // 重新加载预设 / Reload preset
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
     * 获取预设数据 / Get default data
     */
    async getPresetData(presetName) {
        try {
            const response = await fetch('/api/debug/camera/presets');
            if (response.ok) {
                const data = await response.json();
                const presets = data.presets || [];
                return presets.find(preset => preset.name === presetName);
            }
        } catch (error) {
            console.error('[DebugConsole] 获取预设数据失败:', error);
        }
        return null;
    }
    
    /**
     * 应用预设 / Apply preset
     */
    async applyPreset(presetName) {
        try {
            // 先获取预设数据 / Get the default data first
            const presetData = await this.getPresetData(presetName);
            if (!presetData) {
                throw new Error('预设数据不存在');
            }
            
            const response = await fetch(`/api/debug/camera/presets/${encodeURIComponent(presetName)}/apply`, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification(`预设 '${presetName}' 已应用`, 'success');
                
                // 重新加载相机状态 / Reload camera state
                await this.updateCameraStatus();
                
                // 更新UI控件值 / Update UI control value
                document.getElementById('exposure-setting').value = presetData.exposure_us;
                document.getElementById('gain-setting').value = presetData.analogue_gain;
                document.getElementById('digital-gain-setting').value = presetData.digital_gain || 1.0;
                
                if (presetData.contrast !== undefined) {
                    document.getElementById('contrast-setting').value = presetData.contrast;
                }
                if (presetData.brightness !== undefined) {
                    document.getElementById('brightness-setting').value = presetData.brightness;
                }
                if (presetData.saturation !== undefined) {
                    document.getElementById('saturation-setting').value = presetData.saturation;
                }
                if (presetData.sharpness !== undefined) {
                    document.getElementById('sharpness-setting').value = presetData.sharpness;
                }
                if (presetData.noise_reduction !== undefined) {
                    document.getElementById('noise-reduction-setting').value = presetData.noise_reduction;
                }
                if (presetData.white_balance_mode) {
                    document.getElementById('white-balance-mode').value = presetData.white_balance_mode;
                }
                if (presetData.white_balance_gain_r !== undefined) {
                    document.getElementById('wb-gain-r').value = presetData.white_balance_gain_r;
                }
                if (presetData.white_balance_gain_b !== undefined) {
                    document.getElementById('wb-gain-b').value = presetData.white_balance_gain_b;
                }
                
                if (presetData.color_mode !== undefined) {
                    document.getElementById('color-mode').value = presetData.color_mode;
                }

                if (presetData.auto_exposure !== undefined) {
                    this.updateAutoExposureMode(!!presetData.auto_exposure);
                }
                
                // 更新显示值 / Update display value
                this.updateExposureDisplay(presetData.exposure_us);
                this.updateGainDisplay(presetData.analogue_gain);
                this.updateDigitalGainDisplay(presetData.digital_gain ?? 1.0);
                this.updateContrastDisplay(presetData.contrast ?? 1.0);
                this.updateBrightnessDisplay(presetData.brightness ?? 0.0);
                this.updateSaturationDisplay(presetData.saturation ?? 1.0);
                this.updateSharpnessDisplay(presetData.sharpness ?? 1.0);
                this.updateNoiseReductionDisplay(presetData.noise_reduction ?? 0);
                this.updateWhiteBalanceMode(presetData.white_balance_mode ?? 'auto');
                this.updateWhiteBalanceGainR(presetData.white_balance_gain_r ?? 1.0);
                this.updateWhiteBalanceGainB(presetData.white_balance_gain_b ?? 1.0);
                this.updateColorMode(presetData.color_mode ?? 'color');
                this.updateModeCurrentDisplays();
                this.refreshModeApplyStates();
                
                // 更新旋转角度 / Update rotation angle
                if (presetData.rotation !== undefined) {
                    this.currentSettings.rotation = presetData.rotation;
                    this.updateRotationDisplay();
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
     * 删除预设 / Delete preset
     */
    async deletePreset(presetName) {
        if (!confirm(this.t('confirm.deletePreset', { name: presetName }))) {
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
     * 加载文件列表 / Load file list
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
     * 渲染文件列表 / Render file list
     */
    renderFiles() {
        const filesList = document.getElementById('files-list');
        
        if (this.files.length === 0) {
            filesList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📁</div>
                    <div class="empty-state-text">${this.t('files.emptyTitle')}</div>
                    <div class="empty-state-subtext">${this.t('files.emptyHint')}</div>
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
                            ${this.t('files.download')}
                        </button>
                        <button class="btn btn-secondary" onclick="window.debugConsole.showFileInfo('${file.name}')">
                            ${this.t('files.details')}
                        </button>
                        <button class="btn btn-danger" onclick="window.debugConsole.deleteFile('${file.name}')">
                            ${this.t('files.delete')}
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    /**
     * 下载文件 / Download file
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
     * 显示文件信息 / Show file information
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
                            <span class="info-label">${this.t('files.size')}</span>
                            <span class="info-value">${this.formatFileSize(info.size)}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">${this.t('files.modified')}</span>
                            <span class="info-value">${new Date(info.modified).toLocaleString()}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">${this.t('files.type')}</span>
                            <span class="info-value">${info.type === 'image' ? this.t('files.type.image') : this.t('files.type.video')}</span>
                        </div>
                        ${info.exposure_us ? `
                        <div class="info-item">
                            <span class="info-label">${this.t('files.exposure')}</span>
                            <span class="info-value">${info.exposure_us}μs</span>
                        </div>
                        ` : ''}
                        ${info.analogue_gain ? `
                        <div class="info-item">
                            <span class="info-label">${this.t('files.analogueGain')}</span>
                            <span class="info-value">${info.analogue_gain}x</span>
                        </div>
                        ` : ''}
                        ${info.resolution ? `
                        <div class="info-item">
                            <span class="info-label">${this.t('files.resolution')}</span>
                            <span class="info-value">${info.resolution}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>
            `;
            
            this.showModal(this.t('files.infoTitle'), infoHtml);
            
        } catch (error) {
            console.error('[DebugConsole] 获取文件信息失败:', error);
            this.showNotification('获取文件信息失败', 'error');
        }
    }
    
    /**
     * 删除文件 / Delete files
     */
    async deleteFile(filename) {
        // 确认删除 / Confirm deletion
        if (!confirm(this.t('confirm.deleteFile', { name: filename }))) {
            return;
        }
        
        try {
            const response = await fetch(`/api/debug/files/${encodeURIComponent(filename)}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '删除失败');
            }
            
            const result = await response.json();
            this.showNotification(this.extractApiMessage(result, 'notify.fileDeleteSuccess'), 'success');
            
            // 重新加载文件列表 / Reload file list
            await this.loadFiles();
            
        } catch (error) {
            console.error('[DebugConsole] 删除文件失败:', error);
            this.showNotification(`删除文件失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 格式化文件大小 / Format file size
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    /**
     * 处理键盘快捷键 / Handle keyboard shortcuts
     */
    handleKeyboardShortcuts(e) {
        // 防止在输入框中触发快捷键 / Prevent shortcut keys from being triggered in input boxes
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
     * 显示通知 / Show notification
     */
    showNotification(message, type = 'info') {
        // 显示重要通知时强制显示头部 / Force header to be displayed when showing important notifications
        if (type === 'error' || type === 'warning') {
            this.forceShowHeader();
        }
        
        const notifications = document.getElementById('notifications');
        
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = this.localizeText(message);
        
        notifications.appendChild(notification);
        
        // 显示动画 / show animation
        setTimeout(() => {
            notification.classList.add('show');
        }, 100);
        
        // 自动隐藏 / auto-hide
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
     * 显示模态框 / Show modal box
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
        
        // 显示动画 / show animation
        setTimeout(() => {
            modal.classList.add('show');
        }, 100);
        
        // 关闭事件 / close event
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
     * 关闭模态框 / Close modal box
     */
    closeModal(modal) {
        modal.classList.remove('show');
        setTimeout(() => {
            if (modal.parentNode) {
                modal.parentNode.removeChild(modal);
            }
        }, 300);
    }
    
    /**
     * 应用快速预设 / Apply quick presets
     */
    async applyQuickPreset(presetType) {
        const presets = {
            'daylight': {
                exposure: 5000,
                gain: 1.0,
                digitalGain: 1.0,
                contrast: 1.2,
                brightness: 0.1,
                saturation: 1.1,
                sharpness: 1.2,
                noiseReduction: 1,
                whiteBalanceMode: 'auto'
            },
            'night': {
                exposure: 30000,
                gain: 4.0,
                digitalGain: 1.5,
                contrast: 1.1,
                brightness: 0.0,
                saturation: 0.9,
                sharpness: 1.0,
                noiseReduction: 2,
                whiteBalanceMode: 'night'
            },
            'deep-sky': {
                exposure: 60000,
                gain: 8.0,
                digitalGain: 2.0,
                contrast: 1.3,
                brightness: -0.1,
                saturation: 1.2,
                sharpness: 0.8,
                noiseReduction: 3,
                whiteBalanceMode: 'auto'
            },
            'planetary': {
                exposure: 2000,
                gain: 2.0,
                digitalGain: 1.2,
                contrast: 1.5,
                brightness: 0.2,
                saturation: 1.3,
                sharpness: 1.8,
                noiseReduction: 1,
                whiteBalanceMode: 'auto'
            }
        };
        
        const preset = presets[presetType];
        if (!preset) {
            this.showNotification('未知的预设类型', 'error');
            return;
        }
        
        try {
            // 更新UI控件 / Update UI controls
            document.getElementById('exposure-setting').value = preset.exposure;
            document.getElementById('gain-setting').value = preset.gain;
            document.getElementById('digital-gain-setting').value = preset.digitalGain;
            document.getElementById('contrast-setting').value = preset.contrast;
            document.getElementById('brightness-setting').value = preset.brightness;
            document.getElementById('saturation-setting').value = preset.saturation;
            document.getElementById('sharpness-setting').value = preset.sharpness;
            document.getElementById('noise-reduction-setting').value = preset.noiseReduction;
            document.getElementById('white-balance-mode').value = preset.whiteBalanceMode;
            
            // 更新显示值 / Update display value
            this.updateExposureDisplay(preset.exposure);
            this.updateGainDisplay(preset.gain);
            this.updateDigitalGainDisplay(preset.digitalGain);
            this.updateContrastDisplay(preset.contrast);
            this.updateBrightnessDisplay(preset.brightness);
            this.updateSaturationDisplay(preset.saturation);
            this.updateSharpnessDisplay(preset.sharpness);
            this.updateNoiseReductionDisplay(preset.noiseReduction);
            this.updateWhiteBalanceMode(preset.whiteBalanceMode);

            // 快速预设属于手动调参场景，先将待应用值切到手动曝光 / Quick preset is a manual tuning scenario, set pending value to manual exposure first.
            const autoExposureSelect = document.getElementById('auto-exposure-mode');
            if (autoExposureSelect) {
                autoExposureSelect.value = 'manual';
            }
            this.refreshModeApplyStates();

            await this.applyAutoExposureMode(false);
            await this.applyWhiteBalanceMode();
            
            // 应用设置 / Apply settings
            await this.applySettings();
            
            const presetNames = {
                'daylight': '白天模式',
                'night': '夜间模式',
                'deep-sky': '深空模式',
                'planetary': '行星模式'
            };
            
            this.showNotification(`已应用${presetNames[presetType]}预设`, 'success');
            
        } catch (error) {
            console.error('[DebugConsole] 应用快速预设失败:', error);
            this.showNotification(`应用预设失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 执行智能调整 / Perform smart adjustments
     */
    async performAutoAdjust() {
        if (!this.cameraStatus.streaming) {
            this.showNotification('请先启动相机预览', 'warning');
            return;
        }

        if (this.currentSettings.autoExposure) {
            this.showNotification('自动曝光模式下无需智能调整，请先切换为手动曝光', 'info');
            return;
        }
        
        try {
            this.showNotification('正在分析图像质量...', 'info');
            
            // 获取图像质量指标 / Get image quality metrics
            const response = await fetch('/api/debug/camera/image-quality');
            if (!response.ok) {
                throw new Error('获取图像质量失败');
            }
            
            const data = await response.json();
            const quality = this.normalizeQualityMetrics(data.quality || {});
            
            // 基于质量指标自动调整参数 / Automatically adjust parameters based on quality indicators
            const currentExposure = parseInt(document.getElementById('exposure-setting').value);
            const currentGain = parseFloat(document.getElementById('gain-setting').value);
            
            let adjustments = {};
            let suggestions = [];
            
            // 曝光调整 / exposure adjustment
            if (quality.exposureLevel10 < 3) {
                // 曝光不足 / Underexposure
                adjustments.exposure = Math.min(100000, Math.round(currentExposure * 1.5));
                suggestions.push('增加曝光时间以提高亮度');
            } else if (quality.exposureLevel10 > 8) {
                // 过曝 / overexposed
                adjustments.exposure = Math.max(1000, Math.round(currentExposure * 0.7));
                suggestions.push('减少曝光时间以避免过曝');
            }
            
            // 增益调整 / Gain adjustment
            if (quality.noiseLevel10 > 7) {
                // 噪点过高 / Noise is too high
                adjustments.gain = Math.max(1.0, currentGain * 0.8);
                suggestions.push('降低增益以减少噪点');
            } else if (quality.gainLevel < 3 && quality.exposureLevel10 < 5) {
                // 增益过低且曝光不足 / Gain is too low and underexposed
                adjustments.gain = Math.min(16.0, currentGain * 1.3);
                suggestions.push('适当提高增益');
            }
            
            // 降噪调整 / Noise reduction adjustment
            if (quality.noiseLevel10 > 6) {
                adjustments.noiseReduction = Math.min(4, quality.noiseLevel10 > 8 ? 3 : 2);
                suggestions.push('启用降噪功能');
            }
            
            // 对比度调整 / Contrast adjustment
            if (quality.exposureLevel10 > 5 && quality.exposureLevel10 < 7) {
                adjustments.contrast = 1.2; // 适中曝光时提高对比度 / Improve contrast at moderate exposures
                suggestions.push('适当提高对比度');
            }
            
            if (Object.keys(adjustments).length === 0) {
                this.showNotification('当前参数已经很好，无需调整', 'success');
                return;
            }
            
            // 应用调整 / Apply adjustments
            if (adjustments.exposure) {
                document.getElementById('exposure-setting').value = adjustments.exposure;
                this.updateExposureDisplay(adjustments.exposure);
            }
            
            if (adjustments.gain) {
                document.getElementById('gain-setting').value = adjustments.gain;
                this.updateGainDisplay(adjustments.gain);
            }
            
            if (adjustments.noiseReduction !== undefined) {
                document.getElementById('noise-reduction-setting').value = adjustments.noiseReduction;
                this.updateNoiseReductionDisplay(adjustments.noiseReduction);
            }
            
            if (adjustments.contrast) {
                document.getElementById('contrast-setting').value = adjustments.contrast;
                this.updateContrastDisplay(adjustments.contrast);
            }
            
            // 应用设置 / Apply settings
            await this.applySettings();
            
            this.showNotification(`智能调整完成: ${suggestions.join(', ')}`, 'success');
            
        } catch (error) {
            console.error('[DebugConsole] 智能调整失败:', error);
            this.showNotification(`智能调整失败: ${error.message}`, 'error');
        }
    }
}

// 页面加载完成后初始化调试控制台 / Initialize the debugging console after the page is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.debugConsole = new DebugConsole();
});

// 添加模态框样式 / Add modal box style
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

// 添加样式到页面 / Add styles to the page
const styleSheet = document.createElement('style');
styleSheet.textContent = modalStyles;
document.head.appendChild(styleSheet);