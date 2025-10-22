/**
 * OGScope 革命性电子极轴镜 - 横屏全屏应用
 * 支持MJPEG视频流、星点识别、极轴校准、PWA功能
 */

class OGScopeApp {
    constructor() {
        this.isStreaming = false;
        this.isAligning = false;
        this.isZoomed = false;
        this.alignmentProgress = 0;
        this.alignmentStatus = 'idle';
        this.cameraSettings = {
            exposure: 10,
            gain: 1.0,
            brightness: 1.0
        };
        this.deferredPrompt = null;
        this.isInstalled = false;
        this.networkStatus = 'online';
        this.particles = [];
        this.maxParticles = 30;
        
        this.init();
    }

    /**
     * 初始化应用
     */
    async init() {
        console.log('[OGScope] 初始化革命性电子极轴镜...');
        
        // 显示加载屏幕
        this.showLoadingScreen();
        
        // 注册Service Worker
        await this.registerServiceWorker();
        
        // 设置事件监听器
        this.setupEventListeners();
        
        // 初始化UI
        this.initUI();
        
        // 检查网络状态
        this.updateNetworkStatus();
        
        // 初始化粒子背景
        this.initParticles();
        
        // 设置PWA安装提示
        this.setupInstallPrompt();
        
        // 模拟加载过程
        await this.simulateLoading();
        
        // 隐藏加载屏幕
        this.hideLoadingScreen();
        
        console.log('[OGScope] 初始化完成');
    }

    /**
     * 显示加载屏幕
     */
    showLoadingScreen() {
        const loadingScreen = document.getElementById('loading-screen');
        if (loadingScreen) {
            loadingScreen.classList.remove('hidden');
        }
    }

    /**
     * 隐藏加载屏幕
     */
    hideLoadingScreen() {
        const loadingScreen = document.getElementById('loading-screen');
        if (loadingScreen) {
            setTimeout(() => {
                loadingScreen.classList.add('hidden');
            }, 500);
        }
    }

    /**
     * 模拟加载过程
     */
    async simulateLoading() {
        const loadingProgress = document.getElementById('loading-progress');
        const loadingText = document.getElementById('loading-text');
        
        const steps = [
            { progress: 20, text: '正在初始化系统...' },
            { progress: 40, text: '正在连接摄像头...' },
            { progress: 60, text: '正在加载星图数据库...' },
            { progress: 80, text: '正在校准系统...' },
            { progress: 100, text: '系统就绪' }
        ];
        
        for (const step of steps) {
            await new Promise(resolve => setTimeout(resolve, 800));
            if (loadingProgress) {
                loadingProgress.style.width = step.progress + '%';
            }
            if (loadingText) {
                loadingText.textContent = step.text;
            }
        }
    }

