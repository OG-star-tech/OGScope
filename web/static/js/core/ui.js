/**
 * OGScope UI组件模块
 * 处理用户界面相关的所有功能
 */

import { Utils, EventEmitter } from '../shared/utils.js';
import { APP_CONFIG, CSS_CLASSES, EVENTS } from '../shared/constants.js';

export class UIController extends EventEmitter {
    constructor() {
        super();
        this.elements = {};
        this.isZoomed = false;
        this.isLoading = false;
        this.init();
    }

    /**
     * 初始化UI控制器
     */
    init() {
        this.cacheElements();
        this.setupEventListeners();
        this.initUI();
    }

    /**
     * 缓存DOM元素
     */
    cacheElements() {
        this.elements = {
            // 主要容器
            app: document.getElementById('app'),
            videoContainer: document.getElementById('video-container'),
            videoStream: document.getElementById('mjpeg-stream'),
            videoOverlay: document.getElementById('video-overlay'),
            
            // 控制按钮
            startStreamBtn: document.getElementById('start-stream'),
            stopStreamBtn: document.getElementById('stop-stream'),
            zoomToggleBtn: document.getElementById('zoom-toggle'),
            startAlignmentBtn: document.getElementById('start-alignment'),
            stopAlignmentBtn: document.getElementById('stop-alignment'),
            
            // 状态显示
            modeDisplay: document.getElementById('mode-display'),
            statusDisplay: document.getElementById('status-display'),
            progressDisplay: document.getElementById('progress-display'),
            
            // 校准指标
            azimuthError: document.getElementById('azimuth-error'),
            altitudeError: document.getElementById('altitude-error'),
            precisionLevel: document.getElementById('precision-level'),
            
            // 加载屏幕
            loadingScreen: document.getElementById('loading-screen'),
            loadingProgress: document.getElementById('loading-progress'),
            loadingText: document.getElementById('loading-text'),
            
            // 网络状态
            networkStatus: document.getElementById('network-status'),
            
            // PWA安装提示
            installPrompt: document.getElementById('install-prompt'),
            installBtn: document.getElementById('install-app'),
            dismissInstallBtn: document.getElementById('dismiss-install'),
            
            // 十字准星和覆盖层
            crosshair: document.getElementById('crosshair'),
            starMarkers: document.getElementById('star-markers'),
            polarTarget: document.getElementById('polar-target'),
            alignmentRing: document.getElementById('alignment-ring')
        };
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 视频控制按钮
        if (this.elements.startStreamBtn) {
            this.elements.startStreamBtn.addEventListener('click', () => {
                this.emit('ui:stream:start');
            });
        }
        
        if (this.elements.stopStreamBtn) {
            this.elements.stopStreamBtn.addEventListener('click', () => {
                this.emit('ui:stream:stop');
            });
        }
        
        if (this.elements.zoomToggleBtn) {
            this.elements.zoomToggleBtn.addEventListener('click', () => {
                this.toggleZoom();
            });
        }
        
        // 校准控制按钮
        if (this.elements.startAlignmentBtn) {
            this.elements.startAlignmentBtn.addEventListener('click', () => {
                this.emit('ui:alignment:start');
            });
        }
        
        if (this.elements.stopAlignmentBtn) {
            this.elements.stopAlignmentBtn.addEventListener('click', () => {
                this.emit('ui:alignment:stop');
            });
        }
        
        // PWA安装按钮
        if (this.elements.installBtn) {
            this.elements.installBtn.addEventListener('click', () => {
                this.emit('ui:pwa:install');
            });
        }
        
        if (this.elements.dismissInstallBtn) {
            this.elements.dismissInstallBtn.addEventListener('click', () => {
                this.hideInstallPrompt();
            });
        }
        
        // 网络状态监听
        window.addEventListener('online', () => {
            this.updateNetworkStatus(true);
        });
        
        window.addEventListener('offline', () => {
            this.updateNetworkStatus(false);
        });
        
        // 窗口大小变化
        window.addEventListener('resize', Utils.debounce(() => {
            this.handleResize();
        }, 250));
    }

