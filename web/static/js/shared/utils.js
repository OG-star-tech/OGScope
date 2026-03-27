/* OGScope - 工具函数 / OGScope - Utility functions */
/**
 * 格式化时间显示 / Format time display
 * @param {number} seconds - 秒数 / number of seconds
 * @returns {string} 格式化后的时间字符串 / Formatted time string
 */
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 10);
    return mins > 0 ? `${mins}:${secs.toString().padStart(2, '0')}.${ms}` : `${secs}.${ms}s`;
}

/**
 * 防抖函数 / Debounce function
 * @param {Function} func - 要防抖的函数 / 要防抖的函数
 * @param {number} wait - 等待时间 / waiting time
 * @returns {Function} 防抖后的函数 / Function after anti-shake
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
 * 节流函数 / Throttle function
 * @param {Function} func - 要节流的函数 / the function to throttle
 * @param {number} limit - 时间限制 / time limit
 * @returns {Function} 节流后的函数 / Throttled function
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
 * 生成随机数 / Generate random numbers
 * @param {number} min - 最小值 / minimum value
 * @param {number} max - 最大值 / maximum value
 * @returns {number} 随机数 / random number
 */
function random(min, max) {
    return Math.random() * (max - min) + min;
}

/**
 * 生成随机整数 / Generate random integers
 * @param {number} min - 最小值 / minimum value
 * @param {number} max - 最大值 / maximum value
 * @returns {number} 随机整数 / random integer
 */
function randomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * 限制数值范围 / Limit the range of values
 * @param {number} value - 数值 / numerical value
 * @param {number} min - 最小值 / minimum value
 * @param {number} max - 最大值 / maximum value
 * @returns {number} 限制后的数值 / the restricted value
 */
function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

/**
 * 线性插值 / linear interpolation
 * @param {number} start - 起始值 / starting value
 * @param {number} end - 结束值 / end value
 * @param {number} factor - 插值因子 (0-1) / interpolation factor (0-1)
 * @returns {number} 插值结果 / interpolation result
 */
function lerp(start, end, factor) {
    return start + (end - start) * factor;
}

/**
 * 将角度转换为弧度 / Convert angles to radians
 * @param {number} degrees - 角度 / angle
 * @returns {number} 弧度 / radians
 */
function degreesToRadians(degrees) {
    return degrees * (Math.PI / 180);
}

/**
 * 将弧度转换为角度 / Convert radians to degrees
 * @param {number} radians - 弧度 / radians
 * @returns {number} 角度 / angle
 */
function radiansToDegrees(radians) {
    return radians * (180 / Math.PI);
}

/**
 * 计算两点之间的距离 / Calculate the distance between two points
 * @param {Object} point1 - 第一个点 {x, y} / the first point {x, y}
 * @param {Object} point2 - 第二个点 {x, y} / the second point {x, y}
 * @returns {number} 距离 / distance
 */
function distance(point1, point2) {
    const dx = point2.x - point1.x;
    const dy = point2.y - point1.y;
    return Math.sqrt(dx * dx + dy * dy);
}

/**
 * 检查设备是否为移动设备 / Check if the device is mobile
 * @returns {boolean} 是否为移动设备 / whether it is a mobile device
 */
function isMobile() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

/**
 * 检查设备是否为触摸设备 / Check if the device is a touch device
 * @returns {boolean} 是否为触摸设备 / whether it is a touch device
 */
function isTouchDevice() {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
}

/**
 * 获取设备方向 / Get device orientation
 * @returns {string} 'portrait' 或 'landscape' / 'portrait' or 'landscape'
 */
function getOrientation() {
    return window.innerHeight > window.innerWidth ? 'portrait' : 'landscape';
}

/**
 * 检查是否为横屏 / Check if it is landscape orientation
 * @returns {boolean} 是否为横屏 / Whether it is horizontal screen
 */
function isLandscape() {
    return getOrientation() === 'landscape';
}

/**
 * 检查是否为竖屏 / Check if it is vertical screen
 * @returns {boolean} 是否为竖屏 / Whether the screen is vertical
 */
