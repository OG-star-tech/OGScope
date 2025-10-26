/* OGScope - 校准控制模块 */

/**
 * 校准控制器类
 */
class AlignmentController {
    constructor() {
        this.isCalibrating = false;
        this.calibrationData = {
            azimuthOffset: 0,
            altitudeOffset: 0,
            accuracy: 0,
            lastUpdate: null
        };
        this.targetPosition = {
            azimuth: 0,
            altitude: 0
        };
        this.currentPosition = {
            azimuth: 0,
            altitude: 0
        };
        this.eventListeners = new Map();
        this.updateInterval = null;
        this.init();
    }

    /**
     * 初始化校准控制器
     */
    init() {
        this.loadCalibrationData();
        this.startDataUpdates();
    }

    /**
     * 开始校准
     * @param {Object} options - 校准选项
     * @returns {Promise<boolean>} 校准结果
     */
    async startAlignment(options = {}) {
        if (this.isCalibrating) {
            console.warn('校准已在进行中');
            return false;
        }

        try {
            this.isCalibrating = true;
            this.emit('alignmentStart', options);

            console.log('开始校准...');

            // 模拟校准过程
            const result = await this.performAlignment(options);
            
            if (result.success) {
                this.calibrationData = {
                    azimuthOffset: result.azimuthOffset,
                    altitudeOffset: result.altitudeOffset,
                    accuracy: result.accuracy,
                    lastUpdate: new Date()
                };
                
                this.saveCalibrationData();
                this.emit('alignmentComplete', this.calibrationData);
                
                console.log('校准完成:', this.calibrationData);
                return true;
            } else {
                this.emit('alignmentError', result.error);
                console.error('校准失败:', result.error);
                return false;
            }
        } catch (error) {
            this.emit('alignmentError', error);
            console.error('校准过程出错:', error);
            return false;
        } finally {
            this.isCalibrating = false;
        }
    }

    /**
     * 执行校准
     * @param {Object} options - 校准选项
     * @returns {Promise<Object>} 校准结果
     */
    async performAlignment(options) {
        return new Promise((resolve) => {
            // 模拟校准过程
            let progress = 0;
            const steps = [
                { progress: 20, message: '正在检测星点...' },
                { progress: 40, message: '正在计算位置...' },
                { progress: 60, message: '正在分析偏移...' },
                { progress: 80, message: '正在优化参数...' },
                { progress: 100, message: '校准完成' }
            ];

            const interval = setInterval(() => {
                if (progress < steps.length) {
                    const step = steps[progress];
                    this.emit('alignmentProgress', step);
                    progress++;
                } else {
                    clearInterval(interval);
                    
                    // 模拟校准结果
                    const result = {
                        success: true,
                        azimuthOffset: OGScopeUtils.random(-5, 5),
                        altitudeOffset: OGScopeUtils.random(-3, 3),
                        accuracy: OGScopeUtils.random(0.1, 0.5)
                    };
                    
                    resolve(result);
                }
            }, 1000);
        });
    }

    /**
     * 停止校准
     */
    stopAlignment() {
        if (this.isCalibrating) {
            this.isCalibrating = false;
            this.emit('alignmentStopped');
            console.log('校准已停止');
        }
    }

    /**
     * 重置校准
     */
    resetAlignment() {
        this.calibrationData = {
            azimuthOffset: 0,
            altitudeOffset: 0,
            accuracy: 0,
            lastUpdate: null
        };
        
        this.saveCalibrationData();
        this.emit('alignmentReset');
        console.log('校准数据已重置');
    }

    /**
     * 获取校准状态
     * @returns {Object} 校准状态
     */
    getAlignmentStatus() {
        return {
            isCalibrating: this.isCalibrating,
            calibrationData: this.calibrationData,
            targetPosition: this.targetPosition,
            currentPosition: this.currentPosition
        };
    }

    /**
     * 设置目标位置
     * @param {Object} position - 目标位置 {azimuth, altitude}
     */
    setTargetPosition(position) {
        this.targetPosition = { ...position };
        this.emit('targetPositionChanged', this.targetPosition);
        console.log('目标位置已设置:', this.targetPosition);
    }

    /**
     * 更新当前位置
     * @param {Object} position - 当前位置 {azimuth, altitude}
     */
    updateCurrentPosition(position) {
        this.currentPosition = { ...position };
        this.emit('currentPositionChanged', this.currentPosition);
    }

    /**
     * 计算偏移量
     * @returns {Object} 偏移量 {azimuth, altitude}
     */
    calculateOffset() {
        const azimuthOffset = this.targetPosition.azimuth - this.currentPosition.azimuth;
        const altitudeOffset = this.targetPosition.altitude - this.currentPosition.altitude;
        
        return {
            azimuth: azimuthOffset,
            altitude: altitudeOffset
        };
    }

    /**
     * 检查校准精度
     * @returns {Object} 精度信息
     */
    checkAccuracy() {
        const offset = this.calculateOffset();
        const totalOffset = Math.sqrt(
            Math.pow(offset.azimuth, 2) + Math.pow(offset.altitude, 2)
        );
        
        let accuracy = 'excellent';
        if (totalOffset > 2) {
            accuracy = 'poor';
        } else if (totalOffset > 1) {
            accuracy = 'fair';
        } else if (totalOffset > 0.5) {
            accuracy = 'good';
        }
        
        return {
            totalOffset,
            accuracy,
            azimuthOffset: offset.azimuth,
            altitudeOffset: offset.altitude
        };
    }