    /**
     * 注册Service Worker
     */
    async registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                const registration = await navigator.serviceWorker.register('/static/sw.js');
                console.log('[OGScope] Service Worker 注册成功:', registration);
            } catch (error) {
                console.error('[OGScope] Service Worker 注册失败:', error);
            }
        }
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 视频控制按钮
        const startStreamBtn = document.getElementById('start-stream');
        const stopStreamBtn = document.getElementById('stop-stream');
        const zoomToggleBtn = document.getElementById('zoom-toggle');
        
        if (startStreamBtn) {
            startStreamBtn.addEventListener('click', () => this.startVideoStream());
        }
        if (stopStreamBtn) {
            stopStreamBtn.addEventListener('click', () => this.stopVideoStream());
        }
        if (zoomToggleBtn) {
            zoomToggleBtn.addEventListener('click', () => this.toggleVideoZoom());
        }
        
        // 校准控制按钮
        const startAlignmentBtn = document.getElementById('start-alignment');
        const stopAlignmentBtn = document.getElementById('stop-alignment');
        
        if (startAlignmentBtn) {
            startAlignmentBtn.addEventListener('click', () => this.startPolarAlignment());
        }
        if (stopAlignmentBtn) {
            stopAlignmentBtn.addEventListener('click', () => this.stopPolarAlignment());
        }
        
        // PWA安装按钮
        const installAppBtn = document.getElementById('install-app');
        const dismissInstallBtn = document.getElementById('dismiss-install');
        
        if (installAppBtn) {
            installAppBtn.addEventListener('click', () => this.installPWA());
        }
        if (dismissInstallBtn) {
            dismissInstallBtn.addEventListener('click', () => this.dismissInstallPrompt());
        }
        
        // 网络状态监听
        window.addEventListener('online', () => this.updateNetworkStatus());
        window.addEventListener('offline', () => this.updateNetworkStatus());
        
        // 键盘快捷键
        this.setupKeyboardShortcuts();
        
        // 触摸手势
        this.setupTouchGestures();
    }

    /**
     * 初始化UI
     */
    initUI() {
        this.updateSystemStatus('ready', '系统就绪');
        this.updateConnectionStatus('online');
        this.updateVideoInfo();
        this.updateAlignmentProgress(0);
        this.updateAlignmentMetrics();
        this.updateCelestialInfo();
    }

    /**
     * 更新系统状态
     */
    updateSystemStatus(status, text) {
        const statusDisplay = document.getElementById('status-display');
        if (statusDisplay) {
            statusDisplay.textContent = text;
        }
        
        const modeDisplay = document.getElementById('mode-display');
        if (modeDisplay) {
            modeDisplay.textContent = status === 'ready' ? '就绪' : '检测中...';
        }
    }

    /**
     * 更新连接状态
     */
    updateConnectionStatus(status) {
        this.networkStatus = status;
        const networkStatus = document.getElementById('network-status');
        if (networkStatus) {
            networkStatus.className = `network-status ${status}`;
            const statusText = networkStatus.querySelector('.status-text');
            if (statusText) {
                statusText.textContent = status === 'online' ? '在线' : '离线';
            }
        }
    }

    /**
     * 更新网络状态
     */
    updateNetworkStatus() {
        const isOnline = navigator.onLine;
        this.updateConnectionStatus(isOnline ? 'online' : 'offline');
    }

    /**
     * 更新视频信息
     */
    updateVideoInfo() {
        // 模拟视频信息更新
        const resolution = document.getElementById('resolution');
        const fps = document.getElementById('fps');
        const exposureDisplay = document.getElementById('exposure-display');
        
        if (resolution) resolution.textContent = '1920×1080';
        if (fps) fps.textContent = '30fps';
        if (exposureDisplay) exposureDisplay.textContent = this.cameraSettings.exposure + 'ms';
    }

    /**
     * 开始视频流
     */
    async startVideoStream() {
        try {
            console.log('[OGScope] 开始视频流...');
            this.isStreaming = true;
            
            const startBtn = document.getElementById('start-stream');
            const stopBtn = document.getElementById('stop-stream');
            
            if (startBtn) startBtn.disabled = true;
            if (stopBtn) stopBtn.disabled = false;
            
            // 更新视频流URL（添加时间戳防止缓存）
            const videoStream = document.getElementById('mjpeg-stream');
            if (videoStream) {
                videoStream.src = `/api/camera/preview?t=${Date.now()}`;
            }
            
            this.showNotification('success', '视频流已启动', '摄像头连接成功');
            
        } catch (error) {
            console.error('[OGScope] 启动视频流失败:', error);
            this.showNotification('error', '视频流启动失败', error.message);
        }
    }

    /**
     * 停止视频流
     */
    stopVideoStream() {
        console.log('[OGScope] 停止视频流...');
        this.isStreaming = false;
        
        const startBtn = document.getElementById('start-stream');
        const stopBtn = document.getElementById('stop-stream');
        
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
        
        const videoStream = document.getElementById('mjpeg-stream');
        if (videoStream) {
            videoStream.src = '';
        }
        
        this.showNotification('info', '视频流已停止', '摄像头连接已断开');
    }

    /**
     * 切换视频缩放
     */
    toggleVideoZoom() {
        this.isZoomed = !this.isZoomed;
        const videoStream = document.getElementById('mjpeg-stream');
        
        if (videoStream) {
            if (this.isZoomed) {
                videoStream.classList.add('zoomed');
                this.showNotification('info', '视频已放大', '双击屏幕可恢复原始大小');
            } else {
                videoStream.classList.remove('zoomed');
                this.showNotification('info', '视频已恢复', '双击屏幕可放大视频');
            }
        }
    }

    /**
     * 开始极轴校准
     */
    async startPolarAlignment() {
        try {
            console.log('[OGScope] 开始极轴校准...');
            this.isAligning = true;
            this.alignmentStatus = 'starting';
            
            const startBtn = document.getElementById('start-alignment');
            const stopBtn = document.getElementById('stop-alignment');
            
            if (startBtn) startBtn.disabled = true;
            if (stopBtn) stopBtn.disabled = false;
            
            // 显示校准进度环
            const alignmentRing = document.getElementById('alignment-ring');
            if (alignmentRing) {
                alignmentRing.classList.add('active');
            }
            
            // 开始校准流程
            await this.startAlignmentProcess();
            
        } catch (error) {
            console.error('[OGScope] 启动极轴校准失败:', error);
            this.showNotification('error', '校准启动失败', error.message);
        }
    }

    /**
     * 停止极轴校准
     */
    stopPolarAlignment() {
        console.log('[OGScope] 停止极轴校准...');
        this.isAligning = false;
        this.alignmentStatus = 'idle';
        this.alignmentProgress = 0;
        
        const startBtn = document.getElementById('start-alignment');
        const stopBtn = document.getElementById('stop-alignment');
        
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
        
        // 隐藏校准进度环
        const alignmentRing = document.getElementById('alignment-ring');
        if (alignmentRing) {
            alignmentRing.classList.remove('active');
        }
        
        this.updateAlignmentProgress(0);
        this.updateAlignmentStatus('校准已停止');
        
        this.showNotification('info', '校准已停止', '极轴校准流程已中断');
    }

    /**
     * 开始校准流程
     */
    async startAlignmentProcess() {
        const steps = [
            { status: 'starting', progress: 10, text: '系统启动中...' },
            { status: 'identifying', progress: 30, text: '天区识别中...' },
            { status: 'calibrating', progress: 60, text: '校准完成' },
            { status: 'targeting', progress: 80, text: '瞄准中...' },
            { status: 'rendering', progress: 100, text: '渲染天空数据...' }
        ];
        
        for (const step of steps) {
            if (!this.isAligning) break;
            
            this.alignmentStatus = step.status;
            this.alignmentProgress = step.progress;
            
            this.updateAlignmentProgress(step.progress);
            this.updateAlignmentStatus(step.text);
            
            // 模拟星点识别
            if (step.status === 'identifying') {
                this.simulateStarDetection();
            }
            
            // 模拟目标指示
            if (step.status === 'calibrating') {
                this.simulateTargetIndication();
            }
            
            // 模拟震动反馈
            if (step.status === 'targeting') {
                this.triggerVibrationFeedback();
            }
            
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
        
        if (this.isAligning) {
            this.showNotification('success', '校准完成', '极轴校准成功完成！');
            this.isAligning = false;
        }
    }

    /**
     * 模拟星点检测
     */
    simulateStarDetection() {
        const starMarkers = document.getElementById('star-markers');
        if (!starMarkers) return;
        
        // 清除现有星点
        starMarkers.innerHTML = '';
        
        // 生成随机星点
        const starCount = Math.floor(Math.random() * 5) + 3;
        for (let i = 0; i < starCount; i++) {
            const star = document.createElement('div');
            star.className = 'star-marker';
            star.style.left = Math.random() * 80 + 10 + '%';
            star.style.top = Math.random() * 80 + 10 + '%';
            
            const label = document.createElement('div');
            label.className = 'star-label';
            label.textContent = `星${i + 1}`;
            star.appendChild(label);
            
            starMarkers.appendChild(star);
        }
    }

    /**
     * 模拟目标指示
     */
    simulateTargetIndication() {
        const polarTarget = document.getElementById('polar-target');
        if (polarTarget) {
            polarTarget.style.display = 'block';
            polarTarget.style.left = Math.random() * 60 + 20 + '%';
            polarTarget.style.top = Math.random() * 60 + 20 + '%';
        }
    }

    /**
     * 触发震动反馈
     */
    triggerVibrationFeedback() {
        if ('vibrate' in navigator) {
            navigator.vibrate([100, 50, 100]);
        } else {
            // 视觉反馈替代
            const videoContainer = document.getElementById('video-container');
            if (videoContainer) {
                videoContainer.style.animation = 'pulse 0.5s ease-in-out';
                setTimeout(() => {
                    videoContainer.style.animation = '';
                }, 500);
            }
        }
    }

    /**
     * 更新校准进度
     */
    updateAlignmentProgress(progress) {
        this.alignmentProgress = progress;
        
        const progressDisplay = document.getElementById('progress-display');
        if (progressDisplay) {
            progressDisplay.textContent = progress + '%';
        }
    }

    /**
     * 更新校准状态
     */
    updateAlignmentStatus(text) {
        const statusDisplay = document.getElementById('status-display');
        if (statusDisplay) {
            statusDisplay.textContent = text;
        }
    }

    /**
     * 更新校准指标
     */
    updateAlignmentMetrics() {
        const azimuthError = document.getElementById('azimuth-error');
        const altitudeError = document.getElementById('altitude-error');
        const precisionLevel = document.getElementById('precision-level');
        
        if (azimuthError) {
            azimuthError.textContent = this.isAligning ? 
                (Math.random() * 10).toFixed(1) : '--';
        }
        if (altitudeError) {
            altitudeError.textContent = this.isAligning ? 
                (Math.random() * 10).toFixed(1) : '--';
        }
        if (precisionLevel) {
            precisionLevel.textContent = this.isAligning ? 
                (Math.random() * 5 + 1).toFixed(1) : '--';
        }
    }

    /**
     * 更新天体信息
     */
    updateCelestialInfo() {
        const celestialList = document.getElementById('celestial-list');
        if (!celestialList) return;
        
        const celestialObjects = [
            { name: '北极星', magnitude: '2.0' },
            { name: '小熊座α', magnitude: '1.9' },
            { name: '小熊座β', magnitude: '2.1' }
        ];
        
        celestialList.innerHTML = '';
        celestialObjects.forEach(obj => {
            const item = document.createElement('div');
            item.className = 'celestial-item';
            item.innerHTML = `
                <span class="star-name">${obj.name}</span>
                <span class="star-magnitude">${obj.magnitude}</span>
            `;
            celestialList.appendChild(item);
        });
    }

    /**
     * 设置键盘快捷键
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            switch (e.key) {
                case ' ':
                    e.preventDefault();
                    if (this.isStreaming) {
                        this.stopVideoStream();
                    } else {
                        this.startVideoStream();
                    }
                    break;
                case 'a':
                case 'A':
                    e.preventDefault();
                    if (this.isAligning) {
                        this.stopPolarAlignment();
                    } else {
                        this.startPolarAlignment();
                    }
                    break;
                case 'z':
                case 'Z':
                    e.preventDefault();
                    this.toggleVideoZoom();
                    break;
                case 'Escape':
                    e.preventDefault();
                    if (this.isAligning) {
                        this.stopPolarAlignment();
                    }
                    break;
            }
        });
    }

    /**
     * 设置触摸手势
     */
    setupTouchGestures() {
        const videoContainer = document.getElementById('video-container');
        if (!videoContainer) return;
        
        let lastTouchTime = 0;
        let touchStartY = 0;
        
        videoContainer.addEventListener('touchstart', (e) => {
            touchStartY = e.touches[0].clientY;
        });
        
        videoContainer.addEventListener('touchend', (e) => {
            const touchEndY = e.changedTouches[0].clientY;
            const touchDuration = Date.now() - lastTouchTime;
            
            // 双击缩放
            if (touchDuration < 300) {
                this.toggleVideoZoom();
            }
            
            // 上下滑动调节亮度
            const deltaY = touchStartY - touchEndY;
            if (Math.abs(deltaY) > 50) {
                if (deltaY > 0) {
                    this.adjustBrightness(0.1);
                } else {
                    this.adjustBrightness(-0.1);
                }
            }
            
            lastTouchTime = Date.now();
        });
    }

    /**
     * 调节亮度
     */
    adjustBrightness(delta) {
        this.cameraSettings.brightness = Math.max(0.5, Math.min(2.0, 
            this.cameraSettings.brightness + delta));
        
        const brightnessValue = document.getElementById('brightness-value');
        if (brightnessValue) {
            brightnessValue.textContent = this.cameraSettings.brightness.toFixed(1) + '×';
        }
        
        this.showNotification('info', '亮度已调节', 
            `当前亮度: ${this.cameraSettings.brightness.toFixed(1)}×`);
    }

    /**
     * 设置PWA安装提示
     */
    setupInstallPrompt() {
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            
            // 延迟显示安装提示
            setTimeout(() => {
                this.showInstallPrompt();
            }, 5000);
        });
        
        // 检查是否已安装
        window.addEventListener('appinstalled', () => {
            this.isInstalled = true;
            this.hideInstallPrompt();
            this.showNotification('success', '应用已安装', 'OGScope已成功安装到主屏幕');
        });
    }

    /**
     * 显示安装提示
     */
    showInstallPrompt() {
        if (this.isInstalled || !this.deferredPrompt) return;
        
        const installPrompt = document.getElementById('install-prompt');
        if (installPrompt) {
            installPrompt.classList.add('show');
        }
    }

    /**
     * 隐藏安装提示
     */
    hideInstallPrompt() {
        const installPrompt = document.getElementById('install-prompt');
        if (installPrompt) {
            installPrompt.classList.remove('show');
        }
    }

    /**
     * 安装PWA
     */
    async installPWA() {
        if (!this.deferredPrompt) return;
        
        this.deferredPrompt.prompt();
        const { outcome } = await this.deferredPrompt.userChoice;
        
        if (outcome === 'accepted') {
            console.log('[OGScope] 用户接受了安装提示');
        } else {
            console.log('[OGScope] 用户拒绝了安装提示');
        }
        
        this.deferredPrompt = null;
        this.hideInstallPrompt();
    }

    /**
     * 取消安装提示
     */
    dismissInstallPrompt() {
        this.hideInstallPrompt();
        // 24小时内不再显示
        localStorage.setItem('ogscope-install-dismissed', Date.now().toString());
    }

    /**
     * 显示通知
     */
    showNotification(type, title, message) {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = `
            <div class="notification-header">
                <h4 class="notification-title">${title}</h4>
                <button class="notification-close">×</button>
            </div>
            <div class="notification-body">${message}</div>
        `;
        
        document.body.appendChild(notification);
        
        // 显示动画
        setTimeout(() => {
            notification.classList.add('show');
        }, 100);
        
        // 关闭按钮事件
        const closeBtn = notification.querySelector('.notification-close');
        closeBtn.addEventListener('click', () => {
            notification.classList.remove('show');
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        });
        
        // 自动关闭
        setTimeout(() => {
            if (notification.parentNode) {
                notification.classList.remove('show');
                setTimeout(() => {
                    if (notification.parentNode) {
                        document.body.removeChild(notification);
                    }
                }, 300);
            }
        }, 5000);
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
                    <h3 class="modal-title">${title}</h3>
                    <button class="modal-close">×</button>
                </div>
                <div class="modal-body">${content}</div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // 显示动画
        setTimeout(() => {
            modal.classList.add('show');
        }, 100);
        
        // 关闭按钮事件
        const closeBtn = modal.querySelector('.modal-close');
        closeBtn.addEventListener('click', () => {
            modal.classList.remove('show');
            setTimeout(() => {
                document.body.removeChild(modal);
            }, 300);
        });
        
        // 点击背景关闭
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('show');
                setTimeout(() => {
                    document.body.removeChild(modal);
                }, 300);
            }
        });
    }

    /**
     * 初始化粒子背景
     */
    initParticles() {
        const particlesBg = document.getElementById('particles-bg');
        if (!particlesBg) return;
        
        // 创建粒子
        for (let i = 0; i < this.maxParticles; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            particle.style.cssText = `
                position: absolute;
                width: 2px;
                height: 2px;
                background: var(--particle-color);
                border-radius: 50%;
                opacity: ${Math.random() * 0.5 + 0.2};
                left: ${Math.random() * 100}%;
                top: ${Math.random() * 100}%;
                animation: particleFloat ${Math.random() * 10 + 10}s linear infinite;
            `;
            particlesBg.appendChild(particle);
        }
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.ogscopeApp = new OGScopeApp();
});

// 导出类供其他模块使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = OGScopeApp;
}