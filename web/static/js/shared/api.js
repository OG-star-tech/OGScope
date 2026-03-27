/* OGScope - API通信模块 / OGScope - API communication module */
/**
 * API通信类 / API communication class
 */
class OGScopeAPI {
    constructor() {
        this.baseURL = '';
        this.timeout = 10000;
        this.retryCount = 3;
        this.retryDelay = 1000;
    }

    /**
     * 发送HTTP请求 / Send HTTP request
     * @param {string} url - 请求URL / request URL
     * @param {Object} options - 请求选项 / request options
     * @returns {Promise} 请求结果 / request results
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
     * GET请求 / GET request
     * @param {string} endpoint - 端点 / endpoint
     * @param {Object} params - 查询参数 / query parameters
     * @returns {Promise} 请求结果 / request results
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
     * POST请求 / POST request
     * @param {string} endpoint - 端点 / endpoint
     * @param {Object} data - 请求数据 / request data
     * @returns {Promise} 请求结果 / request results
     */
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    /**
     * PUT请求 / PUT request
     * @param {string} endpoint - 端点 / endpoint
     * @param {Object} data - 请求数据 / request data
     * @returns {Promise} 请求结果 / request results
     */
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    /**
     * DELETE请求 / DELETE request
     * @param {string} endpoint - 端点 / endpoint
     * @returns {Promise} 请求结果 / request results
     */
    async delete(endpoint) {
        return this.request(endpoint, {
            method: 'DELETE'
        });
    }

    /**
     * 带重试的请求 / Request with retry
     * @param {Function} requestFn - 请求函数 / request function
     * @param {number} retries - 重试次数 / Number of retries
     * @returns {Promise} 请求结果 / request results
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
 * WebSocket连接管理 / WebSocket connection management
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
     * 连接WebSocket / Connect WebSocket
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
     * 断开WebSocket连接 / Disconnect WebSocket
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.stopHeartbeat();
    }

    /**
     * 发送消息 / Send message
     * @param {Object} data - 消息数据 / message data
     */
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket未连接，无法发送消息');
        }
    }

    /**
     * 尝试重连 / Try to reconnect
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
     * 开始心跳 / Start heartbeat
     */
    startHeartbeat() {
        this.heartbeatTimer = setInterval(() => {
            this.send({ type: 'ping' });
        }, this.heartbeatInterval);
    }

    /**
     * 停止心跳 / stop heartbeat
     */
    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    /**
     * 添加事件监听器 / Add event listener
     * @param {string} event - 事件名 / event name
     * @param {Function} callback - 回调函数 / callback function
     */
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    /**
     * 移除事件监听器 / Remove event listener
     * @param {string} event - 事件名 / event name
     * @param {Function} callback - 回调函数 / callback function
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
     * 触发事件 / trigger event
     * @param {string} event - 事件名 / event name
     * @param {...any} args - 参数 / parameters
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

// 创建API实例 / Create API instance
const wsManager = new WebSocketManager();

// 导出API / Export API
window.OGScopeAPI = {
    OGScopeAPI,
    WebSocketManager,
    wsManager
};