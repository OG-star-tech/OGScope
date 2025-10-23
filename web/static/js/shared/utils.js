/**
 * OGScope 通用工具函数
 * 提供常用的工具方法和辅助函数
 */

import { APP_CONFIG } from './constants.js';

/**
 * 工具函数集合
 */
export class Utils {
    /**
     * 延迟执行
     * @param {number} ms - 延迟毫秒数
     * @returns {Promise} Promise对象
     */
    static delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * 格式化时间
     * @param {number} seconds - 秒数
     * @returns {string} 格式化的时间字符串 (MM:SS)
     */
    static formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    /**
     * 格式化文件大小
     * @param {number} bytes - 字节数
     * @returns {string} 格式化的文件大小
     */
    static formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * 生成唯一ID
     * @returns {string} 唯一ID
     */
    static generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2);
    }

    /**
     * 防抖函数
     * @param {Function} func - 要防抖的函数
     * @param {number} wait - 等待时间
     * @returns {Function} 防抖后的函数
     */
    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * 节流函数
     * @param {Function} func - 要节流的函数
     * @param {number} limit - 时间限制
     * @returns {Function} 节流后的函数
     */
    static throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }

    /**
     * 深拷贝对象
     * @param {Object} obj - 要拷贝的对象
     * @returns {Object} 拷贝后的对象
     */
    static deepClone(obj) {
        if (obj === null || typeof obj !== 'object') return obj;
        if (obj instanceof Date) return new Date(obj.getTime());
        if (obj instanceof Array) return obj.map(item => this.deepClone(item));
        if (typeof obj === 'object') {
            const clonedObj = {};
            for (const key in obj) {
                if (obj.hasOwnProperty(key)) {
                    clonedObj[key] = this.deepClone(obj[key]);
                }
            }
            return clonedObj;
        }
    }

    /**
     * 检查是否为移动设备
     * @returns {boolean} 是否为移动设备
     */
    static isMobile() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    }

    /**
     * 检查网络状态
     * @returns {boolean} 是否在线
     */
    static isOnline() {
        return navigator.onLine;
    }

    /**
     * 显示通知
     * @param {string} message - 通知消息
     * @param {string} type - 通知类型 (success, error, warning, info)
     * @param {number} duration - 显示时长（毫秒）
     */
    static showNotification(message, type = 'info', duration = 3000) {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        // 添加到通知容器
        let container = document.getElementById('notifications');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notifications';
            container.className = 'notifications';
            document.body.appendChild(container);
        }
        
        container.appendChild(notification);
        
        // 显示动画
        setTimeout(() => notification.classList.add('show'), 100);
        
        // 自动隐藏
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => container.removeChild(notification), 300);
        }, duration);
    }

    /**
     * 保存数据到本地存储
     * @param {string} key - 存储键
     * @param {Object} data - 要存储的数据
     */
    static saveToStorage(key, data) {
        try {
            localStorage.setItem(key, JSON.stringify(data));
        } catch (error) {
            console.error('[Utils] 保存到本地存储失败:', error);
        }
    }

    /**
     * 从本地存储读取数据
     * @param {string} key - 存储键
     * @param {Object} defaultValue - 默认值
     * @returns {Object} 读取的数据
     */
    static loadFromStorage(key, defaultValue = null) {
        try {
            const data = localStorage.getItem(key);
            return data ? JSON.parse(data) : defaultValue;
        } catch (error) {
            console.error('[Utils] 从本地存储读取失败:', error);
            return defaultValue;
        }
    }

    /**
     * 计算两点之间的距离
     * @param {Object} point1 - 第一个点 {x, y}
     * @param {Object} point2 - 第二个点 {x, y}
     * @returns {number} 距离
     */
    static calculateDistance(point1, point2) {
        const dx = point2.x - point1.x;
        const dy = point2.y - point1.y;
        return Math.sqrt(dx * dx + dy * dy);
    }

    /**
     * 角度转弧度
     * @param {number} degrees - 角度
     * @returns {number} 弧度
     */
    static degreesToRadians(degrees) {
        return degrees * (Math.PI / 180);
    }

    /**
     * 弧度转角度
     * @param {number} radians - 弧度
     * @returns {number} 角度
     */
    static radiansToDegrees(radians) {
        return radians * (180 / Math.PI);
    }

    /**
     * 限制数值范围
     * @param {number} value - 要限制的值
     * @param {number} min - 最小值
     * @param {number} max - 最大值
     * @returns {number} 限制后的值
     */
    static clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    /**
     * 线性插值
     * @param {number} start - 起始值
     * @param {number} end - 结束值
     * @param {number} factor - 插值因子 (0-1)
     * @returns {number} 插值结果
     */
    static lerp(start, end, factor) {
        return start + (end - start) * factor;
    }
}

/**
 * 事件发射器
 */
export class EventEmitter {
    constructor() {
        this.events = {};
    }

    /**
     * 监听事件
     * @param {string} event - 事件名
     * @param {Function} callback - 回调函数
     */
    on(event, callback) {
        if (!this.events[event]) {
            this.events[event] = [];
        }
        this.events[event].push(callback);
    }

    /**
     * 移除事件监听
     * @param {string} event - 事件名
     * @param {Function} callback - 回调函数
     */
    off(event, callback) {
        if (!this.events[event]) return;
        this.events[event] = this.events[event].filter(cb => cb !== callback);
    }

    /**
     * 触发事件
     * @param {string} event - 事件名
     * @param {...any} args - 事件参数
     */
    emit(event, ...args) {
        if (!this.events[event]) return;
        this.events[event].forEach(callback => {
            try {
                callback(...args);
            } catch (error) {
                console.error(`[EventEmitter] 事件 ${event} 回调执行失败:`, error);
            }
        });
    }

    /**
     * 移除所有事件监听
     * @param {string} event - 事件名（可选）
     */
    removeAllListeners(event) {
        if (event) {
            delete this.events[event];
        } else {
            this.events = {};
        }
    }
}
