/**
 * OGScope 主应用入口
 * 革命性电子极轴镜 - 横屏全屏应用
 * 支持MJPEG视频流、星点识别、极轴校准、PWA功能
 */

import { CameraController } from './camera.js';
import { AlignmentController } from './alignment.js';
import { UIController } from './ui.js';
import { ParticleSystem } from './particles.js';
import { PWAManager } from './pwa.js';
import { Utils } from '../shared/utils.js';
import { APP_CONFIG, EVENTS } from '../shared/constants.js';

export class OGScopeApp {
    constructor() {
        this.isInitialized = false;
        this.modules = {};
        this.init();
    }

    /**
     * 初始化应用
     */
    async init() {
        try {
            console.log('[OGScope] 初始化革命性电子极轴镜...');
            
            // 显示加载屏幕
            this.showLoadingScreen();
            
            // 初始化各个模块
            await this.initializeModules();
            
            // 设置模块间通信
            this.setupModuleCommunication();
            
            // 模拟加载过程
            await this.simulateLoading();
            
            // 隐藏加载屏幕
            this.hideLoadingScreen();
            
            this.isInitialized = true;
            console.log('[OGScope] 初始化完成');
            
        } catch (error) {
            console.error('[OGScope] 初始化失败:', error);
            this.handleInitializationError(error);
        }
    }

    /**
     * 初始化各个模块
     */
    async initializeModules() {
        console.log('[OGScope] 初始化模块...');
        
        // 初始化UI控制器
        this.modules.ui = new UIController();
        
        // 初始化相机控制器
        this.modules.camera = new CameraController();
        
        // 初始化校准控制器
        this.modules.alignment = new AlignmentController();
        
        // 初始化粒子系统
        this.modules.particles = new ParticleSystem();
        
        // 初始化PWA管理器
        this.modules.pwa = new PWAManager();
        
        console.log('[OGScope] 模块初始化完成');
    }

    /**
     * 设置模块间通信
     */
    setupModuleCommunication() {
        console.log('[OGScope] 设置模块间通信...');
        
        // UI事件处理
        this.modules.ui.on('ui:stream:start', () => {
            this.modules.camera.startStream();
        });
        
        this.modules.ui.on('ui:stream:stop', () => {
            this.modules.camera.stopStream();
        });
        
        this.modules.ui.on('ui:alignment:start', () => {
            this.modules.alignment.startAlignment();
        });
        
        this.modules.ui.on('ui:alignment:stop', () => {
            this.modules.alignment.stopAlignment();
        });
        
        this.modules.ui.on('ui:pwa:install', () => {
            this.modules.pwa.installApp();
        });
        
        // 相机事件处理
        this.modules.camera.on(EVENTS.CAMERA_STREAM_START, () => {
            this.modules.ui.updateButtonStates({ streamRunning: true });
            this.modules.ui.updateStatusDisplay('视频流运行中');
            this.modules.ui.showSuccess('视频流启动成功');
        });
        
        this.modules.camera.on(EVENTS.CAMERA_STREAM_STOP, () => {
            this.modules.ui.updateButtonStates({ streamRunning: false });
            this.modules.ui.updateStatusDisplay('视频流已停止');
        });
        
        this.modules.camera.on(EVENTS.CAMERA_STREAM_ERROR, (error) => {
            this.modules.ui.updateButtonStates({ streamRunning: false });
            this.modules.ui.updateStatusDisplay('视频流错误');
            this.modules.ui.showError('视频流启动失败');
        });
        
        // 校准事件处理
        this.modules.alignment.on(EVENTS.ALIGNMENT_START, () => {
            this.modules.ui.updateButtonStates({ alignmentRunning: true });
            this.modules.ui.updateStatusDisplay('校准进行中...');
            this.modules.ui.showSuccess('校准已开始');
        });
        
        this.modules.alignment.on(EVENTS.ALIGNMENT_STOP, () => {
            this.modules.ui.updateButtonStates({ alignmentRunning: false });
            this.modules.ui.updateStatusDisplay('校准已停止');
        });
        
        this.modules.alignment.on(EVENTS.ALIGNMENT_PROGRESS, (data) => {
            this.modules.ui.updateProgressDisplay(data.progress);
            this.modules.ui.updateAlignmentMetrics(
                data.result.azimuthError,
                data.result.altitudeError,
                data.result.precision
            );
        });
        
        this.modules.alignment.on(EVENTS.ALIGNMENT_COMPLETE, (result) => {
            this.modules.ui.updateButtonStates({ alignmentRunning: false });
            this.modules.ui.updateStatusDisplay('校准完成');
            this.modules.ui.updateProgressDisplay(100);
            this.modules.ui.showSuccess('极轴校准完成！');
        });
        
        // PWA事件处理
        this.modules.pwa.on(EVENTS.PWA_INSTALL_PROMPT, () => {
            this.modules.ui.showInstallPrompt();
        });
        
        this.modules.pwa.on(EVENTS.PWA_INSTALLED, () => {
            this.modules.ui.hideInstallPrompt();
            this.modules.ui.showSuccess('应用已安装到主屏幕');
        });
        
        // 网络状态处理
        this.modules.pwa.on('pwa:network:online', () => {
            this.modules.ui.updateNetworkStatus(true);
            this.modules.ui.showSuccess('网络连接已恢复');
        });
        
        this.modules.pwa.on('pwa:network:offline', () => {
            this.modules.ui.updateNetworkStatus(false);
            this.modules.ui.showWarning('网络连接已断开');
        });
        
        console.log('[OGScope] 模块间通信设置完成');
    }

