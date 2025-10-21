/**
 * OGScope PWA 移动端应用
 * 支持触摸控制、离线功能、推送通知等
 */

class OGScopeApp {
    constructor() {
        this.isOnline = navigator.onLine;
        this.cameraStream = null;
        this.alignmentInProgress = false;
        this.touchStartY = 0;
        this.touchStartX = 0;
        
        this.init();
    }
    
    /**
     * 初始化应用
     */
    async init() {
        console.log('[OGScope] 初始化应用...');
        
        // 注册Service Worker
        await this.registerServiceWorker();
        
        // 设置事件监听器
        this.setupEventListeners();
        
        // 初始化UI
        this.initUI();
        
        // 检查网络状态
        this.updateNetworkStatus();
        
        // 检查PWA安装提示
        this.checkInstallPrompt();
        
        // 初始化相机
        this.initCamera();
        
        console.log('[OGScope] 应用初始化完成');
    }
    
    /**
     * 注册Service Worker
     */
    async registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                const registration = await navigator.serviceWorker.register('/static/sw.js');
                console.log('[SW] 注册成功:', registration.scope);
                
                // 监听更新
                registration.addEventListener('updatefound', () => {
                    const newWorker = registration.installing;
                    newWorker.addEventListener('statechange', () => {
                        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                            this.showUpdateNotification();
                        }
                    });
                });
                
            } catch (error) {
                console.error('[SW] 注册失败:', error);
            }
        }
    }
    
    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 网络状态监听
        window.addEventListener('online', () => {
            this.isOnline = true;
            this.updateNetworkStatus();
            this.showNotification('网络已连接', 'success');
        });
        
        window.addEventListener('offline', () => {
            this.isOnline = false;
            this.updateNetworkStatus();
            this.showNotification('网络连接断开', 'warning');
        });
        
        // 标签页切换
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });
        
        // 相机控制
        document.getElementById('start-preview')?.addEventListener('click', () => {
            this.startCameraPreview();
        });
        
        document.getElementById('stop-preview')?.addEventListener('click', () => {
            this.stopCameraPreview();
        });
        
        // 相机参数控制
        document.getElementById('exposure')?.addEventListener('input', (e) => {
            this.updateCameraExposure(parseInt(e.target.value));
        });
        
        document.getElementById('gain')?.addEventListener('input', (e) => {
            this.updateCameraGain(parseFloat(e.target.value));
        });
        
        // 极轴校准控制
        document.getElementById('start-align')?.addEventListener('click', () => {
            this.startPolarAlignment();
        });
        
        document.getElementById('stop-align')?.addEventListener('click', () => {
            this.stopPolarAlignment();
        });
        
        // 触摸手势
        this.setupTouchGestures();
        
        // 键盘快捷键
        this.setupKeyboardShortcuts();
        
        // PWA安装提示
        this.setupInstallPrompt();
    }
    
    /**
     * 初始化UI
     */
    initUI() {
        // 设置默认标签页
        this.switchTab('camera');
        
        // 初始化相机参数显示
        this.updateParameterDisplays();
        
        // 添加触摸反馈类
        document.querySelectorAll('.btn, .tab-button, .control-row input').forEach(element => {
            element.classList.add('touch-feedback');
        });
    }
    
    /**
     * 设置触摸手势
     */
    setupTouchGestures() {
        const cameraPreview = document.getElementById('preview');
        if (!cameraPreview) return;
        
        // 双击缩放
        let lastTap = 0;
        cameraPreview.addEventListener('touchend', (e) => {
            const currentTime = new Date().getTime();
            const tapLength = currentTime - lastTap;
            
            if (tapLength < 500 && tapLength > 0) {
                e.preventDefault();
                this.toggleCameraZoom();
            }
            lastTap = currentTime;
        });
        
        // 长按显示详细信息
        let longPressTimer;
        cameraPreview.addEventListener('touchstart', (e) => {
            longPressTimer = setTimeout(() => {
                this.showCameraInfo();
            }, 800);
        });
        
        cameraPreview.addEventListener('touchend', () => {
            clearTimeout(longPressTimer);
        });
        
        cameraPreview.addEventListener('touchmove', () => {
            clearTimeout(longPressTimer);
        });
        
        // 滑动手势
        let startY = 0;
        cameraPreview.addEventListener('touchstart', (e) => {
            startY = e.touches[0].clientY;
        });
        
        cameraPreview.addEventListener('touchmove', (e) => {
            const currentY = e.touches[0].clientY;
            const diff = startY - currentY;
            
            // 上下滑动调整亮度
            if (Math.abs(diff) > 50) {
                const brightnessChange = diff > 0 ? 0.1 : -0.1;
                this.adjustCameraBrightness(brightnessChange);
                startY = currentY;
            }
        });
    }
    
    /**
     * 设置键盘快捷键
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // 防止在输入框中触发快捷键
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return;
            }
            
            switch(e.key) {
                case '1':
                    this.switchTab('camera');
                    break;
                case '2':
                    this.switchTab('controls');
                    break;
                case '3':
                    this.switchTab('alignment');
                    break;
                case ' ':
                    e.preventDefault();
                    this.toggleCameraPreview();
                    break;
                case 'Escape':
                    this.stopPolarAlignment();
                    break;
            }
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
        
        // 更新URL
        const url = new URL(window.location);
        url.searchParams.set('tab', tabName);
        window.history.replaceState({}, '', url);
    }
    
    /**
     * 初始化相机
     */
    async initCamera() {
        try {
            // 获取相机配置
            const config = await this.fetchCameraConfig();
            this.updateCameraUI(config);
            
            // 开始预览
            this.startCameraPreview();
            
        } catch (error) {
            console.error('[Camera] 初始化失败:', error);
            this.showNotification('相机初始化失败', 'error');
        }
    }
    
    /**
     * 开始相机预览
     */
    async startCameraPreview() {
        try {
            const response = await fetch('/api/camera/start', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.updatePreviewImage();
                this.updateButtonStates(true);
                this.showNotification('相机预览已开始', 'success');
            } else {
                throw new Error('启动预览失败');
            }
        } catch (error) {
            console.error('[Camera] 启动预览失败:', error);
            this.showNotification('启动相机预览失败', 'error');
        }
    }
    
    /**
     * 停止相机预览
     */
    async stopCameraPreview() {
        try {
            await fetch('/api/camera/stop', {
                method: 'POST'
            });
            
            this.updateButtonStates(false);
            this.showNotification('相机预览已停止', 'info');
        } catch (error) {
            console.error('[Camera] 停止预览失败:', error);
        }
    }
    
    /**
     * 切换相机预览
     */
    toggleCameraPreview() {
        const isPreviewing = document.getElementById('stop-preview').disabled === false;
        if (isPreviewing) {
            this.stopCameraPreview();
        } else {
            this.startCameraPreview();
        }
    }
    
    /**
     * 更新预览图像
     */
    updatePreviewImage() {
        const previewImg = document.getElementById('preview');
        if (!previewImg) return;
        
        const updateImage = () => {
            if (this.isOnline) {
                previewImg.src = `/api/camera/preview?t=${Date.now()}`;
            }
        };
        
        // 立即更新一次
        updateImage();
        
        // 定期更新
        this.previewInterval = setInterval(updateImage, 200); // 5fps
    }
    
    /**
     * 更新相机曝光
     */
    async updateCameraExposure(exposure) {
        try {
            await fetch('/api/camera/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    exposure_us: exposure * 1000 // 转换为微秒
                })
            });
            
            document.getElementById('exposure-value').textContent = exposure;
        } catch (error) {
            console.error('[Camera] 更新曝光失败:', error);
        }
    }
    
    /**
     * 更新相机增益
     */
    async updateCameraGain(gain) {
        try {
            await fetch('/api/camera/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    analogue_gain: gain
                })
            });
            
            document.getElementById('gain-value').textContent = gain.toFixed(1);
        } catch (error) {
            console.error('[Camera] 更新增益失败:', error);
        }
    }
    
    /**
     * 调整相机亮度
     */
    adjustCameraBrightness(delta) {
        const gainSlider = document.getElementById('gain');
        if (gainSlider) {
            const currentGain = parseFloat(gainSlider.value);
            const newGain = Math.max(1.0, Math.min(16.0, currentGain + delta));
            gainSlider.value = newGain;
            this.updateCameraGain(newGain);
        }
    }
    
    /**
     * 切换相机缩放
     */
    toggleCameraZoom() {
        const previewImg = document.getElementById('preview');
        if (!previewImg) return;
        
        if (previewImg.style.objectFit === 'cover') {
            previewImg.style.objectFit = 'contain';
            this.showNotification('缩放模式: 完整显示', 'info');
        } else {
            previewImg.style.objectFit = 'cover';
            this.showNotification('缩放模式: 填充显示', 'info');
        }
    }
    
    /**
     * 显示相机信息
     */
    showCameraInfo() {
        // 显示相机详细信息的模态框
        this.showModal('相机信息', `
            <div class="camera-info">
                <p><strong>分辨率:</strong> 1920x1080</p>
                <p><strong>帧率:</strong> 30fps</p>
                <p><strong>传感器:</strong> IMX327</p>
                <p><strong>接口:</strong> MIPI CSI</p>
            </div>
        `);
    }
    
    /**
     * 开始极轴校准
     */
    async startPolarAlignment() {
        if (this.alignmentInProgress) return;
        
        try {
            this.alignmentInProgress = true;
            this.updateAlignmentUI(true);
            
            // 开始校准流程
            const response = await fetch('/api/alignment/start', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification('极轴校准已开始', 'success');
                this.startAlignmentProcess();
            } else {
                throw new Error('启动校准失败');
            }
            
        } catch (error) {
            console.error('[Alignment] 启动校准失败:', error);
            this.showNotification('启动极轴校准失败', 'error');
            this.alignmentInProgress = false;
            this.updateAlignmentUI(false);
        }
    }
    
    /**
     * 停止极轴校准
     */
    async stopPolarAlignment() {
        try {
            await fetch('/api/alignment/stop', {
                method: 'POST'
            });
            
            this.alignmentInProgress = false;
            this.updateAlignmentUI(false);
            this.showNotification('极轴校准已停止', 'info');
            
        } catch (error) {
            console.error('[Alignment] 停止校准失败:', error);
        }
    }
    
    /**
     * 开始校准过程
     */
    startAlignmentProcess() {
        const updateAlignment = async () => {
            if (!this.alignmentInProgress) return;
            
            try {
                const response = await fetch('/api/alignment/status');
                const status = await response.json();
                
                this.updateAlignmentStatus(status);
                
                // 继续更新
                setTimeout(updateAlignment, 1000);
                
            } catch (error) {
                console.error('[Alignment] 获取状态失败:', error);
                setTimeout(updateAlignment, 5000); // 重试间隔更长
            }
        };
        
        updateAlignment();
    }
    
    /**
     * 更新校准状态
     */
    updateAlignmentStatus(status) {
        document.getElementById('align-status').textContent = status.status || '校准中...';
        document.getElementById('az-error').textContent = status.azimuth_error ? 
            `${status.azimuth_error.toFixed(2)}′` : '--';
        document.getElementById('alt-error').textContent = status.altitude_error ? 
            `${status.altitude_error.toFixed(2)}′` : '--';
        
        // 更新状态颜色
        const statusElement = document.getElementById('align-status');
        statusElement.className = `status-${status.status || 'info'}`;
    }
    
    /**
     * 更新网络状态
     */
    updateNetworkStatus() {
        const statusElement = document.querySelector('.network-status');
        if (statusElement) {
            statusElement.className = `network-status ${this.isOnline ? 'online' : 'offline'}`;
            statusElement.textContent = this.isOnline ? '在线' : '离线';
        }
    }
    
    /**
     * 检查PWA安装提示
     */
    checkInstallPrompt() {
        // 检查是否支持PWA安装
        if ('serviceWorker' in navigator && 'PushManager' in window) {
            // 检查是否已经安装
            if (window.matchMedia('(display-mode: standalone)').matches) {
                console.log('[PWA] 已安装为PWA');
                return;
            }
            
            // 显示安装提示
            setTimeout(() => {
                this.showInstallPrompt();
            }, 5000);
        }
    }
    
    /**
     * 显示PWA安装提示
     */
    showInstallPrompt() {
        const prompt = document.querySelector('.install-prompt');
        if (prompt) {
            prompt.classList.add('show');
        }
    }
    
    /**
     * 设置PWA安装提示
     */
    setupInstallPrompt() {
        document.getElementById('install-app')?.addEventListener('click', () => {
            this.installPWA();
        });
        
        document.getElementById('dismiss-install')?.addEventListener('click', () => {
            this.dismissInstallPrompt();
        });
    }
    
    /**
     * 安装PWA
     */
    async installPWA() {
        if (this.deferredPrompt) {
            this.deferredPrompt.prompt();
            const { outcome } = await this.deferredPrompt.userChoice;
            
            if (outcome === 'accepted') {
                this.showNotification('PWA安装成功', 'success');
            }
            
            this.deferredPrompt = null;
            this.dismissInstallPrompt();
        }
    }
    
    /**
     * 关闭安装提示
     */
    dismissInstallPrompt() {
        const prompt = document.querySelector('.install-prompt');
        if (prompt) {
            prompt.classList.remove('show');
        }
    }
    
    /**
     * 显示通知
     */
    showNotification(message, type = 'info') {
        // 创建通知元素
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        // 添加到页面
        document.body.appendChild(notification);
        
        // 显示动画
        setTimeout(() => {
            notification.classList.add('show');
        }, 100);
        
        // 自动隐藏
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        }, 3000);
    }
    
    /**
     * 显示模态框
     */
    showModal(title, content) {
        // 创建模态框
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
        
        // 添加到页面
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
            document.body.removeChild(modal);
        }, 300);
    }
    
    /**
     * 更新按钮状态
     */
    updateButtonStates(isPreviewing) {
        const startBtn = document.getElementById('start-preview');
        const stopBtn = document.getElementById('stop-preview');
        
        if (startBtn) startBtn.disabled = isPreviewing;
        if (stopBtn) stopBtn.disabled = !isPreviewing;
    }
    
    /**
     * 更新校准UI状态
     */
    updateAlignmentUI(isActive) {
        const startBtn = document.getElementById('start-align');
        const stopBtn = document.getElementById('stop-align');
        
        if (startBtn) startBtn.disabled = isActive;
        if (stopBtn) stopBtn.disabled = !isActive;
    }
    
    /**
     * 更新参数显示
     */
    updateParameterDisplays() {
        // 同步滑块值和显示值
        const exposureSlider = document.getElementById('exposure');
        const gainSlider = document.getElementById('gain');
        
        if (exposureSlider) {
            exposureSlider.addEventListener('input', (e) => {
                document.getElementById('exposure-value').textContent = e.target.value;
            });
        }
        
        if (gainSlider) {
            gainSlider.addEventListener('input', (e) => {
                document.getElementById('gain-value').textContent = parseFloat(e.target.value).toFixed(1);
            });
        }
    }
    
    /**
     * 获取相机配置
     */
    async fetchCameraConfig() {
        try {
            const response = await fetch('/api/camera/config');
            return await response.json();
        } catch (error) {
            console.error('[Camera] 获取配置失败:', error);
            return null;
        }
    }
    
    /**
     * 更新相机UI
     */
    updateCameraUI(config) {
        if (!config) return;
        
        const exposureSlider = document.getElementById('exposure');
        const gainSlider = document.getElementById('gain');
        
        if (exposureSlider && config.exposure_us) {
            exposureSlider.value = config.exposure_us / 1000;
            document.getElementById('exposure-value').textContent = exposureSlider.value;
        }
        
        if (gainSlider && config.analogue_gain) {
            gainSlider.value = config.analogue_gain;
            document.getElementById('gain-value').textContent = config.analogue_gain.toFixed(1);
        }
    }
    
    /**
     * 显示更新通知
     */
    showUpdateNotification() {
        this.showModal('应用更新', `
            <p>发现新版本，是否立即更新？</p>
            <div class="modal-actions">
                <button class="btn btn-primary" onclick="window.location.reload()">立即更新</button>
                <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">稍后更新</button>
            </div>
        `);
    }
}

// 页面加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.ogscopeApp = new OGScopeApp();
});

// 监听PWA安装提示
let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    window.ogscopeApp.deferredPrompt = e;
});

// 监听PWA安装完成
window.addEventListener('appinstalled', () => {
    console.log('[PWA] 应用已安装');
    window.ogscopeApp.showNotification('PWA安装成功', 'success');
});