    /**
     * 初始化UI
     */
    initUI() {
        // 设置初始状态
        this.updateModeDisplay('检测中...');
        this.updateStatusDisplay('系统启动中...');
        this.updateProgressDisplay(0);
        this.updateNetworkStatus(Utils.isOnline());
        
        // 初始化校准指标
        this.updateAlignmentMetrics(null, null, null);
        
        // 设置按钮状态
        this.updateButtonStates();
        
        this.emit(EVENTS.UI_READY);
    }

    /**
     * 显示加载屏幕
     */
    showLoadingScreen() {
        if (this.elements.loadingScreen) {
            this.elements.loadingScreen.classList.remove(CSS_CLASSES.HIDDEN);
            this.isLoading = true;
        }
    }

    /**
     * 隐藏加载屏幕
     */
    hideLoadingScreen() {
        if (this.elements.loadingScreen) {
            setTimeout(() => {
                this.elements.loadingScreen.classList.add(CSS_CLASSES.HIDDEN);
                this.isLoading = false;
            }, 500);
        }
    }

    /**
     * 模拟加载过程
     * @returns {Promise} 加载完成Promise
     */
    async simulateLoading() {
        const steps = APP_CONFIG.UI.LOADING_STEPS;
        
        for (const step of steps) {
            await Utils.delay(800); // 每步延迟800ms
            
            if (this.elements.loadingProgress) {
                this.elements.loadingProgress.style.width = `${step.progress}%`;
            }
            
            if (this.elements.loadingText) {
                this.elements.loadingText.textContent = step.text;
            }
        }
        
        await Utils.delay(500); // 最后延迟500ms
    }

    /**
     * 更新模式显示
     * @param {string} mode - 模式文本
     */
    updateModeDisplay(mode) {
        if (this.elements.modeDisplay) {
            this.elements.modeDisplay.textContent = mode;
        }
    }

    /**
     * 更新状态显示
     * @param {string} status - 状态文本
     */
    updateStatusDisplay(status) {
        if (this.elements.statusDisplay) {
            this.elements.statusDisplay.textContent = status;
        }
    }

    /**
     * 更新进度显示
     * @param {number} progress - 进度百分比
     */
    updateProgressDisplay(progress) {
        if (this.elements.progressDisplay) {
            this.elements.progressDisplay.textContent = `${Math.round(progress)}%`;
        }
    }

    /**
     * 更新校准指标
     * @param {number} azimuthError - 方位误差
     * @param {number} altitudeError - 高度误差
     * @param {number} precision - 精度
     */
    updateAlignmentMetrics(azimuthError, altitudeError, precision) {
        if (this.elements.azimuthError) {
            this.elements.azimuthError.textContent = this.formatError(azimuthError);
        }
        
        if (this.elements.altitudeError) {
            this.elements.altitudeError.textContent = this.formatError(altitudeError);
        }
        
        if (this.elements.precisionLevel) {
            this.elements.precisionLevel.textContent = this.getPrecisionLevel(precision);
        }
    }

    /**
     * 格式化误差显示
     * @param {number} error - 误差值
     * @returns {string} 格式化的误差
     */
    formatError(error) {
        if (error === null || error === undefined) {
            return '--';
        }
        return Math.abs(error * 60).toFixed(1);
    }

    /**
     * 获取精度等级
     * @param {number} precision - 精度值
     * @returns {string} 精度等级
     */
    getPrecisionLevel(precision) {
        if (precision === null || precision === undefined) {
            return '--';
        }
        
        if (precision <= 0.1) return '优秀';
        if (precision <= 0.2) return '良好';
        if (precision <= 0.5) return '一般';
        return '需改进';
    }