function isPortrait() {
    return getOrientation() === 'portrait';
}

/**
 * 添加CSS类 / Add CSS classes
 * @param {Element} element - DOM元素 / DOM element
 * @param {string} className - 类名 / class name
 */
function addClass(element, className) {
    if (element && element.classList) {
        element.classList.add(className);
    }
}

/**
 * 移除CSS类 / Remove CSS classes
 * @param {Element} element - DOM元素 / DOM element
 * @param {string} className - 类名 / class name
 */
function removeClass(element, className) {
    if (element && element.classList) {
        element.classList.remove(className);
    }
}

/**
 * 切换CSS类 / Switch CSS classes
 * @param {Element} element - DOM元素 / DOM element
 * @param {string} className - 类名 / class name
 * @returns {boolean} 是否包含该类 / whether this class is included
 */
function toggleClass(element, className) {
    if (element && element.classList) {
        return element.classList.toggle(className);
    }
    return false;
}

/**
 * 检查是否包含CSS类 / Check if CSS class is included
 * @param {Element} element - DOM元素 / DOM element
 * @param {string} className - 类名 / class name
 * @returns {boolean} 是否包含该类 / whether this class is included
 */
function hasClass(element, className) {
    return element && element.classList && element.classList.contains(className);
}

/**
 * 设置元素样式 / Set element style
 * @param {Element} element - DOM元素 / DOM element
 * @param {Object} styles - 样式对象 / style object
 */
function setStyles(element, styles) {
    if (element && element.style) {
        Object.assign(element.style, styles);
    }
}

/**
 * 获取元素位置 / Get element position
 * @param {Element} element - DOM元素 / DOM element
 * @returns {Object} 位置对象 {top, left, width, height} / position object {top, left, width, height}
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
 * 等待指定时间 / Wait for specified time
 * @param {number} ms - 等待时间（毫秒） / waiting time (milliseconds)
 * @returns {Promise} Promise对象 / Promise object
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 深拷贝对象 / deep copy object
 * @param {*} obj - 要拷贝的对象 / the object to be copied
 * @returns {*} 拷贝后的对象 / copied object
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
 * 合并对象 / Merge objects
 * @param {Object} target - 目标对象 / target object
 * @param {...Object} sources - 源对象 / source object
 * @returns {Object} 合并后的对象 / merged object
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
 * 检查是否为对象 / Check if it is an object
 * @param {*} item - 要检查的项目 / the item to check
 * @returns {boolean} 是否为对象 / whether it is an object
 */
function isObject(item) {
    return item && typeof item === 'object' && !Array.isArray(item);
}

/**
 * 生成唯一ID / Generate unique ID
 * @param {string} prefix - 前缀 / prefix
 * @returns {string} 唯一ID / unique ID
 */
function generateId(prefix = 'id') {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * 格式化文件大小 / Format file size
 * @param {number} bytes - 字节数 / Number of bytes
 * @returns {string} 格式化后的文件大小 / formatted file size
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * 验证邮箱格式 / Verify email format
 * @param {string} email - 邮箱地址 / email address
 * @returns {boolean} 是否为有效邮箱 / whether it is a valid email address
 */
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * 验证URL格式 / Verify URL format
 * @param {string} url - URL地址 / URL address
 * @returns {boolean} 是否为有效URL / whether it is a valid URL
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
 * 获取URL参数 / Get URL parameters
 * @param {string} name - 参数名 / parameter name
 * @returns {string|null} 参数值 / parameter value
 */
function getUrlParameter(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

/**
 * 设置URL参数 / Set URL parameters
 * @param {string} name - 参数名 / parameter name
 * @param {string} value - 参数值 / parameter value
 */
function setUrlParameter(name, value) {
    const url = new URL(window.location);
    url.searchParams.set(name, value);
    window.history.replaceState({}, '', url);
}

/**
 * 移除URL参数 / Remove URL parameters
 * @param {string} name - 参数名 / parameter name
 */
function removeUrlParameter(name) {
    const url = new URL(window.location);
    url.searchParams.delete(name);
    window.history.replaceState({}, '', url);
}

// 导出工具函数 / Export utility functions
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