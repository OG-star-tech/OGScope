/* OGScope - API通信模块 */

/**
 * API通信类
 */
class OGScopeAPI {
    constructor() {
        this.baseURL = '';
        this.timeout = 10000;
        this.retryCount = 3;
        this.retryDelay = 1000;
    }

    /**
     * 发送HTTP请求
     * @param {string} url - 请求URL
     * @param {Object} options - 请求选项
     * @returns {Promise} 请求结果
     */
    async request(url, options = {}) {
        const defaultOptions = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
            timeout: this.timeout
        };

        const requestOptions = { ...defaultOptions, ...options };
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.timeout);
            
            requestOptions.signal = controller.signal;
            
            const response = await fetch(url, requestOptions);
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            } else {
                return await response.text();
            }
        } catch (error) {
            console.error('API请求失败:', error);
            throw error;
        }
    }

    /**
     * GET请求
     * @param {string} endpoint - 端点
     * @param {Object} params - 查询参数
     * @returns {Promise} 请求结果
     */
    async get(endpoint, params = {}) {
        const url = new URL(endpoint, this.baseURL);
        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined) {
                url.searchParams.append(key, params[key]);
            }
        });
        
        return this.request(url.toString());
    }

    /**
     * POST请求
     * @param {string} endpoint - 端点
     * @param {Object} data - 请求数据
     * @returns {Promise} 请求结果
     */
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    /**
     * PUT请求
     * @param {string} endpoint - 端点
     * @param {Object} data - 请求数据
     * @returns {Promise} 请求结果
     */
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    /**
     * DELETE请求
     * @param {string} endpoint - 端点
     * @returns {Promise} 请求结果
     */
    async delete(endpoint) {
        return this.request(endpoint, {
            method: 'DELETE'
        });
    }

    /**
     * 带重试的请求
     * @param {Function} requestFn - 请求函数
     * @param {number} retries - 重试次数
     * @returns {Promise} 请求结果
     */
    async requestWithRetry(requestFn, retries = this.retryCount) {
        for (let i = 0; i < retries; i++) {
            try {
                return await requestFn();
            } catch (error) {
                if (i === retries - 1) {
                    throw error;
                }
                await OGScopeUtils.sleep(this.retryDelay * Math.pow(2, i));
            }
        }
    }
}

/**
 * 视频流API
 */
class VideoAPI extends OGScopeAPI {
    constructor() {
        super();
    }

    /**
     * 获取视频流URL
     * @returns {string} 视频流URL
     */
    getStreamURL() {
        return `${this.baseURL}${OGScopeConstants.APP_CONSTANTS.API_ENDPOINTS.VIDEO_STREAM}`;
    }

    /**
     * 获取预览图像URL
     * @returns {string} 预览图像URL
     */
    getPreviewURL() {
        return `${this.baseURL}${OGScopeConstants.APP_CONSTANTS.API_ENDPOINTS.CAMERA_PREVIEW}`;
    }

    /**
     * 设置视频参数
     * @param {Object} params - 视频参数
     * @returns {Promise} 设置结果
     */
    async setVideoParams(params) {
        return this.post('/api/video/params', params);
    }

    /**
     * 获取视频状态
     * @returns {Promise} 视频状态
     */
    async getVideoStatus() {
        return this.get('/api/video/status');
    }

    /**
     * 开始录制
     * @returns {Promise} 录制结果
     */
    async startRecording() {
        return this.post('/api/video/record/start');
    }

    /**
     * 停止录制
     * @returns {Promise} 停止结果
     */
    async stopRecording() {
        return this.post('/api/video/record/stop');
    }

    /**
     * 拍照
     * @returns {Promise} 拍照结果
     */
    async capturePhoto() {
        return this.post('/api/video/capture');
    }
}

/**
 * 校准API
 */
class AlignmentAPI extends OGScopeAPI {
    constructor() {
        super();
    }

    /**
     * 获取校准状态
     * @returns {Promise} 校准状态
     */
    async getAlignmentStatus() {
        return this.get(OGScopeConstants.APP_CONSTANTS.API_ENDPOINTS.ALIGNMENT_STATUS);
    }

    /**
     * 开始校准
     * @param {Object} params - 校准参数
     * @returns {Promise} 校准结果
     */
    async startAlignment(params = {}) {
        return this.post('/api/alignment/start', params);
    }

    /**
     * 停止校准
     * @returns {Promise} 停止结果
     */
    async stopAlignment() {
        return this.post('/api/alignment/stop');
    }

    /**
     * 重置校准
     * @returns {Promise} 重置结果
     */
    async resetAlignment() {
        return this.post('/api/alignment/reset');
    }

    /**
     * 获取校准偏移
     * @returns {Promise} 偏移数据
     */
    async getAlignmentOffset() {
        return this.get('/api/alignment/offset');
    }

    /**
     * 设置校准偏移
     * @param {Object} offset - 偏移数据
     * @returns {Promise} 设置结果
     */
    async setAlignmentOffset(offset) {
        return this.post('/api/alignment/offset', offset);
    }
}

/**
 * 系统API
 */
class SystemAPI extends OGScopeAPI {
    constructor() {
        super();
    }

