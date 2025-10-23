/**
 * OGScope 极轴校准模块
 * 处理极轴校准相关的所有功能
 */

import { alignmentAPI } from '../shared/api.js';
import { Utils, EventEmitter } from '../shared/utils.js';
import { APP_CONFIG, EVENTS } from '../shared/constants.js';

export class AlignmentController extends EventEmitter {
    constructor() {
        super();
        this.isAligning = false;
        this.progress = 0;
        this.status = 'idle';
        this.result = {
            azimuthError: null,
            altitudeError: null,
            precision: null,
            isComplete: false
        };
        this.updateInterval = null;
        this.init();
    }

    /**
     * 初始化校准控制器
     */
    init() {
        this.setupEventListeners();
        this.loadProgress();
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 页面卸载时停止校准
        window.addEventListener('beforeunload', () => {
            if (this.isAligning) {
                this.stopAlignment();
            }
        });
    }

    /**
     * 开始校准
     * @returns {Promise<boolean>} 是否成功开始
     */
    async startAlignment() {
        try {
            if (this.isAligning) {
                console.log('[Alignment] 校准已在进行中');
                return true;
            }

            console.log('[Alignment] 开始极轴校准...');
            
            // 调用API开始校准
            await alignmentAPI.startAlignment();
            
            this.isAligning = true;
            this.status = 'running';
            this.progress = 0;
            this.result.isComplete = false;
            
            // 开始进度更新
            this.startProgressUpdate();
            
            this.emit(EVENTS.ALIGNMENT_START);
            console.log('[Alignment] 校准开始成功');
            return true;
        } catch (error) {
            console.error('[Alignment] 校准开始失败:', error);
            this.emit(EVENTS.ALIGNMENT_ERROR, error);
            return false;
        }
    }

    /**
     * 停止校准
     * @returns {Promise<boolean>} 是否成功停止
     */
    async stopAlignment() {
        try {
            if (!this.isAligning) {
                console.log('[Alignment] 校准未在进行中');
                return true;
            }

            console.log('[Alignment] 停止极轴校准...');
            
            // 调用API停止校准
            await alignmentAPI.stopAlignment();
            
            this.isAligning = false;
            this.status = 'stopped';
            this.stopProgressUpdate();
            
            this.emit(EVENTS.ALIGNMENT_STOP);
            console.log('[Alignment] 校准停止成功');
            return true;
        } catch (error) {
            console.error('[Alignment] 校准停止失败:', error);
            return false;
        }
    }

    /**
     * 开始进度更新
     */
    startProgressUpdate() {
        this.updateInterval = setInterval(async () => {
            try {
                await this.updateProgress();
            } catch (error) {
                console.error('[Alignment] 进度更新失败:', error);
            }
        }, APP_CONFIG.ALIGNMENT.UPDATE_INTERVAL);
    }

    /**
     * 停止进度更新
     */
    stopProgressUpdate() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    /**
     * 更新校准进度
     */
    async updateProgress() {
        try {
            const progressData = await alignmentAPI.getProgress();
            
            this.progress = progressData.progress || 0;
            this.status = progressData.status || this.status;
            
            // 更新校准结果
            if (progressData.result) {
                this.result = {
                    azimuthError: progressData.result.azimuthError,
                    altitudeError: progressData.result.altitudeError,
                    precision: progressData.result.precision,
                    isComplete: progressData.result.isComplete
                };
            }
            
            this.emit(EVENTS.ALIGNMENT_PROGRESS, {
                progress: this.progress,
                status: this.status,
                result: this.result
            });
            
            // 检查是否完成
            if (this.result.isComplete) {
                this.completeAlignment();
            }
        } catch (error) {
            console.error('[Alignment] 获取进度失败:', error);
        }
    }

    /**
     * 完成校准
     */
    async completeAlignment() {
        try {
            console.log('[Alignment] 校准完成');
            
            this.isAligning = false;
            this.status = 'completed';
            this.stopProgressUpdate();
            
            // 获取最终结果
            const finalResult = await alignmentAPI.getResult();
            this.result = { ...this.result, ...finalResult };
            
            this.emit(EVENTS.ALIGNMENT_COMPLETE, this.result);
            
            // 保存进度
            this.saveProgress();
        } catch (error) {
            console.error('[Alignment] 获取最终结果失败:', error);
        }
    }

    /**
     * 获取校准结果
     * @returns {Object} 校准结果
     */
    getResult() {
        return { ...this.result };
    }

    /**
     * 获取校准进度
     * @returns {Object} 校准进度
     */
    getProgress() {
        return {
            progress: this.progress,
            status: this.status,
            isAligning: this.isAligning,
            result: this.result
        };
    }

    /**
     * 格式化误差显示
     * @param {number} error - 误差值（度）
     * @returns {string} 格式化的误差字符串
     */
    formatError(error) {
        if (error === null || error === undefined) {
            return '--';
        }
        
        // 转换为角分
        const arcMinutes = Math.abs(error * 60);
        
        if (arcMinutes >= APP_CONFIG.ALIGNMENT.MAX_ERROR_DISPLAY) {
            return `${APP_CONFIG.ALIGNMENT.MAX_ERROR_DISPLAY}+`;
        }
        
        return arcMinutes.toFixed(1);
    }

    /**
     * 获取精度等级
     * @param {number} precision - 精度值
     * @returns {string} 精度等级
     */
    getPrecisionLevel(precision) {
        if (precision === null || precision === undefined) {
            return '--';
        }
        
        if (precision <= APP_CONFIG.ALIGNMENT.PRECISION_THRESHOLD) {
            return '优秀';
        } else if (precision <= APP_CONFIG.ALIGNMENT.PRECISION_THRESHOLD * 2) {
            return '良好';
        } else if (precision <= APP_CONFIG.ALIGNMENT.PRECISION_THRESHOLD * 5) {
            return '一般';
        } else {
            return '需改进';
        }
    }

    /**
     * 保存进度到本地存储
     */
    saveProgress() {
        const progressData = {
            progress: this.progress,
            status: this.status,
            result: this.result,
            timestamp: Date.now()
        };
        Utils.saveToStorage('alignment-progress', progressData);
    }

    /**
     * 从本地存储加载进度
     */
    loadProgress() {
        const savedProgress = Utils.loadFromStorage('alignment-progress', null);
        if (savedProgress) {
            // 检查时间戳，如果超过1小时则重置
            const oneHour = 60 * 60 * 1000;
            if (Date.now() - savedProgress.timestamp < oneHour) {
                this.progress = savedProgress.progress || 0;
                this.status = savedProgress.status || 'idle';
                this.result = savedProgress.result || this.result;
            }
        }
    }

    /**
     * 重置校准状态
     */
    reset() {
        this.isAligning = false;
        this.progress = 0;
        this.status = 'idle';
        this.result = {
            azimuthError: null,
            altitudeError: null,
            precision: null,
            isComplete: false
        };
        this.stopProgressUpdate();
        
        // 清除本地存储
        localStorage.removeItem('alignment-progress');
    }
}
