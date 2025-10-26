/* OGScope - 主应用 */

/**
 * OGScope主应用类
 */
class OGScopeApp {
    constructor() {
        this.isInitialized = false;
        this.isLoaded = false;
        this.loadingProgress = 0;
        this.loadingSteps = [
            { progress: 20, text: '正在连接设备...' },
            { progress: 40, text: '正在初始化相机...' },
            { progress: 60, text: '正在加载视频流...' },
            { progress: 80, text: '正在加载组件...' },
            { progress: 100, text: '加载完成' }
        ];
        this.currentStep = 0;
        this.loadingInterval = null;
        this.dataUpdateInterval = null;
        this.init();
    }

    /**
     * 初始化应用
     */
    async init() {
        try {
            console.log('OGScope应用初始化开始...');
            
            // 显示加载屏幕
            this.showLoadingScreen();
            
            // 开始加载过程
            await this.startLoadingProcess();
            
            // 初始化各个模块
            await this.initializeModules();
            
            // 设置事件监听
            this.setupEventListeners();
            
            // 开始数据更新
            this.startDataUpdates();
            
            // 隐藏加载屏幕
            this.hideLoadingScreen();
            
            this.isInitialized = true;
            this.isLoaded = true;
            
            console.log('OGScope应用初始化完成');
            
        } catch (error) {
            console.error('应用初始化失败:', error);
            this.handleInitializationError(error);
        }
    }

    /**
     * 显示加载屏幕
     */
    showLoadingScreen() {
        const loadingScreen = document.getElementById(OGScopeConstants.ELEMENT_IDS.LOADING_SCREEN);
        if (loadingScreen) {
            loadingScreen.classList.remove(OGScopeConstants.CSS_CLASSES.HIDDEN);
        }
    }

    /**
     * 隐藏加载屏幕
     */
    hideLoadingScreen() {
        const loadingScreen = document.getElementById(OGScopeConstants.ELEMENT_IDS.LOADING_SCREEN);
        const app = document.getElementById(OGScopeConstants.ELEMENT_IDS.APP);
        
        if (loadingScreen) {
            loadingScreen.classList.add(OGScopeConstants.CSS_CLASSES.HIDDEN);
        }
        
        if (app) {
            app.classList.add(OGScopeConstants.CSS_CLASSES.LOADED);
        }
    }

    /**
     * 开始加载过程
     */
    async startLoadingProcess() {
        return new Promise((resolve) => {
            this.loadingInterval = setInterval(() => {
                if (this.currentStep < this.loadingSteps.length) {
                    const step = this.loadingSteps[this.currentStep];
                    this.updateLoadingProgress(step.progress, step.text);
                    this.currentStep++;
                } else {
                    clearInterval(this.loadingInterval);
                    setTimeout(resolve, 500);
                }
            }, 600);
        });
    }

    /**
     * 更新加载进度
     * @param {number} progress - 进度百分比
     * @param {string} text - 状态文本
     */
    updateLoadingProgress(progress, text) {
        this.loadingProgress = progress;
        
        const progressBar = document.getElementById(OGScopeConstants.ELEMENT_IDS.PROGRESS_BAR);
        const loadingStatus = document.getElementById(OGScopeConstants.ELEMENT_IDS.LOADING_STATUS);
        
        if (progressBar) {
            progressBar.style.width = progress + '%';
        }
        
        if (loadingStatus) {
            loadingStatus.textContent = text;
        }
    }

    /**
     * 初始化各个模块
     */
    async initializeModules() {
        try {
            // 初始化相机
            if (window.OGScopeCamera && window.OGScopeCamera.cameraController) {
                await window.OGScopeCamera.cameraController.initVideoStream();
            }
            
            // 初始化校准
            if (window.OGScopeAlignment && window.OGScopeAlignment.alignmentController) {
                // 校准模块已在构造函数中初始化
            }
            
            // 初始化UI
            if (window.OGScopeUI && window.OGScopeUI.uiController) {
                // UI模块已在构造函数中初始化
            }
            
            console.log('所有模块初始化完成');
        } catch (error) {
            console.error('模块初始化失败:', error);
            throw error;
        }
    }