    /**
     * 更新按钮状态
     * @param {Object} states - 按钮状态对象
     */
    updateButtonStates(states = {}) {
        const defaultStates = {
            streamRunning: false,
            alignmentRunning: false,
            zoomed: false
        };
        
        const buttonStates = { ...defaultStates, ...states };
        
        // 视频流按钮
        if (this.elements.startStreamBtn) {
            this.elements.startStreamBtn.disabled = buttonStates.streamRunning;
        }
        
        if (this.elements.stopStreamBtn) {
            this.elements.stopStreamBtn.disabled = !buttonStates.streamRunning;
        }
        
        // 校准按钮
        if (this.elements.startAlignmentBtn) {
            this.elements.startAlignmentBtn.disabled = buttonStates.alignmentRunning;
        }
        
        if (this.elements.stopAlignmentBtn) {
            this.elements.stopAlignmentBtn.disabled = !buttonStates.alignmentRunning;
        }
        
        // 缩放按钮
        if (this.elements.zoomToggleBtn) {
            this.elements.zoomToggleBtn.classList.toggle('active', buttonStates.zoomed);
        }
    }

    /**
     * 切换缩放状态
     */
    toggleZoom() {
        this.isZoomed = !this.isZoomed;
        
        if (this.elements.videoContainer) {
            this.elements.videoContainer.classList.toggle('zoomed', this.isZoomed);
        }
        
        this.updateButtonStates({ zoomed: this.isZoomed });
        this.emit('ui:zoom:toggle', this.isZoomed);
    }

    /**
     * 更新网络状态显示
     * @param {boolean} isOnline - 是否在线
     */
    updateNetworkStatus(isOnline) {
        if (this.elements.networkStatus) {
            this.elements.networkStatus.classList.toggle(CSS_CLASSES.STATUS_ONLINE, isOnline);
            this.elements.networkStatus.classList.toggle(CSS_CLASSES.STATUS_OFFLINE, !isOnline);
            
            const statusText = this.elements.networkStatus.querySelector('.status-text');
            if (statusText) {
                statusText.textContent = isOnline ? '在线' : '离线';
            }
        }
    }

    /**
     * 显示PWA安装提示
     */
    showInstallPrompt() {
        if (this.elements.installPrompt) {
            this.elements.installPrompt.classList.remove(CSS_CLASSES.HIDDEN);
        }
    }

    /**
     * 隐藏PWA安装提示
     */
    hideInstallPrompt() {
        if (this.elements.installPrompt) {
            this.elements.installPrompt.classList.add(CSS_CLASSES.HIDDEN);
        }
    }

    /**
     * 处理窗口大小变化
     */
    handleResize() {
        // 重新计算布局
        this.updateLayout();
        
        // 触发resize事件
        this.emit('ui:resize', {
            width: window.innerWidth,
            height: window.innerHeight
        });
    }

    /**
     * 更新布局
     */
    updateLayout() {
        // 根据屏幕方向调整布局
        const isLandscape = window.innerWidth > window.innerHeight;
        
        if (this.elements.app) {
            this.elements.app.classList.toggle('landscape', isLandscape);
            this.elements.app.classList.toggle('portrait', !isLandscape);
        }
    }

    /**
     * 显示通知
     * @param {string} message - 通知消息
     * @param {string} type - 通知类型
     * @param {number} duration - 显示时长
     */
    showNotification(message, type = 'info', duration = 3000) {
        Utils.showNotification(message, type, duration);
    }

    /**
     * 显示错误消息
     * @param {string} message - 错误消息
     */
    showError(message) {
        this.showNotification(message, 'error', 5000);
    }

    /**
     * 显示成功消息
     * @param {string} message - 成功消息
     */
    showSuccess(message) {
        this.showNotification(message, 'success', 3000);
    }

    /**
     * 显示警告消息
     * @param {string} message - 警告消息
     */
    showWarning(message) {
        this.showNotification(message, 'warning', 4000);
    }

    /**
     * 获取元素引用
     * @param {string} name - 元素名称
     * @returns {HTMLElement} DOM元素
     */
    getElement(name) {
        return this.elements[name];
    }

    /**
     * 销毁UI控制器
     */
    destroy() {
        this.removeAllListeners();
        this.elements = {};
    }
}
