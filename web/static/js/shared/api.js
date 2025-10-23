/**
 * OGScope API通信工具
 * 提供统一的API调用接口
 */

import { APP_CONFIG, ERROR_MESSAGES } from './constants.js';

export class APIClient {
    constructor() {
        this.baseURL = APP_CONFIG.API_BASE_URL;
        this.timeout = APP_CONFIG.NETWORK.TIMEOUT;
    }

    /**
     * 发送HTTP请求
     * @param {string} endpoint - API端点
     * @param {Object} options - 请求选项
     * @returns {Promise} 响应数据
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            timeout: this.timeout,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`[API] 请求失败 ${endpoint}:`, error);
            throw this.handleError(error);
        }
    }

    /**
     * GET请求
     * @param {string} endpoint - API端点
     * @param {Object} params - 查询参数
     * @returns {Promise} 响应数据
     */
    async get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        
        return this.request(url, { method: 'GET' });
    }

    /**
     * POST请求
     * @param {string} endpoint - API端点
     * @param {Object} data - 请求数据
     * @returns {Promise} 响应数据
     */
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    /**
     * PUT请求
     * @param {string} endpoint - API端点
     * @param {Object} data - 请求数据
     * @returns {Promise} 响应数据
     */
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    /**
     * DELETE请求
     * @param {string} endpoint - API端点
     * @returns {Promise} 响应数据
     */
    async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }

    /**
     * 处理错误
     * @param {Error} error - 原始错误
     * @returns {Error} 处理后的错误
     */
    handleError(error) {
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
            return new Error(ERROR_MESSAGES.NETWORK_ERROR);
        }
        return error;
    }
}

/**
 * 相机API
 */
export class CameraAPI {
    constructor(apiClient) {
        this.api = apiClient;
    }

    /**
     * 获取相机状态
     * @returns {Promise} 相机状态
     */
    async getStatus() {
        return this.api.get('/camera/status');
    }

    /**
     * 开始视频流
     * @returns {Promise} 流状态
     */
    async startStream() {
        return this.api.post('/camera/stream/start');
    }

    /**
     * 停止视频流
     * @returns {Promise} 流状态
     */
    async stopStream() {
        return this.api.post('/camera/stream/stop');
    }

    /**
     * 更新相机设置
     * @param {Object} settings - 相机设置
     * @returns {Promise} 更新结果
     */
    async updateSettings(settings) {
        return this.api.put('/camera/settings', settings);
    }

    /**
     * 拍摄照片
     * @returns {Promise} 拍摄结果
     */
    async captureImage() {
        return this.api.post('/camera/capture');
    }

    /**
     * 开始录制
     * @returns {Promise} 录制状态
     */
    async startRecording() {
        return this.api.post('/camera/recording/start');
    }

    /**
     * 停止录制
     * @returns {Promise} 录制状态
     */
    async stopRecording() {
        return this.api.post('/camera/recording/stop');
    }
}

/**
 * 校准API
 */
export class AlignmentAPI {
    constructor(apiClient) {
        this.api = apiClient;
    }

    /**
     * 开始校准
     * @returns {Promise} 校准状态
     */
    async startAlignment() {
        return this.api.post('/alignment/start');
    }

    /**
     * 停止校准
     * @returns {Promise} 校准状态
     */
    async stopAlignment() {
        return this.api.post('/alignment/stop');
    }

    /**
     * 获取校准进度
     * @returns {Promise} 校准进度
     */
    async getProgress() {
        return this.api.get('/alignment/progress');
    }

    /**
     * 获取校准结果
     * @returns {Promise} 校准结果
     */
    async getResult() {
        return this.api.get('/alignment/result');
    }
}

// 创建全局API客户端实例
export const apiClient = new APIClient();
export const cameraAPI = new CameraAPI(apiClient);
export const alignmentAPI = new AlignmentAPI(apiClient);