    /**
     * 设置事件监听
     */
    setupEventListeners() {
        // 监听相机事件
        if (window.OGScopeCamera && window.OGScopeCamera.cameraController) {
            window.OGScopeCamera.cameraController.on('streamInitialized', () => {
                console.log('视频流初始化成功');
            });
            
            window.OGScopeCamera.cameraController.on('streamError', (error) => {
                console.error('视频流错误:', error);
            });
        }
        
        // 监听校准事件
        if (window.OGScopeAlignment && window.OGScopeAlignment.alignmentController) {
            window.OGScopeAlignment.alignmentController.on('alignmentComplete', (data) => {
                console.log('校准完成:', data);
            });
            
            window.OGScopeAlignment.alignmentController.on('alignmentError', (error) => {
                console.error('校准错误:', error);
            });
        }
        
        // 监听窗口事件
        window.addEventListener('beforeunload', () => {
            this.cleanup();
        });
        
        window.addEventListener('error', (event) => {
            console.error('全局错误:', event.error);
        });
        
        window.addEventListener('unhandledrejection', (event) => {
            console.error('未处理的Promise拒绝:', event.reason);
        });
    }

    /**
     * 开始数据更新
     */
    startDataUpdates() {
        this.dataUpdateInterval = setInterval(() => {
            this.updateSystemData();
        }, 2000);
    }

    /**
     * 更新系统数据
     */
    updateSystemData() {
        // 更新GPS坐标
        this.updateGPSData();
        
        // 更新海拔
        this.updateAltitudeData();
        
        // 更新信号强度
        this.updateSignalData();
        
        // 更新电池信息
        this.updateBatteryData();
        
        // 更新图像质量
        this.updateImageQuality();
        
        // 更新引导线
        this.updateGuideLine();
    }