    /**
     * 开始数据更新
     */
    startDataUpdates() {
        this.updateInterval = setInterval(() => {
            this.updateAlignmentData();
        }, OGScopeConstants.APP_CONSTANTS.UPDATE_INTERVALS.OFFSET);
    }

    /**
     * 停止数据更新
     */
    stopDataUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    /**
     * 更新校准数据
     */
    updateAlignmentData() {
        // 模拟数据更新
        const offset = this.calculateOffset();
        
        // 更新UI显示
        this.updateOffsetDisplay(offset);
        
        // 更新校准数据
        this.calibrationData.azimuthOffset = offset.azimuth;
        this.calibrationData.altitudeOffset = offset.altitude;
        this.calibrationData.lastUpdate = new Date();
        
        this.emit('alignmentDataUpdated', this.calibrationData);
    }

    /**
     * 更新偏移显示
     * @param {Object} offset - 偏移量
     */
    updateOffsetDisplay(offset) {
        const azimuthElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.AZIMUTH_OFFSET);
        const altitudeElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.ALTITUDE_OFFSET);
        
        if (azimuthElement) {
            azimuthElement.textContent = `${offset.azimuth >= 0 ? '+' : ''}${offset.azimuth.toFixed(1)}°`;
        }
        
        if (altitudeElement) {
            altitudeElement.textContent = `${offset.altitude >= 0 ? '+' : ''}${offset.altitude.toFixed(1)}°`;
        }
    }

    /**
     * 保存校准数据
     */
    saveCalibrationData() {
        try {
            localStorage.setItem(
                OGScopeConstants.STORAGE_KEYS.CALIBRATION_DATA,
                JSON.stringify(this.calibrationData)
            );
        } catch (error) {
            console.error('保存校准数据失败:', error);
        }
    }

    /**
     * 加载校准数据
     */
    loadCalibrationData() {
        try {
            const savedData = localStorage.getItem(
                OGScopeConstants.STORAGE_KEYS.CALIBRATION_DATA
            );
            
            if (savedData) {
                this.calibrationData = JSON.parse(savedData);
                console.log('校准数据已加载:', this.calibrationData);
            }
        } catch (error) {
            console.error('加载校准数据失败:', error);
        }
    }

    /**
     * 导出校准数据
     * @returns {Object} 校准数据
     */
    exportCalibrationData() {
        return {
            ...this.calibrationData,
            targetPosition: this.targetPosition,
            currentPosition: this.currentPosition,
            exportTime: new Date().toISOString()
        };
    }

    /**
     * 导入校准数据
     * @param {Object} data - 校准数据
     */
    importCalibrationData(data) {
        if (data.azimuthOffset !== undefined) {
            this.calibrationData.azimuthOffset = data.azimuthOffset;
        }
        if (data.altitudeOffset !== undefined) {
            this.calibrationData.altitudeOffset = data.altitudeOffset;
        }
        if (data.accuracy !== undefined) {
            this.calibrationData.accuracy = data.accuracy;
        }
        if (data.targetPosition) {
            this.targetPosition = data.targetPosition;
        }
        if (data.currentPosition) {
            this.currentPosition = data.currentPosition;
        }
        
        this.calibrationData.lastUpdate = new Date();
        this.saveCalibrationData();
        
        this.emit('calibrationDataImported', this.calibrationData);
        console.log('校准数据已导入:', this.calibrationData);
    }

    /**
     * 获取校准历史
     * @returns {Array} 校准历史
     */
    getCalibrationHistory() {
        try {
            const history = localStorage.getItem('ogscope_calibration_history');
            return history ? JSON.parse(history) : [];
        } catch (error) {
            console.error('获取校准历史失败:', error);
            return [];
        }
    }

    /**
     * 添加校准记录
     * @param {Object} record - 校准记录
     */
    addCalibrationRecord(record) {
        try {
            const history = this.getCalibrationHistory();
            history.push({
                ...record,
                timestamp: new Date().toISOString()
            });
            
            // 只保留最近50条记录
            if (history.length > 50) {
                history.splice(0, history.length - 50);
            }
            
            localStorage.setItem('ogscope_calibration_history', JSON.stringify(history));
        } catch (error) {
            console.error('添加校准记录失败:', error);
        }
    }

    /**
     * 清除校准历史
     */
    clearCalibrationHistory() {
        try {
            localStorage.removeItem('ogscope_calibration_history');
            console.log('校准历史已清除');
        } catch (error) {
            console.error('清除校准历史失败:', error);
        }
    }

    /**
     * 添加事件监听器
     * @param {string} event - 事件名
     * @param {Function} callback - 回调函数
     */
    on(event, callback) {
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, []);
        }
        this.eventListeners.get(event).push(callback);
    }

    /**
     * 移除事件监听器
     * @param {string} event - 事件名
     * @param {Function} callback - 回调函数
     */
    off(event, callback) {
        if (this.eventListeners.has(event)) {
            const callbacks = this.eventListeners.get(event);
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
        if (this.eventListeners.has(event)) {
            this.eventListeners.get(event).forEach(callback => {
                try {
                    callback(...args);
                } catch (error) {
                    console.error('校准事件回调执行失败:', error);
                }
            });
        }
    }

    /**
     * 销毁校准控制器
     */
    destroy() {
        this.stopDataUpdates();
        this.eventListeners.clear();
        this.isCalibrating = false;
    }
}

// 创建校准控制器实例
const alignmentController = new AlignmentController();

// 导出校准控制器
window.OGScopeAlignment = {
    AlignmentController,
    alignmentController
};