    /**
     * 显示加载屏幕
     */
    showLoadingScreen() {
        this.modules.ui?.showLoadingScreen();
    }

    /**
     * 隐藏加载屏幕
     */
    hideLoadingScreen() {
        this.modules.ui?.hideLoadingScreen();
    }

    /**
     * 模拟加载过程
     */
    async simulateLoading() {
        if (this.modules.ui) {
            await this.modules.ui.simulateLoading();
        } else {
            // 备用加载过程
            const steps = APP_CONFIG.UI.LOADING_STEPS;
            for (const step of steps) {
                await Utils.delay(800);
                console.log(`[OGScope] ${step.text} (${step.progress}%)`);
            }
            await Utils.delay(500);
        }
    }

    /**
     * 处理初始化错误
     * @param {Error} error - 错误对象
     */
    handleInitializationError(error) {
        console.error('[OGScope] 初始化错误:', error);
        
        // 显示错误信息
        if (this.modules.ui) {
            this.modules.ui.showError('系统初始化失败，请刷新页面重试');
        } else {
            alert('系统初始化失败，请刷新页面重试');
        }
    }

    /**
     * 获取应用状态
     * @returns {Object} 应用状态
     */
    getStatus() {
        return {
            initialized: this.isInitialized,
            camera: this.modules.camera?.getStatus() || {},
            alignment: this.modules.alignment?.getProgress() || {},
            pwa: this.modules.pwa?.getPWAInfo() || {},
            particles: this.modules.particles?.getParticleCount() || 0
        };
    }

    /**
     * 销毁应用
     */
    destroy() {
        console.log('[OGScope] 销毁应用...');
        
        // 销毁各个模块
        Object.values(this.modules).forEach(module => {
            if (module && typeof module.destroy === 'function') {
                module.destroy();
            }
        });
        
        this.modules = {};
        this.isInitialized = false;
        
        console.log('[OGScope] 应用已销毁');
    }
}

// 全局应用实例
let appInstance = null;

/**
 * 初始化应用
 */
export function initializeApp() {
    if (!appInstance) {
        appInstance = new OGScopeApp();
    }
    return appInstance;
}

/**
 * 获取应用实例
 */
export function getApp() {
    return appInstance;
}

// 页面加载完成后自动初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}
