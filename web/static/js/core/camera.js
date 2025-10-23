/**
 * OGScope 相机控制模块
 * 处理相机相关的所有功能
 */

import { cameraAPI } from '../shared/api.js';
import { Utils, EventEmitter } from '../shared/utils.js';
import { APP_CONFIG, EVENTS } from '../shared/constants.js';

export class CameraController extends EventEmitter {
    constructor() {
        super();
        this.isStreaming = false;
        this.isRecording = false;
        this.settings = {
            exposure: APP_CONFIG.CAMERA.DEFAULT_EXPOSURE,
            gain: APP_CONFIG.CAMERA.DEFAULT_GAIN,
            brightness: APP_CONFIG.CAMERA.DEFAULT_BRIGHTNESS
        };
        this.streamElement = null;
        this.init();
    }

    /**
     * 初始化相机控制器
     */
    init() {
        this.streamElement = document.getElementById('mjpeg-stream');
        this.setupEventListeners();
        this.loadSettings();
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 视频流元素事件
        if (this.streamElement) {
            this.streamElement.addEventListener('load', () => {
                this.emit(EVENTS.CAMERA_STREAM_START);
            });
            
            this.streamElement.addEventListener('error', () => {
                this.emit(EVENTS.CAMERA_STREAM_ERROR);
            });
        }

        // 网络状态监听
        window.addEventListener('online', () => {
            this.emit(EVENTS.NETWORK_ONLINE);
        });
        
        window.addEventListener('offline', () => {
            this.emit(EVENTS.NETWORK_OFFLINE);
        });
    }

    /**
     * 开始视频流
     * @returns {Promise<boolean>} 是否成功启动
     */
    async startStream() {
        try {
            if (this.isStreaming) {
                console.log('[Camera] 视频流已在运行');
                return true;
            }

            console.log('[Camera] 启动视频流...');
            
            // 更新视频流URL，添加时间戳防止缓存
            const timestamp = Date.now();
            this.streamElement.src = `${APP_CONFIG.CAMERA_PREVIEW_URL}?t=${timestamp}`;
            
            this.isStreaming = true;
            this.emit(EVENTS.CAMERA_STREAM_START);
            
            console.log('[Camera] 视频流启动成功');
            return true;
        } catch (error) {
            console.error('[Camera] 视频流启动失败:', error);
            this.emit(EVENTS.CAMERA_STREAM_ERROR, error);
            return false;
        }
    }

    /**
     * 停止视频流
     * @returns {Promise<boolean>} 是否成功停止
     */
    async stopStream() {
        try {
            if (!this.isStreaming) {
                console.log('[Camera] 视频流未在运行');
                return true;
            }

            console.log('[Camera] 停止视频流...');
            
            // 停止视频流
            this.streamElement.src = '';
            this.isStreaming = false;
            this.emit(EVENTS.CAMERA_STREAM_STOP);
            
            console.log('[Camera] 视频流停止成功');
            return true;
        } catch (error) {
            console.error('[Camera] 视频流停止失败:', error);
            return false;
        }
    }

    /**
     * 切换视频流状态
     * @returns {Promise<boolean>} 新的流状态
     */
    async toggleStream() {
        if (this.isStreaming) {
            await this.stopStream();
            return false;
        } else {
            await this.startStream();
            return true;
        }
    }

    /**
     * 更新相机设置
     * @param {Object} newSettings - 新的设置
     * @returns {Promise<boolean>} 是否更新成功
     */
    async updateSettings(newSettings) {
        try {
            console.log('[Camera] 更新相机设置:', newSettings);
            
            // 验证设置范围
            const validatedSettings = this.validateSettings(newSettings);
            
            // 发送到API
            await cameraAPI.updateSettings(validatedSettings);
            
            // 更新本地设置
            this.settings = { ...this.settings, ...validatedSettings };
            
            // 保存到本地存储
            this.saveSettings();
            
            console.log('[Camera] 相机设置更新成功');
            return true;
        } catch (error) {
            console.error('[Camera] 相机设置更新失败:', error);
            return false;
        }
    }

    /**
     * 验证设置范围
     * @param {Object} settings - 要验证的设置
     * @returns {Object} 验证后的设置
     */
    validateSettings(settings) {
        const validated = {};
        
        if (settings.exposure !== undefined) {
            validated.exposure = Utils.clamp(
                settings.exposure,
                APP_CONFIG.CAMERA.MIN_EXPOSURE,
                APP_CONFIG.CAMERA.MAX_EXPOSURE
            );
        }
        
        if (settings.gain !== undefined) {
            validated.gain = Utils.clamp(
                settings.gain,
                APP_CONFIG.CAMERA.MIN_GAIN,
                APP_CONFIG.CAMERA.MAX_GAIN
            );
        }
        
        if (settings.brightness !== undefined) {
            validated.brightness = Utils.clamp(settings.brightness, 0.1, 3.0);
        }
        
        return validated;
    }

    /**
     * 拍摄照片
     * @returns {Promise<Object>} 拍摄结果
     */
    async captureImage() {
        try {
            console.log('[Camera] 拍摄照片...');
            const result = await cameraAPI.captureImage();
            console.log('[Camera] 照片拍摄成功');
            return result;
        } catch (error) {
            console.error('[Camera] 照片拍摄失败:', error);
            throw error;
        }
    }

    /**
     * 开始录制
     * @returns {Promise<boolean>} 是否成功开始
     */
    async startRecording() {
        try {
            if (this.isRecording) {
                console.log('[Camera] 录制已在进行中');
                return true;
            }

            console.log('[Camera] 开始录制...');
            await cameraAPI.startRecording();
            this.isRecording = true;
            console.log('[Camera] 录制开始成功');
            return true;
        } catch (error) {
            console.error('[Camera] 录制开始失败:', error);
            return false;
        }
    }

    /**
     * 停止录制
     * @returns {Promise<boolean>} 是否成功停止
     */
    async stopRecording() {
        try {
            if (!this.isRecording) {
                console.log('[Camera] 录制未在进行中');
                return true;
            }

            console.log('[Camera] 停止录制...');
            await cameraAPI.stopRecording();
            this.isRecording = false;
            console.log('[Camera] 录制停止成功');
            return true;
        } catch (error) {
            console.error('[Camera] 录制停止失败:', error);
            return false;
        }
    }

    /**
     * 获取相机状态
     * @returns {Promise<Object>} 相机状态
     */
    async getStatus() {
        try {
            return await cameraAPI.getStatus();
        } catch (error) {
            console.error('[Camera] 获取状态失败:', error);
            return {
                connected: false,
                streaming: this.isStreaming,
                recording: this.isRecording,
                error: error.message
            };
        }
    }

    /**
     * 保存设置到本地存储
     */
    saveSettings() {
        Utils.saveToStorage('camera-settings', this.settings);
    }

    /**
     * 从本地存储加载设置
     */
    loadSettings() {
        const savedSettings = Utils.loadFromStorage('camera-settings', null);
        if (savedSettings) {
            this.settings = { ...this.settings, ...savedSettings };
        }
    }

    /**
     * 获取当前设置
     * @returns {Object} 当前设置
     */
    getSettings() {
        return { ...this.settings };
    }

    /**
     * 重置设置为默认值
     */
    resetSettings() {
        this.settings = {
            exposure: APP_CONFIG.CAMERA.DEFAULT_EXPOSURE,
            gain: APP_CONFIG.CAMERA.DEFAULT_GAIN,
            brightness: APP_CONFIG.CAMERA.DEFAULT_BRIGHTNESS
        };
        this.saveSettings();
    }
}
