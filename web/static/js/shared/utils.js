/* OGScope - 工具函数 */

/**
 * 格式化时间显示
 * @param {number} seconds - 秒数
 * @returns {string} 格式化后的时间字符串
 */
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 10);
    return mins > 0 ? `${mins}:${secs.toString().padStart(2, '0')}.${ms}` : `${secs}.${ms}s`;
}

/**
 * 防抖函数
 * @param {Function} func - 要防抖的函数
 * @param {number} wait - 等待时间
 * @returns {Function} 防抖后的函数
 */
function debounce(func, wait) {
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
function throttle(func, limit) {
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
 * 生成随机数
 * @param {number} min - 最小值
 * @param {number} max - 最大值
 * @returns {number} 随机数
 */
function random(min, max) {
    return Math.random() * (max - min) + min;
}

/**
 * 生成随机整数
 * @param {number} min - 最小值
 * @param {number} max - 最大值
 * @returns {number} 随机整数
 */
function randomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * 限制数值范围
 * @param {number} value - 数值
 * @param {number} min - 最小值
 * @param {number} max - 最大值
 * @returns {number} 限制后的数值
 */
function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

/**
 * 线性插值
 * @param {number} start - 起始值
 * @param {number} end - 结束值
 * @param {number} factor - 插值因子 (0-1)
 * @returns {number} 插值结果
 */
function lerp(start, end, factor) {
    return start + (end - start) * factor;
}

/**
 * 将角度转换为弧度
 * @param {number} degrees - 角度
 * @returns {number} 弧度
 */
function degreesToRadians(degrees) {
    return degrees * (Math.PI / 180);
}

/**
 * 将弧度转换为角度
 * @param {number} radians - 弧度
 * @returns {number} 角度
 */
function radiansToDegrees(radians) {
    return radians * (180 / Math.PI);
}

/**
 * 计算两点之间的距离
 * @param {Object} point1 - 第一个点 {x, y}
 * @param {Object} point2 - 第二个点 {x, y}
 * @returns {number} 距离
 */
function distance(point1, point2) {
    const dx = point2.x - point1.x;
    const dy = point2.y - point1.y;
    return Math.sqrt(dx * dx + dy * dy);
}

/**
 * 检查设备是否为移动设备
 * @returns {boolean} 是否为移动设备
 */
function isMobile() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

/**
 * 检查设备是否为触摸设备
 * @returns {boolean} 是否为触摸设备
 */
function isTouchDevice() {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
}

/**
 * 获取设备方向
 * @returns {string} 'portrait' 或 'landscape'
 */
function getOrientation() {
    return window.innerHeight > window.innerWidth ? 'portrait' : 'landscape';
}

/**
 * 检查是否为横屏
 * @returns {boolean} 是否为横屏
 */
function isLandscape() {
    return getOrientation() === 'landscape';
}

/**
 * 检查是否为竖屏
 * @returns {boolean} 是否为竖屏
 */
function isPortrait() {
    return getOrientation() === 'portrait';
}

/**
 * 添加CSS类
 * @param {Element} element - DOM元素
 * @param {string} className - 类名
 */
function addClass(element, className) {
    if (element && element.classList) {
        element.classList.add(className);
    }
}

/**
 * 移除CSS类
 * @param {Element} element - DOM元素
 * @param {string} className - 类名
 */
function removeClass(element, className) {
    if (element && element.classList) {
        element.classList.remove(className);
    }
}

/**
 * 切换CSS类
 * @param {Element} element - DOM元素
 * @param {string} className - 类名
 * @returns {boolean} 是否包含该类
 */
function toggleClass(element, className) {
    if (element && element.classList) {
        return element.classList.toggle(className);
    }
    return false;
}

/**
 * 检查是否包含CSS类
 * @param {Element} element - DOM元素
 * @param {string} className - 类名
 * @returns {boolean} 是否包含该类
 */
function hasClass(element, className) {
    return element && element.classList && element.classList.contains(className);
}

/**
 * 设置元素样式
 * @param {Element} element - DOM元素
 * @param {Object} styles - 样式对象
 */
function setStyles(element, styles) {
    if (element && element.style) {
        Object.assign(element.style, styles);
    }
}

/**
 * 获取元素位置
 * @param {Element} element - DOM元素
 * @returns {Object} 位置对象 {top, left, width, height}
 */
function getElementPosition(element) {
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return {
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height
    };
}

/**
 * 等待指定时间
 * @param {number} ms - 等待时间（毫秒）
 * @returns {Promise} Promise对象
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 深拷贝对象
 * @param {*} obj - 要拷贝的对象
 * @returns {*} 拷贝后的对象
 */
function deepClone(obj) {
    if (obj === null || typeof obj !== 'object') return obj;
    if (obj instanceof Date) return new Date(obj.getTime());
    if (obj instanceof Array) return obj.map(item => deepClone(item));
    if (typeof obj === 'object') {
        const clonedObj = {};
        for (const key in obj) {
            if (obj.hasOwnProperty(key)) {
                clonedObj[key] = deepClone(obj[key]);
            }
        }
        return clonedObj;
    }
}

/**
 * 合并对象
 * @param {Object} target - 目标对象
 * @param {...Object} sources - 源对象
 * @returns {Object} 合并后的对象
 */
function merge(target, ...sources) {
    if (!sources.length) return target;
    const source = sources.shift();
    
    if (isObject(target) && isObject(source)) {
        for (const key in source) {
            if (isObject(source[key])) {
                if (!target[key]) Object.assign(target, { [key]: {} });
                merge(target[key], source[key]);
            } else {
                Object.assign(target, { [key]: source[key] });
            }
        }
    }
    
    return merge(target, ...sources);
}

/**
 * 检查是否为对象
 * @param {*} item - 要检查的项目
 * @returns {boolean} 是否为对象
 */
function isObject(item) {
    return item && typeof item === 'object' && !Array.isArray(item);
}

/**
 * 生成唯一ID
 * @param {string} prefix - 前缀
 * @returns {string} 唯一ID
 */
function generateId(prefix = 'id') {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string} 格式化后的文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * 验证邮箱格式
 * @param {string} email - 邮箱地址
 * @returns {boolean} 是否为有效邮箱
 */
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * 验证URL格式
 * @param {string} url - URL地址
 * @returns {boolean} 是否为有效URL
 */
function isValidUrl(url) {
    try {
        new URL(url);
        return true;
    } catch {
        return false;
    }
}

/**
 * 获取URL参数
 * @param {string} name - 参数名
 * @returns {string|null} 参数值
 */
function getUrlParameter(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

/**
 * 设置URL参数
 * @param {string} name - 参数名
 * @param {string} value - 参数值
 */
function setUrlParameter(name, value) {
    const url = new URL(window.location);
    url.searchParams.set(name, value);
    window.history.replaceState({}, '', url);
}

/**
 * 移除URL参数
 * @param {string} name - 参数名
 */
function removeUrlParameter(name) {
    const url = new URL(window.location);
    url.searchParams.delete(name);
    window.history.replaceState({}, '', url);
}

// 导出工具函数
window.OGScopeUtils = {
    formatTime,
    debounce,
    throttle,
    random,
    randomInt,
    clamp,
    lerp,
    degreesToRadians,
    radiansToDegrees,
    distance,
    isMobile,
    isTouchDevice,
    getOrientation,
    isLandscape,
    isPortrait,
    addClass,
    removeClass,
    toggleClass,
    hasClass,
    setStyles,
    getElementPosition,
    sleep,
    deepClone,
    merge,
    isObject,
    generateId,
    formatFileSize,
    isValidEmail,
    isValidUrl,
    getUrlParameter,
    setUrlParameter,
    removeUrlParameter
};