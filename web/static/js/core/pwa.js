/**
 * OGScope PWA功能模块
 * 处理PWA相关的所有功能
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
     * 初始化PWA管理器
     */
    init() {
        this.setupEventListeners();
        this.checkInstallationStatus();
        this.registerServiceWorker();
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // PWA安装提示事件
        window.addEventListener('beforeinstallprompt', (e) => {
            console.log('[PWA] 安装提示事件触发');
            e.preventDefault();
            this.deferredPrompt = e;
            this.emit(EVENTS.PWA_INSTALL_PROMPT, e);
        });

        // PWA安装完成事件
        window.addEventListener('appinstalled', () => {
            console.log('[PWA] 应用已安装');
            this.isInstalled = true;
            this.deferredPrompt = null;
            this.emit(EVENTS.PWA_INSTALLED);
        });

        // Service Worker更新事件
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.addEventListener('controllerchange', () => {
                console.log('[PWA] Service Worker已更新');
                this.emit('pwa:sw:updated');
            });
        }
    }

    /**
     * 注册Service Worker
     * @returns {Promise<boolean>} 是否注册成功
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
            
            // 检查更新
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
     * 检查安装状态
     */
    checkInstallationStatus() {
        // 检查是否在独立模式下运行（已安装）
        if (window.matchMedia('(display-mode: standalone)').matches) {
            this.isInstalled = true;
            console.log('[PWA] 应用已在独立模式下运行');
        }
        
        // 检查是否在iOS Safari中添加到主屏幕
        if (window.navigator.standalone === true) {
            this.isInstalled = true;
            console.log('[PWA] 应用已在iOS主屏幕中');
        }
    }

    /**
     * 显示安装提示
     * @returns {boolean} 是否可以显示提示
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

        // 触发安装提示显示事件
        this.emit('pwa:install:show');
        return true;
    }

    /**
     * 安装应用
     * @returns {Promise<boolean>} 是否安装成功
     */
    async installApp() {
        if (!this.deferredPrompt) {
            console.log('[PWA] 没有可用的安装提示');
            return false;
        }

        try {
            console.log('[PWA] 开始安装应用...');
            
            // 显示安装提示
            this.deferredPrompt.prompt();
            
            // 等待用户响应
            const { outcome } = await this.deferredPrompt.userChoice;
            
            console.log('[PWA] 用户选择:', outcome);
            
            if (outcome === 'accepted') {
                console.log('[PWA] 用户接受安装');
                this.emit('pwa:install:accepted');
            } else {
                console.log('[PWA] 用户拒绝安装');
                this.emit('pwa:install:rejected');
            }
            
            // 清除提示
            this.deferredPrompt = null;
            return outcome === 'accepted';
        } catch (error) {
            console.error('[PWA] 安装过程出错:', error);
            return false;
        }
    }

    /**
     * 检查是否可以安装
     * @returns {boolean} 是否可以安装
     */
    canInstall() {
        return this.deferredPrompt !== null && !this.isInstalled;
    }

    /**
     * 检查是否已安装
     * @returns {boolean} 是否已安装
     */
    isAppInstalled() {
        return this.isInstalled;
    }

    /**
     * 获取PWA信息
     * @returns {Object} PWA信息
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
     * 更新Service Worker
     * @returns {Promise<boolean>} 是否更新成功
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
     * 检查网络状态
     * @returns {boolean} 是否在线
     */
    isOnline() {
        return Utils.isOnline();
    }

    /**
     * 添加离线事件监听
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
     * 获取应用版本信息
     * @returns {Object} 版本信息
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
     * 请求通知权限
     * @returns {Promise<boolean>} 是否获得权限
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
     * 显示通知
     * @param {string} title - 通知标题
     * @param {Object} options - 通知选项
     * @returns {Notification} 通知对象
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
     * 销毁PWA管理器
     */
    destroy() {
        this.deferredPrompt = null;
        this.removeAllListeners();
    }
}
