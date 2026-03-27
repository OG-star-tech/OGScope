/**
 * OGScope PWA功能模块 / OGScope PWA function module
 * 处理PWA相关的所有功能 / Handles all PWA related functions
 */

import { Utils, EventEmitter } from '../shared/utils.js';
import { EVENTS } from '../shared/constants.js';

export class PWAManager extends EventEmitter {
    constructor() {
        super();
        this.deferredPrompt = null;
        this.isInstalled = false;
        this.init();
    }

    /**
     * 初始化PWA管理器 / Initialize PWA Manager
     */
    init() {
        this.setupEventListeners();
        this.checkInstallationStatus();
        this.registerServiceWorker();
    }

    /**
     * 设置事件监听器 / Set event listener
     */
    setupEventListeners() {
        // PWA安装提示事件 / PWA installation prompt event
        window.addEventListener('beforeinstallprompt', (e) => {
            console.log('[PWA] 安装提示事件触发');
            e.preventDefault();
            this.deferredPrompt = e;
            this.emit(EVENTS.PWA_INSTALL_PROMPT, e);
        });

        // PWA安装完成事件 / PWA installation completion event
        window.addEventListener('appinstalled', () => {
            console.log('[PWA] 应用已安装');
            this.isInstalled = true;
            this.deferredPrompt = null;
            this.emit(EVENTS.PWA_INSTALLED);
        });

        // Service Worker更新事件 / Service Worker update event
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.addEventListener('controllerchange', () => {
                console.log('[PWA] Service Worker已更新');
                this.emit('pwa:sw:updated');
            });
        }
    }

    /**
     * 注册Service Worker / Register Service Worker
     * @returns {Promise<boolean>} 是否注册成功 / Whether the registration is successful
     */
    async registerServiceWorker() {
        if (!('serviceWorker' in navigator)) {
            console.log('[PWA] 浏览器不支持Service Worker');
            return false;
        }

        try {
            console.log('[PWA] 注册Service Worker...');
            const registration = await navigator.serviceWorker.register('/static/sw.js');
            
            console.log('[PWA] Service Worker注册成功:', registration);
            
            // 检查更新 / Check for updates
            registration.addEventListener('updatefound', () => {
                const newWorker = registration.installing;
                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        console.log('[PWA] 发现新版本，准备更新');
                        this.emit('pwa:sw:update-available');
                    }
                });
            });
            
            return true;
        } catch (error) {
            console.error('[PWA] Service Worker注册失败:', error);
            return false;
        }
    }

    /**
     * 检查安装状态 / Check installation status
     */
    checkInstallationStatus() {
        // 检查是否在独立模式下运行（已安装） / Check if running in standalone mode (already installed)
        if (window.matchMedia('(display-mode: standalone)').matches) {
            this.isInstalled = true;
            console.log('[PWA] 应用已在独立模式下运行');
        }
        
        // 检查是否在iOS Safari中添加到主屏幕 / Check if added to home screen in iOS Safari
        if (window.navigator.standalone === true) {
            this.isInstalled = true;
            console.log('[PWA] 应用已在iOS主屏幕中');
        }
    }

    /**
     * 显示安装提示 / Show installation prompts
     * @returns {boolean} 是否可以显示提示 / Whether prompts can be displayed
     */
    showInstallPrompt() {
        if (!this.deferredPrompt) {
            console.log('[PWA] 没有可用的安装提示');
            return false;
        }

        if (this.isInstalled) {
            console.log('[PWA] 应用已安装，无需显示提示');
            return false;
        }

        // 触发安装提示显示事件 / Trigger the installation prompt display event
        this.emit('pwa:install:show');
        return true;
    }

    /**
     * 安装应用 / Install app
     * @returns {Promise<boolean>} 是否安装成功 / Whether the installation was successful
     */
    async installApp() {
        if (!this.deferredPrompt) {
            console.log('[PWA] 没有可用的安装提示');
            return false;
        }

        try {
            console.log('[PWA] 开始安装应用...');
            
            // 显示安装提示 / Show installation prompts
            this.deferredPrompt.prompt();
            
            // 等待用户响应 / Wait for user response
            const { outcome } = await this.deferredPrompt.userChoice;
            
            console.log('[PWA] 用户选择:', outcome);
            
            if (outcome === 'accepted') {
                console.log('[PWA] 用户接受安装');
                this.emit('pwa:install:accepted');
            } else {
                console.log('[PWA] 用户拒绝安装');
                this.emit('pwa:install:rejected');
            }
            
            // 清除提示 / Clear prompt
            this.deferredPrompt = null;
            return outcome === 'accepted';
        } catch (error) {
            console.error('[PWA] 安装过程出错:', error);
            return false;
        }
    }

    /**
     * 检查是否可以安装 / Check if it can be installed
     * @returns {boolean} 是否可以安装 / Whether it can be installed
     */
    canInstall() {
        return this.deferredPrompt !== null && !this.isInstalled;
    }

    /**
     * 检查是否已安装 / Check if it is installed
     * @returns {boolean} 是否已安装 / Whether it is installed
     */
    isAppInstalled() {
        return this.isInstalled;
    }

    /**
     * 获取PWA信息 / Get PWA information
     * @returns {Object} PWA信息 / PWA information
     */
    getPWAInfo() {
        return {
            canInstall: this.canInstall(),
            isInstalled: this.isInstalled,
            hasServiceWorker: 'serviceWorker' in navigator,
            isStandalone: window.matchMedia('(display-mode: standalone)').matches,
            isIOSStandalone: window.navigator.standalone === true
        };
    }

    /**
     * 更新Service Worker / Update Service Worker
     * @returns {Promise<boolean>} 是否更新成功 / Whether the update is successful
     */
    async updateServiceWorker() {
        if (!('serviceWorker' in navigator)) {
            return false;
        }

        try {
            const registration = await navigator.serviceWorker.getRegistration();
            if (registration) {
                await registration.update();
                console.log('[PWA] Service Worker更新完成');
                return true;
            }
            return false;
        } catch (error) {
            console.error('[PWA] Service Worker更新失败:', error);
            return false;
        }
    }

    /**
     * 检查网络状态 / Check network status
     * @returns {boolean} 是否在线 / whether online
     */
    isOnline() {
        return Utils.isOnline();
    }

    /**
     * 添加离线事件监听 / Add offline event listening
     */
    setupOfflineHandling() {
        window.addEventListener('online', () => {
            console.log('[PWA] 网络已连接');
            this.emit('pwa:network:online');
        });

        window.addEventListener('offline', () => {
            console.log('[PWA] 网络已断开');
            this.emit('pwa:network:offline');
        });
    }

    /**
     * 获取应用版本信息 / Get application version information
     * @returns {Object} 版本信息 / version information
     */
    getVersionInfo() {
        return {
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            cookieEnabled: navigator.cookieEnabled,
            onLine: navigator.onLine,
            serviceWorkerSupported: 'serviceWorker' in navigator,
            pushManagerSupported: 'PushManager' in window,
            notificationSupported: 'Notification' in window
        };
    }

    /**
     * 请求通知权限 / Request notification permission
     * @returns {Promise<boolean>} 是否获得权限 / whether to obtain permission
     */
    async requestNotificationPermission() {
        if (!('Notification' in window)) {
            console.log('[PWA] 浏览器不支持通知');
            return false;
        }

        if (Notification.permission === 'granted') {
            return true;
        }

        if (Notification.permission === 'denied') {
            console.log('[PWA] 通知权限已被拒绝');
            return false;
        }

        try {
            const permission = await Notification.requestPermission();
            return permission === 'granted';
        } catch (error) {
            console.error('[PWA] 请求通知权限失败:', error);
            return false;
        }
    }

    /**
     * 显示通知 / Show notification
     * @param {string} title - 通知标题 / notification title
     * @param {Object} options - 通知选项 / notification options
     * @returns {Notification} 通知对象 / notification object
     */
    showNotification(title, options = {}) {
        if (!('Notification' in window) || Notification.permission !== 'granted') {
            console.log('[PWA] 无法显示通知');
            return null;
        }

        const defaultOptions = {
            icon: '/static/images/icon-192x192.png',
            badge: '/static/images/icon-72x72.png',
            tag: 'ogscope-notification',
            requireInteraction: false,
            ...options
        };

        return new Notification(title, defaultOptions);
    }

    /**
     * 销毁PWA管理器 / Destroy PWA Manager
     */
    destroy() {
        this.deferredPrompt = null;
        this.removeAllListeners();
    }
}