    /**
     * 更新GPS数据
     */
    updateGPSData() {
        const gpsElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.GPS_COORD);
        if (gpsElement) {
            // 模拟GPS坐标更新
            const lat = 39.9042 + OGScopeUtils.random(-0.01, 0.01);
            const lon = 116.4074 + OGScopeUtils.random(-0.01, 0.01);
            
            const latDeg = Math.floor(lat);
            const latMin = Math.floor((lat - latDeg) * 60);
            const latSec = Math.floor(((lat - latDeg) * 60 - latMin) * 60);
            
            const lonDeg = Math.floor(lon);
            const lonMin = Math.floor((lon - lonDeg) * 60);
            const lonSec = Math.floor(((lon - lonDeg) * 60 - lonMin) * 60);
            
            gpsElement.textContent = `${latDeg}°${latMin}'${latSec}"N &nbsp;&nbsp; ${lonDeg}°${lonMin}'${lonSec}"E`;
        }
    }

    /**
     * 更新海拔数据
     */
    updateAltitudeData() {
        const altitudeElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.ALTITUDE);
        if (altitudeElement) {
            // 模拟海拔更新
            const altitude = 43.8 + OGScopeUtils.random(-2, 2);
            altitudeElement.textContent = `${altitude.toFixed(1)} m`;
        }
    }

    /**
     * 更新信号数据
     */
    updateSignalData() {
        // WiFi信号
        const wifiElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.WIFI_STRENGTH);
        if (wifiElement) {
            const wifiStrength = OGScopeUtils.randomInt(80, 100);
            wifiElement.textContent = `${wifiStrength}%`;
        }
        
        // GPS信号
        const gpsElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.GPS_STRENGTH);
        if (gpsElement) {
            const gpsStrength = OGScopeUtils.randomInt(90, 100);
            gpsElement.textContent = `${gpsStrength}%`;
        }
    }

    /**
     * 更新电池数据
     */
    updateBatteryData() {
        const batteryElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.BATTERY_LEVEL);
        if (batteryElement) {
            // 模拟电池电量更新
            const batteryLevel = OGScopeUtils.randomInt(75, 95);
            batteryElement.textContent = `${batteryLevel}%`;
        }
    }

    /**
     * 更新图像质量
     */
    updateImageQuality() {
        const qualityFillElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.QUALITY_FILL);
        const qualityValueElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.QUALITY_VALUE);
        
        if (qualityFillElement && qualityValueElement) {
            // 模拟图像质量更新
            const quality = OGScopeUtils.randomInt(70, 95);
            qualityFillElement.style.width = quality + '%';
            
            let qualityText = '一般';
            if (quality > 85) {
                qualityText = '优秀';
            } else if (quality > 75) {
                qualityText = '良好';
            }
            
            qualityValueElement.textContent = qualityText;
        }
    }

    /**
     * 更新引导线
     */
    updateGuideLine() {
        const guideLine = document.querySelector('.guide-line');
        if (guideLine) {
            // 模拟引导线角度更新
            const angle = (Date.now() / 50) % 360;
            guideLine.style.transform = `translate(-50%, 0) rotate(${angle}deg)`;
        }
    }

    /**
     * 处理初始化错误
     * @param {Error} error - 错误对象
     */
    handleInitializationError(error) {
        console.error('应用初始化失败:', error);
        
        // 显示错误信息
        const loadingStatus = document.getElementById(OGScopeConstants.ELEMENT_IDS.LOADING_STATUS);
        if (loadingStatus) {
            loadingStatus.textContent = '初始化失败，请刷新页面重试';
            loadingStatus.style.color = '#ff4444';
        }
        
        // 可以在这里添加错误恢复逻辑
        setTimeout(() => {
            console.log('尝试重新初始化...');
            this.init();
        }, 5000);
    }

    /**
     * 获取应用状态
     * @returns {Object} 应用状态
     */
    getAppStatus() {
        return {
            isInitialized: this.isInitialized,
            isLoaded: this.isLoaded,
            loadingProgress: this.loadingProgress,
            currentStep: this.currentStep,
            modules: {
                camera: window.OGScopeCamera ? window.OGScopeCamera.cameraController.isInitialized : false,
                alignment: window.OGScopeAlignment ? window.OGScopeAlignment.alignmentController.isCalibrating : false,
                ui: window.OGScopeUI ? true : false
            }
        };
    }

    /**
     * 重启应用
     */
    async restart() {
        console.log('重启应用...');
        
        // 清理资源
        this.cleanup();
        
        // 重置状态
        this.isInitialized = false;
        this.isLoaded = false;
        this.loadingProgress = 0;
        this.currentStep = 0;
        
        // 重新初始化
        await this.init();
    }

    /**
     * 清理资源
     */
    cleanup() {
        console.log('清理应用资源...');
        
        // 清理定时器
        if (this.loadingInterval) {
            clearInterval(this.loadingInterval);
            this.loadingInterval = null;
        }
        
        if (this.dataUpdateInterval) {
            clearInterval(this.dataUpdateInterval);
            this.dataUpdateInterval = null;
        }
        
        // 清理各个模块
        if (window.OGScopeCamera && window.OGScopeCamera.cameraController) {
            window.OGScopeCamera.cameraController.destroy();
        }
        
        if (window.OGScopeAlignment && window.OGScopeAlignment.alignmentController) {
            window.OGScopeAlignment.alignmentController.destroy();
        }
        
        if (window.OGScopeUI && window.OGScopeUI.uiController) {
            window.OGScopeUI.uiController.destroy();
        }
    }
}

// 等待DOM加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM加载完成，开始初始化OGScope应用...');
    
    // 创建应用实例
    const app = new OGScopeApp();
    
    // 将应用实例挂载到全局对象
    window.OGScopeApp = app;
    
    // 添加全局错误处理
    window.addEventListener('error', (event) => {
        console.error('全局错误:', event.error);
    });
    
    window.addEventListener('unhandledrejection', (event) => {
        console.error('未处理的Promise拒绝:', event.reason);
    });
    
    console.log('OGScope应用已启动');
});