    /**
     * 获取系统信息
     * @returns {Promise} 系统信息
     */
    async getSystemInfo() {
        return this.get(OGScopeConstants.APP_CONSTANTS.API_ENDPOINTS.SYSTEM_INFO);
    }

    /**
     * 获取设备状态
     * @returns {Promise} 设备状态
     */
    async getDeviceStatus() {
        return this.get('/api/system/device/status');
    }

    /**
     * 获取GPS信息
     * @returns {Promise} GPS信息
     */
    async getGPSInfo() {
        return this.get('/api/system/gps');
    }

    /**
     * 获取电池信息
     * @returns {Promise} 电池信息
     */
    async getBatteryInfo() {
        return this.get('/api/system/battery');
    }

    /**
     * 获取网络信息
     * @returns {Promise} 网络信息
     */
    async getNetworkInfo() {
        return this.get('/api/system/network');
    }

    /**
     * 重启系统
     * @returns {Promise} 重启结果
     */
    async restartSystem() {
        return this.post('/api/system/restart');
    }

    /**
     * 关机
     * @returns {Promise} 关机结果
     */
    async shutdownSystem() {
        return this.post('/api/system/shutdown');
    }
}

/**
 * 设置API
 */
class SettingsAPI extends OGScopeAPI {
    constructor() {
        super();
    }

    /**
     * 获取设置
     * @returns {Promise} 设置数据
     */
    async getSettings() {
        return this.get(OGScopeConstants.APP_CONSTANTS.API_ENDPOINTS.SETTINGS);
    }

    /**
     * 保存设置
     * @param {Object} settings - 设置数据
     * @returns {Promise} 保存结果
     */
    async saveSettings(settings) {
        return this.post(OGScopeConstants.APP_CONSTANTS.API_ENDPOINTS.SETTINGS, settings);
    }

    /**
     * 重置设置
     * @returns {Promise} 重置结果
     */
    async resetSettings() {
        return this.post('/api/settings/reset');
    }

    /**
     * 导出设置
     * @returns {Promise} 设置数据
     */
    async exportSettings() {
        return this.get('/api/settings/export');
    }

    /**
     * 导入设置
     * @param {Object} settings - 设置数据
     * @returns {Promise} 导入结果
     */
    async importSettings(settings) {
        return this.post('/api/settings/import', settings);
    }
}

/**
 * WebSocket连接管理
 */
class WebSocketManager {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.heartbeatInterval = 30000;
        this.heartbeatTimer = null;
        this.listeners = new Map();
    }

    /**
     * 连接WebSocket
     * @param {string} url - WebSocket URL
     */
    connect(url) {
        try {
            this.ws = new WebSocket(url);
            
            this.ws.onopen = () => {
                console.log('WebSocket连接已建立');
                this.reconnectAttempts = 0;
                this.startHeartbeat();
                this.emit('connected');
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.emit('message', data);
                } catch (error) {
                    console.error('WebSocket消息解析失败:', error);
                }
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket连接已关闭');
                this.stopHeartbeat();
                this.emit('disconnected');
                this.attemptReconnect(url);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket错误:', error);
                this.emit('error', error);
            };
        } catch (error) {
            console.error('WebSocket连接失败:', error);
            this.emit('error', error);
        }
    }

    /**
     * 断开WebSocket连接
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.stopHeartbeat();
    }

    /**
     * 发送消息
     * @param {Object} data - 消息数据
     */
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket未连接，无法发送消息');
        }
    }

    /**
     * 尝试重连
     * @param {string} url - WebSocket URL
     */
    attemptReconnect(url) {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            
            setTimeout(() => {
                this.connect(url);
            }, this.reconnectDelay * this.reconnectAttempts);
        } else {
            console.error('WebSocket重连失败，已达到最大重试次数');
        }
    }

    /**
     * 开始心跳
     */
    startHeartbeat() {
        this.heartbeatTimer = setInterval(() => {
            this.send({ type: 'ping' });
        }, this.heartbeatInterval);
    }

    /**
     * 停止心跳
     */
    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    /**
     * 添加事件监听器
     * @param {string} event - 事件名
     * @param {Function} callback - 回调函数
     */
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    /**
     * 移除事件监听器
     * @param {string} event - 事件名
     * @param {Function} callback - 回调函数
     */
    off(event, callback) {
        if (this.listeners.has(event)) {
            const callbacks = this.listeners.get(event);
            const index = callbacks.indexOf(callback);
            if (index > -1) {
                callbacks.splice(index, 1);
            }
        }
    }

    /**
     * 触发事件
     * @param {string} event - 事件名
     * @param {...any} args - 参数
     */
    emit(event, ...args) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(...args);
                } catch (error) {
                    console.error('事件回调执行失败:', error);
                }
            });
        }
    }
}

// 创建API实例
const videoAPI = new VideoAPI();
const alignmentAPI = new AlignmentAPI();
const systemAPI = new SystemAPI();
const settingsAPI = new SettingsAPI();
const wsManager = new WebSocketManager();

// 导出API
window.OGScopeAPI = {
    VideoAPI,
    AlignmentAPI,
    SystemAPI,
    SettingsAPI,
    WebSocketManager,
    videoAPI,
    alignmentAPI,
    systemAPI,
    settingsAPI,
    wsManager
};