/**
 * OGScope 调试控制台 JavaScript
 * 提供相机调试、拍摄控制、参数设置等功能
 */

class DebugConsole {
    constructor() {
        this.cameraStatus = {
            connected: false,
            streaming: false,
            recording: false
        };
        this.previewActive = false;
        
        this.currentSettings = {
            exposure: 10000,
            gain: 1.0,
            digitalGain: 1.0,
            rotation: 180
        };
        
        // 直方图相关设置
        this.histogramSettings = {
            visible: false,
            showRGB: true,
            showLuminance: false,
            showOverexposure: false,
            panelVisible: false
        };
        
        this.presets = [];
        this.files = [];
        this.recordingStartTime = null;
        this.recordingInterval = null;
        this.statusInterval = null;
        
        // 实时数据流分析
        this.streamStats = {
            frameCount: 0,
            lastFrameTime: null,
            fpsCalculated: 0.0,
            resolutionDetected: null,
            dataSize: 0,
            avgFrameSize: 0,
            frameTimes: [],
            startTime: null
        };
        
        // 网络带宽监控
        this.networkStats = {
            startTime: null,
            lastCheckTime: null,
            totalBytesTransferred: 0,
            bytesPerSecond: 0,
            lastBytesCount: 0,
            checkInterval: 2000, // 每2秒检查一次，监控下行流量
            isMonitoring: false
        };
        
        this.init();
    }
    
    /**
     * 分析实时数据流
     */
    analyzeStreamData(imageElement) {
        const currentTime = performance.now();
        
        // 记录开始时间
        if (this.streamStats.startTime === null) {
            this.streamStats.startTime = currentTime;
        }
        
        // 更新帧计数
        this.streamStats.frameCount++;
        
        // 注意：数据大小现在通过网络监控获取，不再需要手动计算
        
        // 检测分辨率并调整容器宽高比
        if (imageElement && imageElement.naturalWidth && imageElement.naturalHeight) {
            const detectedRes = `${imageElement.naturalWidth}x${imageElement.naturalHeight}`;
            if (this.streamStats.resolutionDetected !== detectedRes) {
                this.streamStats.resolutionDetected = detectedRes;
                console.log(`[Stream] 检测到分辨率: ${detectedRes}`);
                this.updateVideoContainerAspectRatio(imageElement.naturalWidth, imageElement.naturalHeight);
            }
        }
        
        // 计算帧率
        if (this.streamStats.lastFrameTime !== null) {
            const timeDiff = currentTime - this.streamStats.lastFrameTime;
            // 忽略过小的时间差（可能由浏览器缓存/事件合并导致的“超高FPS”）
            if (timeDiff > 10) {
                let fps = 1000 / timeDiff; // 转换为每秒帧数
                // 上限保护：以相机报告 fps 的 2 倍或默认 10fps 作为硬上限
                const reported = (this.cameraStatus?.info?.fps) || 5;
                const fpsCap = Math.max(10, reported * 2);
                if (fps > fpsCap) fps = fpsCap;
                this.streamStats.frameTimes.push(fps);
                
                // 保持最近10帧的FPS数据
                if (this.streamStats.frameTimes.length > 10) {
                    this.streamStats.frameTimes.shift();
                }
                
                // 计算平均FPS
                const avgFps = this.streamStats.frameTimes.reduce((a, b) => a + b, 0) / this.streamStats.frameTimes.length;
                this.streamStats.fpsCalculated = avgFps;
            }
        }
        
        this.streamStats.lastFrameTime = currentTime;
        
        // 更新UI显示
        this.updateStreamStatsDisplay();
    }
    
    /**
     * 计算帧数据大小
     */
    calculateFrameDataSize(imageElement) {
        try {
            let frameSize = 0;
            
            // 方法1: 尝试获取真实的图像数据大小
            const realSize = this.tryGetRealImageSize(imageElement);
            if (realSize > 0) {
                frameSize = realSize;
            } else {
                // 方法2: 尝试从图片的src URL获取数据大小
                if (imageElement.src) {
                    if (imageElement.src.startsWith('data:')) {
                        // 对于base64编码的图片，计算实际数据大小
                        const base64Data = imageElement.src.split(',')[1];
                        if (base64Data) {
                            frameSize = (base64Data.length * 3) / 4; // base64解码后的大小
                        }
                    } else if (imageElement.src.startsWith('blob:')) {
                        // 对于blob URL，使用基于分辨率的估算
                        frameSize = this.estimateFrameSizeFromResolution(imageElement);
                    } else {
                        // 对于普通URL，使用基于分辨率的估算
                        frameSize = this.estimateFrameSizeFromResolution(imageElement);
                    }
                } else {
                    // 使用基于分辨率的估算
                    frameSize = this.estimateFrameSizeFromResolution(imageElement);
                }
            }
            
            // 如果估算失败，使用默认值
            if (frameSize === 0) {
                frameSize = this.getDefaultFrameSize(imageElement);
            }
            
            // 强制确保有数据大小（调试用）
            if (frameSize === 0) {
                frameSize = 25000; // 强制25KB（更合理的默认值）
                console.warn('[DebugConsole] 强制设置帧大小为25KB');
            }
            
            // 更新统计数据
            this.streamStats.dataSize += frameSize;
            this.streamStats.avgFrameSize = this.streamStats.dataSize / this.streamStats.frameCount;
            
            // 调试信息 - 每10帧输出一次，便于调试
            if (this.streamStats.frameCount % 10 === 0) {
                const pixels = imageElement.naturalWidth * imageElement.naturalHeight;
                const bytesPerPixel = pixels > 0 ? (frameSize / pixels).toFixed(3) : 'N/A';
                console.log(`[Stream] 帧 ${this.streamStats.frameCount}: 大小=${this.formatDataSize(frameSize)}, 总计=${this.formatDataSize(this.streamStats.dataSize)}, 分辨率=${imageElement.naturalWidth}x${imageElement.naturalHeight}, 每像素=${bytesPerPixel}B`);
            }
            
        } catch (error) {
            console.warn('[DebugConsole] 计算帧数据大小失败:', error);
            // 使用保守估算
            const fallbackFrameSize = this.getDefaultFrameSize(imageElement);
            this.streamStats.dataSize += fallbackFrameSize;
            this.streamStats.avgFrameSize = this.streamStats.dataSize / this.streamStats.frameCount;
        }
    }
    
    /**
     * 尝试获取真实的图像数据大小
     */
    tryGetRealImageSize(imageElement) {
        try {
            // 方法1: 尝试通过fetch获取图像大小
            if (imageElement.src && !imageElement.src.startsWith('data:')) {
                // 对于HTTP URL，尝试获取Content-Length
                fetch(imageElement.src, { method: 'HEAD' })
                    .then(response => {
                        const contentLength = response.headers.get('content-length');
                        if (contentLength) {
                            console.log(`[Stream] 检测到真实图像大小: ${this.formatDataSize(parseInt(contentLength))}`);
                        }
                    })
                    .catch(() => {
                        // 忽略错误，使用估算值
                    });
            }
            
            // 方法2: 尝试从canvas获取图像数据大小
            if (imageElement.naturalWidth && imageElement.naturalHeight) {
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                canvas.width = imageElement.naturalWidth;
                canvas.height = imageElement.naturalHeight;
                
                ctx.drawImage(imageElement, 0, 0);
                const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                const rawSize = imageData.data.length;
                
                // JPEG压缩比估算：原始数据通常是压缩后数据的10-20倍
                const compressedSize = rawSize / 15; // 假设15:1压缩比
                
                if (compressedSize > 0 && compressedSize < 1000000) { // 小于1MB才认为是合理的
                    return compressedSize;
                }
            }
            
            return 0;
        } catch (error) {
            console.warn('[DebugConsole] 获取真实图像大小失败:', error);
            return 0;
        }
    }
    
    /**
     * 基于分辨率估算帧大小
     */
    estimateFrameSizeFromResolution(imageElement) {
        if (!imageElement.naturalWidth || !imageElement.naturalHeight) {
            return 0;
        }
        
        const width = imageElement.naturalWidth;
        const height = imageElement.naturalHeight;
        const pixels = width * height;
        
        // 更准确的JPEG压缩比估算（基于实际经验）
        // JPEG压缩比通常在10:1到50:1之间，取决于图像复杂度
        let bytesPerPixel;
        if (pixels < 640 * 480) {
            bytesPerPixel = 0.05; // 约50KB for 640x480 (低分辨率，简单压缩)
        } else if (pixels < 1280 * 720) {
            bytesPerPixel = 0.08; // 约75KB for 1280x720
        } else if (pixels < 1920 * 1080) {
            bytesPerPixel = 0.12; // 约250KB for 1920x1080
        } else {
            bytesPerPixel = 0.15; // 更高分辨率
        }
        
        const estimatedSize = pixels * bytesPerPixel;
        
        // 设置合理的上下限
        const minSize = 10000;  // 最小10KB
        const maxSize = 500000; // 最大500KB
        
        return Math.max(minSize, Math.min(maxSize, estimatedSize));
    }
    
    /**
     * 获取默认帧大小
     */
    getDefaultFrameSize(imageElement) {
        // 基于图像尺寸的默认估算
        if (imageElement.naturalWidth && imageElement.naturalHeight) {
            const pixels = imageElement.naturalWidth * imageElement.naturalHeight;
            const estimatedSize = pixels * 0.08; // 更保守的估算
            return Math.max(estimatedSize, 15000); // 最小15KB
        }
        
        // 基于常见分辨率的默认值
        return 30000; // 默认30KB（更合理的估算）
    }
    
    /**
     * 根据相机分辨率动态调整视频容器的宽高比
     * 考虑传感器原生宽高比，避免画面被压缩
     */
    updateVideoContainerAspectRatio(width, height) {
        const videoContainer = document.querySelector('.video-container');
        if (!videoContainer) return;
        
        // IMX327传感器原生宽高比约为16:9 (1945x1097)
        const sensorAspectRatio = 1945 / 1097; // ≈ 1.773
        const outputAspectRatio = width / height;
        
        // 如果输出分辨率与传感器比例差异较大，使用传感器比例
        // 这样可以避免画面被压缩
        let targetAspectRatio;
        if (Math.abs(outputAspectRatio - sensorAspectRatio) > 0.1) {
            // 使用传感器原生比例
            targetAspectRatio = sensorAspectRatio;
            console.log(`[UI] 输出分辨率${width}x${height}与传感器比例差异较大，使用传感器比例: ${sensorAspectRatio.toFixed(3)}`);
        } else {
            // 使用输出分辨率比例
            targetAspectRatio = outputAspectRatio;
            console.log(`[UI] 使用输出分辨率比例: ${width}:${height} (${outputAspectRatio.toFixed(3)})`);
        }
        
        // 设置CSS自定义属性
        videoContainer.style.aspectRatio = `${targetAspectRatio}`;
        
        // 添加视觉反馈
        videoContainer.classList.add('aspect-ratio-changing');
        setTimeout(() => {
            videoContainer.classList.remove('aspect-ratio-changing');
        }, 300);
    }
    
    /**
     * 更新数据流统计显示
     */
    updateStreamStatsDisplay() {
        // 更新分辨率显示
        if (this.streamStats.resolutionDetected) {
            const resolutionElement = document.getElementById('detected-resolution');
            if (resolutionElement) {
                resolutionElement.textContent = this.streamStats.resolutionDetected;
            }
        }
        
        // 更新FPS显示
        const fpsElement = document.getElementById('calculated-fps');
        if (fpsElement) {
            fpsElement.textContent = this.streamStats.fpsCalculated.toFixed(2);
        }
        
        // 更新帧计数显示
        const frameCountElement = document.getElementById('frame-count');
        if (frameCountElement) {
            frameCountElement.textContent = this.streamStats.frameCount;
        }
        
        // 数据大小、传输速率和平均帧大小现在通过网络监控显示
        // 这些数据由 updateNetworkStatsDisplay() 方法更新
        
        // 更新调试信息显示
        const debugInfoElement = document.getElementById('debug-info');
        if (debugInfoElement) {
            const debugText = this.getDebugInfo();
            debugInfoElement.textContent = debugText;
        }
        
        // 更新流状态显示
        const streamStatusElement = document.getElementById('stream-status');
        if (streamStatusElement) {
            const isActive = this.streamStats.lastFrameTime !== null && 
                           (performance.now() - this.streamStats.lastFrameTime) < 5000;
            streamStatusElement.textContent = isActive ? '活跃' : '非活跃';
            streamStatusElement.className = isActive ? 'status-active' : 'status-inactive';
        }
        
        // 更新运行时长显示
        const runtimeElement = document.getElementById('runtime');
        if (runtimeElement && this.streamStats.startTime !== null) {
            const runtime = (performance.now() - this.streamStats.startTime) / 1000;
            runtimeElement.textContent = `${runtime.toFixed(1)}s`;
        }
    }
    
    /**
     * 格式化数据大小显示
     */
    formatDataSize(bytes) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        const value = bytes / Math.pow(k, i);
        return `${value.toFixed(2)} ${sizes[i]}`;
    }
    
    /**
     * 计算传输速率
     */
    calculateTransferRate() {
        if (!this.streamStats.startTime || this.streamStats.frameCount === 0) {
            return '--';
        }
        
        const currentTime = performance.now();
        const elapsedSeconds = (currentTime - this.streamStats.startTime) / 1000;
        
        if (elapsedSeconds === 0) return '--';
        
        const bytesPerSecond = this.streamStats.dataSize / elapsedSeconds;
        return `${this.formatDataSize(bytesPerSecond)}/s`;
    }
    
    /**
     * 获取调试信息
     */
    getDebugInfo() {
        if (this.streamStats.frameCount === 0) {
            return '无数据';
        }
        
        const lastFrameTime = this.streamStats.lastFrameTime ? 
            Math.round((performance.now() - this.streamStats.lastFrameTime)) : '--';
        
        return `上次更新:${lastFrameTime}ms`;
    }
    
    /**
     * 启动网络带宽监控
     */
    startNetworkMonitoring() {
        if (this.networkStats.isMonitoring) return;
        
        this.networkStats.isMonitoring = true;
        this.networkStats.startTime = performance.now();
        this.networkStats.lastCheckTime = performance.now();
        
        console.log('[DebugConsole] 启动下行流量监控');
        
        // 使用Performance API监控网络活动
        this.networkMonitoringInterval = setInterval(() => {
            this.updateNetworkStats();
        }, this.networkStats.checkInterval);
    }
    
    /**
     * 停止网络带宽监控
     */
    stopNetworkMonitoring() {
        if (!this.networkStats.isMonitoring) return;
        
        this.networkStats.isMonitoring = false;
        
        if (this.networkMonitoringInterval) {
            clearInterval(this.networkMonitoringInterval);
            this.networkMonitoringInterval = null;
        }
        
        console.log('[DebugConsole] 停止下行流量监控');
    }
    
    /**
     * 更新网络统计信息
     */
    updateNetworkStats() {
        try {
            const currentTime = performance.now();
            
            // 使用Performance API获取网络资源信息
            const resources = performance.getEntriesByType('resource');
            const currentBytesCount = this.estimateTotalTransferSize(resources);
            
            if (this.networkStats.lastBytesCount > 0) {
                const timeDiff = (currentTime - this.networkStats.lastCheckTime) / 1000; // 转换为秒
                const bytesDiff = currentBytesCount - this.networkStats.lastBytesCount;
                
                if (timeDiff > 0) {
                    this.networkStats.bytesPerSecond = bytesDiff / timeDiff;
                    this.networkStats.totalBytesTransferred += bytesDiff;
                }
            }
            
            this.networkStats.lastBytesCount = currentBytesCount;
            this.networkStats.lastCheckTime = currentTime;
            
            // 更新UI显示
            this.updateNetworkStatsDisplay();
            
            // 调试信息：每10次检查输出一次详细信息
            if (this.networkStats.totalBytesTransferred > 0 && 
                Math.floor(currentTime / (this.networkStats.checkInterval * 10)) !== 
                Math.floor(this.networkStats.lastCheckTime / (this.networkStats.checkInterval * 10))) {
                const resources = performance.getEntriesByType('resource');
                const cameraResources = resources.filter(resource => {
                    const url = resource.name;
                    return url.includes('/api/debug/camera/');
                });
                console.log(`[DebugConsole] 下行流量统计: 总计=${this.formatDataSize(this.networkStats.totalBytesTransferred)}, 速率=${this.formatDataSize(this.networkStats.bytesPerSecond)}/s, 相机资源数=${cameraResources.length}`);
            }
            
        } catch (error) {
            console.warn('[DebugConsole] 更新网络统计失败:', error);
        }
    }
    
    /**
     * 估算总下行传输大小（接收的数据）
     */
    estimateTotalTransferSize(resources) {
        let totalSize = 0;
        
        // 只计算最近的资源（避免计算所有历史资源）
        const recentResources = resources.filter(resource => {
            const resourceTime = resource.startTime;
            const currentTime = performance.now();
            return (currentTime - resourceTime) < 30000; // 只计算最近30秒的资源
        });
        
        // 过滤出相机相关的资源（主要是图像数据）
        const cameraResources = recentResources.filter(resource => {
            const url = resource.name;
            return url.includes('/api/debug/camera/preview') || 
                   url.includes('/api/debug/camera/capture') ||
                   url.includes('/api/debug/camera/size') ||
                   url.includes('/api/debug/camera/fps') ||
                   url.includes('/api/debug/camera/sampling') ||
                   (url.includes('preview') && url.includes('/api/debug/')) ||
                   (url.includes('capture') && url.includes('/api/debug/'));
        });
        
        cameraResources.forEach(resource => {
            // 优先使用transferSize（实际传输大小），其次使用decodedBodySize（解码后大小）
            if (resource.transferSize && resource.transferSize > 0) {
                totalSize += resource.transferSize;
            } else if (resource.decodedBodySize && resource.decodedBodySize > 0) {
                totalSize += resource.decodedBodySize;
            }
        });
        
        return totalSize;
    }
    
    /**
     * 更新网络统计显示
     */
    updateNetworkStatsDisplay() {
        // 更新数据大小显示
        const dataSizeElement = document.getElementById('data-size');
        if (dataSizeElement) {
            const dataSizeText = this.formatDataSize(this.networkStats.totalBytesTransferred);
            dataSizeElement.textContent = dataSizeText;
        }
        
        // 更新传输速率显示
        const transferRateElement = document.getElementById('transfer-rate');
        if (transferRateElement) {
            const transferRateText = this.formatDataSize(this.networkStats.bytesPerSecond) + '/s';
            transferRateElement.textContent = transferRateText;
        }
        
        // 更新平均帧大小显示
        const avgFrameSizeElement = document.getElementById('avg-frame-size');
        if (avgFrameSizeElement) {
            if (this.streamStats.frameCount > 0 && this.networkStats.totalBytesTransferred > 0) {
                const avgFrameSize = this.networkStats.totalBytesTransferred / this.streamStats.frameCount;
                const avgFrameSizeText = this.formatDataSize(avgFrameSize);
                avgFrameSizeElement.textContent = avgFrameSizeText;
            } else {
                avgFrameSizeElement.textContent = '--';
            }
        }
    }
    
    /**
     * 重置数据流统计
     */
    resetStreamStats() {
        this.streamStats = {
            frameCount: 0,
            lastFrameTime: null,
            fpsCalculated: 0.0,
            resolutionDetected: null,
            dataSize: 0,
            avgFrameSize: 0,
            frameTimes: [],
            startTime: null
        };
        
        // 重置网络统计
        this.networkStats = {
            startTime: null,
            lastCheckTime: null,
            totalBytesTransferred: 0,
            bytesPerSecond: 0,
            lastBytesCount: 0,
            checkInterval: 2000,
            isMonitoring: false
        };
        
        this.updateStreamStatsDisplay();
    }
    
    /**
     * 重置网络统计（用于分辨率切换）
     */
    resetNetworkStatsForResolutionChange() {
        // 重置网络统计数据，但保持监控状态
        if (this.networkStats.isMonitoring) {
            this.networkStats.totalBytesTransferred = 0;
            this.networkStats.bytesPerSecond = 0;
            this.networkStats.lastBytesCount = 0;
            this.networkStats.startTime = performance.now();
            this.networkStats.lastCheckTime = performance.now();
            
            // 清除旧的网络资源记录，避免影响新的统计
            if (performance.clearResourceTimings) {
                performance.clearResourceTimings();
            }
            
            console.log('[DebugConsole] 分辨率切换后重置网络统计');
        }
    }
    
    /**
     * 设置画面旋转角度
     */
    async setRotation(rotation) {
        try {
            const response = await fetch(`/api/debug/camera/rotation/${rotation}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            if (result.success) {
                this.currentSettings.rotation = rotation;
                this.updateRotationDisplay();
                this.showNotification(result.message, 'success');
            } else {
                throw new Error(result.message || '设置旋转失败');
            }
        } catch (error) {
            console.error('设置旋转失败:', error);
            this.showNotification(`设置旋转失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 更新旋转角度显示
     */
    updateRotationDisplay() {
        // 更新当前角度显示
        const rotationElement = document.getElementById('current-rotation');
        if (rotationElement) {
            rotationElement.textContent = `${this.currentSettings.rotation}°`;
        }
        
        // 更新按钮状态
        document.querySelectorAll('[data-rotation]').forEach(button => {
            const buttonRotation = parseInt(button.dataset.rotation);
            if (buttonRotation === this.currentSettings.rotation) {
                button.classList.remove('btn-secondary');
                button.classList.add('btn-primary');
            } else {
                button.classList.remove('btn-primary');
                button.classList.add('btn-secondary');
            }
        });
    }
    
    /**
     * 初始化调试控制台
     */
    async init() {
        console.log('[DebugConsole] 初始化调试控制台...');
        
        // 设置事件监听器
        this.setupEventListeners();
        
        // 初始化UI
        this.initUI();
        
        // 初始化直方图
        this.initHistogram();
        
        // 加载数据
        await this.loadPresets();
        await this.loadFiles();
        
        // 更新相机状态
        await this.updateCameraStatus();
        
        console.log('[DebugConsole] 调试控制台初始化完成');
    }
    
    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 标签页切换
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });
        
        // 相机控制
        document.getElementById('start-preview')?.addEventListener('click', () => {
            this.startPreview();
        });
        
        document.getElementById('stop-preview')?.addEventListener('click', () => {
            this.stopPreview();
        });
        
        // 拍摄控制
        document.getElementById('capture-image')?.addEventListener('click', () => {
            this.captureImage();
        });
        
        document.getElementById('start-recording')?.addEventListener('click', () => {
            this.startRecording();
        });
        
        document.getElementById('stop-recording')?.addEventListener('click', () => {
            this.stopRecording();
        });
        
        // 参数设置
        document.getElementById('exposure-setting')?.addEventListener('input', (e) => {
            this.updateExposureDisplay(parseInt(e.target.value));
        });
        
        document.getElementById('gain-setting')?.addEventListener('input', (e) => {
            this.updateGainDisplay(parseFloat(e.target.value));
        });
        
        document.getElementById('digital-gain-setting')?.addEventListener('input', (e) => {
            this.updateDigitalGainDisplay(parseFloat(e.target.value));
        });
        
        document.getElementById('apply-settings')?.addEventListener('click', () => {
            this.applySettings();
        });
        
        document.getElementById('reset-settings')?.addEventListener('click', () => {
            this.resetSettings();
        });
        
        // 预设管理
        document.getElementById('save-preset')?.addEventListener('click', () => {
            this.savePreset();
        });
        
        // 文件管理
        document.getElementById('refresh-files')?.addEventListener('click', () => {
            this.loadFiles();
        });
        
        // 设置重置统计按钮事件监听器
        document.getElementById('reset-stats')?.addEventListener('click', () => {
            this.resetStreamStats();
        });
        
        // 设置旋转控制按钮事件监听器
        document.querySelectorAll('[data-rotation]').forEach(button => {
            button.addEventListener('click', (e) => {
                const rotation = parseInt(e.target.dataset.rotation);
                this.setRotation(rotation);
            });
        });
        
        // 分辨率预设选择
        document.querySelectorAll('[data-res]').forEach(button => {
            button.addEventListener('click', (e) => {
                document.querySelectorAll('[data-res]').forEach(b=>b.classList.remove('btn-primary'));
                e.currentTarget.classList.add('btn-primary');
            });
        });
        // 应用分辨率（仅宽高，不影响帧率）
        document.getElementById('apply-resolution')?.addEventListener('click', () => {
            const activeBtn = document.querySelector('[data-res].btn-primary');
            if (!activeBtn) {
                this.showNotification('请选择分辨率预设', 'warning');
                return;
            }
            const [w, h] = activeBtn.dataset.res.split('x').map(v=>parseInt(v));
            this.applySizeOnly(w, h);
        });

        // 应用单独帧率
        document.getElementById('apply-fps')?.addEventListener('click', async () => {
            const fpsInput = document.getElementById('fps-input');
            const fps = parseInt(fpsInput?.value || '5');
            const btn = document.getElementById('apply-fps');
            
            if (!Number.isFinite(fps) || fps <= 0) {
                this.showNotification('请输入有效的帧率', 'warning');
                return;
            }
            try {
                if (btn) btn.disabled = true;
                this.showNotification('正在设置帧率...', 'info');
                
                // 尽量不中断预览直接应用
                const params = new URLSearchParams({ fps: String(fps) });
                const resp = await fetch(`/api/debug/camera/fps?${params.toString()}`, { method: 'POST' });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || '设置帧率失败');
                }
                this.showNotification('帧率已应用', 'success');
                await this.updateCameraStatus();
            } catch (e) {
                console.error(e);
                this.showNotification(`设置帧率失败: ${e.message}`, 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        });

        // 应用采样模式
        document.getElementById('apply-sampling')?.addEventListener('click', async () => {
            const sel = document.getElementById('sampling-select');
            const mode = sel?.value || 'supersample';
            const btn = document.getElementById('apply-sampling');
            
            try {
                if (btn) btn.disabled = true;
                this.showNotification('正在切换采样模式...', 'info');
                
                // 停止预览以避免旧源卡住
                try { await this.stopPreview(); } catch(_){}
                const params = new URLSearchParams({ mode });
                const resp = await fetch(`/api/debug/camera/sampling?${params.toString()}`, { method: 'POST' });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || '设置采样模式失败');
                }
                this.showNotification('采样模式已切换', 'success');
                // 刷新状态并重启预览
                await this.updateCameraStatus();
                await this.startPreview();
            } catch (e) {
                console.error(e);
                this.showNotification(`设置采样模式失败: ${e.message}`, 'error');
                // 尝试恢复预览
                try {
                    await this.updateCameraStatus();
                    if (this.cameraStatus.streaming) {
                        await this.startPreview();
                    }
                } catch (recoveryError) {
                    console.error('[apply-sampling] recovery failed:', recoveryError);
                }
            } finally {
                if (btn) btn.disabled = false;
            }
        });
        
        // 直方图控制
        document.getElementById('histogram-toggle')?.addEventListener('click', () => {
            this.toggleHistogram();
        });
        
        document.getElementById('histogram-settings')?.addEventListener('click', () => {
            this.toggleHistogramPanel();
        });
        
        // 直方图设置选项
        document.getElementById('show-histogram')?.addEventListener('change', (e) => {
            this.histogramSettings.visible = e.target.checked;
            this.updateHistogramVisibility();
        });
        
        document.getElementById('show-rgb')?.addEventListener('change', (e) => {
            this.histogramSettings.showRGB = e.target.checked;
            this.updateHistogramDisplay();
        });
        
        document.getElementById('show-luminance')?.addEventListener('change', (e) => {
            this.histogramSettings.showLuminance = e.target.checked;
            this.updateHistogramDisplay();
        });
        
        document.getElementById('show-overexposure')?.addEventListener('change', (e) => {
            this.histogramSettings.showOverexposure = e.target.checked;
            this.updateHistogramDisplay();
        });
        
        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            this.handleKeyboardShortcuts(e);
        });

        // 启动时同步一次边框状态
        this.setRecOverlay(this.cameraStatus.recording);
    }
    
    /**
     * 初始化UI
     */
    initUI() {
        // 设置默认标签页
        this.switchTab('preview');
        
        // 初始化参数显示
        this.updateExposureDisplay(this.currentSettings.exposure);
        this.updateGainDisplay(this.currentSettings.gain);
        this.updateDigitalGainDisplay(this.currentSettings.digitalGain);
        
        // 添加触摸反馈
        document.querySelectorAll('.btn, .tab-button, .control-row input').forEach(element => {
            element.classList.add('touch-feedback');
        });
    }
    
    /**
     * 切换标签页
     */
    switchTab(tabName) {
        // 更新按钮状态
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        
        // 更新内容显示
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `tab-${tabName}`);
        });
        
        // 特殊处理
        if (tabName === 'files') {
            this.loadFiles();
        } else if (tabName === 'presets') {
            this.loadPresets();
        }
    }
    
    /**
     * 更新相机状态
     */
    async updateCameraStatus() {
        try {
            const response = await fetch('/api/debug/camera/status');
            const status = await response.json();
            
            this.cameraStatus = status;
            this.updateStatusUI();
            this.updateInfoUI();
            
            // 如果相机正在运行，且预览未激活，则启动预览循环（避免重复重置统计）
            if (status.streaming && !this.previewActive) {
                this.startPreviewUpdate();
            }
            // 同步录制状态与计时
            if (this.cameraStatus.recording) {
                if (!this.recordingStartTime) {
                    this.recordingStartTime = Date.now();
                    this.startRecordingTimer();
                }
                this.updateRecordingButtons(true);
                this.setRecOverlay(true);
            } else {
                this.stopRecordingTimer();
                this.updateRecordingButtons(false);
                this.setRecOverlay(false);
            }
            
        } catch (error) {
            console.error('[DebugConsole] 获取相机状态失败:', error);
            this.showNotification('获取相机状态失败', 'error');
        }
    }
    
    /**
     * 更新状态UI
     */
    updateStatusUI() {
        const statusIndicator = document.getElementById('camera-status');
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('.status-text');
        
        if (this.cameraStatus.recording) {
            statusDot.className = 'status-dot recording';
            statusText.textContent = '录制中';
        } else if (this.cameraStatus.streaming) {
            statusDot.className = 'status-dot online';
            statusText.textContent = '预览中';
        } else if (this.cameraStatus.connected) {
            statusDot.className = 'status-dot online';
            statusText.textContent = '已连接';
        } else {
            statusDot.className = 'status-dot offline';
            statusText.textContent = '相机离线';
        }
        
        // 更新预览状态
        document.getElementById('preview-status').textContent = 
            this.cameraStatus.streaming ? '运行中' : '未启动';
        
        // 更新录制状态
        document.getElementById('recording-status').textContent = 
            this.cameraStatus.recording ? '录制中' : '未录制';
        
        // 更新按钮状态
        this.updateButtonStates();
    }

    /**
     * 更新分辨率/帧率显示
     */
    updateInfoUI() {
        const resEl = document.getElementById('resolution');
        const fpsEl = document.getElementById('fps');
        const info = this.cameraStatus.info || {};
        const width = info.width || (info.resolution ? parseInt(String(info.resolution).split('x')[0]) : null);
        const height = info.height || (info.resolution ? parseInt(String(info.resolution).split('x')[1]) : null);
        if (width && height) {
            resEl.textContent = `${width}x${height}`;
        } else {
            resEl.textContent = '--';
        }
        fpsEl.textContent = (info.fps || this.cameraStatus.fps || 0) ? `${info.fps || this.cameraStatus.fps}` : '--';
        const samplingEl = document.getElementById('sampling-mode');
        if (samplingEl) samplingEl.textContent = info.sampling_mode || '--';
    }
    
    /**
     * 启动预览
     */
    async startPreview() {
        try {
            const response = await fetch('/api/debug/camera/start', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification('相机预览已启动', 'success');
                this.startPreviewUpdate();
                this.updateButtonStates();
                await this.updateCameraStatus();
                this.beginStatusPolling();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '启动预览失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 启动预览失败:', error);
            this.showNotification(`启动预览失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 停止预览
     */
    async stopPreview() {
        try {
            await fetch('/api/debug/camera/stop', {
                method: 'POST'
            });
            
            this.stopPreviewUpdate();
            this.updateButtonStates();
            await this.updateCameraStatus();
            this.showNotification('相机预览已停止', 'info');
            this.endStatusPolling();
            
        } catch (error) {
            console.error('[DebugConsole] 停止预览失败:', error);
            this.showNotification('停止预览失败', 'error');
        }
    }
    
    /**
     * 开始预览更新
     */
    startPreviewUpdate() {
        this.stopPreviewUpdate(); // 清除现有定时器
        const previewImg = document.getElementById('preview-image');
        const overlay = document.getElementById('preview-overlay');
        if (!previewImg || !overlay) return;

        // 启动前立即隐藏覆盖层，并重置统计，避免提示一直停留
        overlay.classList.add('hidden');
        this.resetStreamStats();
        this.startNetworkMonitoring();

        // 使用单次请求循环（避免并发取消）：每次等上一帧 onload/onerror/超时 后再发起下一帧
        this.previewActive = true;
        const fps = 5;
        const intervalMs = Math.max(1000 / fps, 150);
        let consecutiveFailures = 0;
        let frameToken = 0;

        const loop = () => {
            if (!this.previewActive) return;
            const loader = new Image();
            const startedAt = performance.now();
            const myToken = ++frameToken;

            // 帧超时保护：1.5s 未返回则视为失败，退避重试
            let timeoutId = setTimeout(() => {
                if (!this.previewActive || myToken !== frameToken) return;
                consecutiveFailures++;
                const retryDelay = Math.min(1000, 200 + consecutiveFailures * 200);
                this.previewTimer = setTimeout(loop, retryDelay);
            }, 1500);

            loader.onload = () => {
                // 交换显示源，避免中途取消请求
                previewImg.src = loader.src;
                // 使用previewImg而不是loader进行分析，因为previewImg有naturalWidth/naturalHeight属性
                this.analyzeStreamData(previewImg);
                if (timeoutId) { clearTimeout(timeoutId); timeoutId = null; }
                consecutiveFailures = 0;
                const elapsed = performance.now() - startedAt;
                const delay = Math.max(0, intervalMs - elapsed);
                this.previewTimer = setTimeout(loop, delay);
            };
            loader.onerror = () => {
                // 失败则稍后重试
                if (timeoutId) { clearTimeout(timeoutId); timeoutId = null; }
                consecutiveFailures++;
                const retryDelay = Math.min(1000, 200 + consecutiveFailures * 200);
                this.previewTimer = setTimeout(loop, retryDelay);
            };
            loader.src = `/api/debug/camera/preview?t=${Date.now()}`;
        };
        loop();

        // 看门狗：若3秒未收到帧，强制刷新状态
        this.previewWatchdog = setInterval(() => {
            if (this.streamStats.lastFrameTime === null) return;
            const since = performance.now() - this.streamStats.lastFrameTime;
            if (since > 3000) {
                this.updateCameraStatus();
            }
        }, 1000);
    }
    
    /**
     * 停止预览更新
     */
    stopPreviewUpdate() {
        if (this.previewInterval) {
            clearInterval(this.previewInterval);
            this.previewInterval = null;
        }
        if (this.previewTimer) {
            clearTimeout(this.previewTimer);
            this.previewTimer = null;
        }
        this.previewActive = false;
        if (this.previewWatchdog) {
            clearInterval(this.previewWatchdog);
            this.previewWatchdog = null;
        }
        // 复位预览图片
        const previewImg = document.getElementById('preview-image');
        if (previewImg) {
            try { previewImg.onload = null; previewImg.onerror = null; } catch(_){}
            previewImg.src = '/static/images/placeholder-camera.png';
        }
        // 显示覆盖层
        document.getElementById('preview-overlay').classList.remove('hidden');
        
        // 停止网络监控
        this.stopNetworkMonitoring();
    }
    
    /**
     * 拍摄图片
     */
    async captureImage() {
        if (!this.cameraStatus.streaming) {
            this.showNotification('请先启动相机预览', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/debug/camera/capture', {
                method: 'POST'
            });
            
            if (response.ok) {
                const result = await response.json();
                this.showNotification(`照片已保存: ${result.filename}`, 'success');
                
                // 更新最后拍摄时间
                const now = new Date();
                document.getElementById('last-capture').textContent = 
                    now.toLocaleTimeString();
                
                // 刷新文件列表
                await this.loadFiles();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '拍摄失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 拍摄失败:', error);
            this.showNotification(`拍摄失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 开始录制
     */
    async startRecording() {
        if (!this.cameraStatus.streaming) {
            this.showNotification('请先启动相机预览', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/debug/camera/record/start', {
                method: 'POST'
            });
            
            if (response.ok) {
                const result = await response.json();
                this.showNotification(`开始录制: ${result.filename}`, 'success');
                
                // 开始计时
                this.recordingStartTime = Date.now();
                this.startRecordingTimer();
                
                // 更新按钮状态
                this.updateRecordingButtons(true);
                this.setRecOverlay(true);
                
                // 更新状态
                await this.updateCameraStatus();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '开始录制失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 开始录制失败:', error);
            this.showNotification(`开始录制失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 停止录制
     */
    async stopRecording() {
        try {
            await fetch('/api/debug/camera/record/stop', {
                method: 'POST'
            });
            
            this.showNotification('录制已停止', 'info');
            
            // 停止计时
            this.stopRecordingTimer();
            
            // 更新按钮状态
            this.updateRecordingButtons(false);
            this.setRecOverlay(false);
            
            // 更新状态
            await this.updateCameraStatus();
            
            // 刷新文件列表
            await this.loadFiles();
            
        } catch (error) {
            console.error('[DebugConsole] 停止录制失败:', error);
            this.showNotification('停止录制失败', 'error');
        }
    }
    
    /**
     * 开始录制计时器
     */
    startRecordingTimer() {
        this.stopRecordingTimer(); // 清除现有定时器
        
        this.recordingInterval = setInterval(() => {
            if (this.recordingStartTime) {
                const duration = Date.now() - this.recordingStartTime;
                const minutes = Math.floor(duration / 60000);
                const seconds = Math.floor((duration % 60000) / 1000);
                
                document.getElementById('recording-duration').textContent = 
                    `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                const badgeTime = document.getElementById('rec-badge-time');
                if (badgeTime) {
                    badgeTime.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                }
            }
        }, 1000);
    }
    
    /**
     * 停止录制计时器
     */
    stopRecordingTimer() {
        if (this.recordingInterval) {
            clearInterval(this.recordingInterval);
            this.recordingInterval = null;
        }
        
        document.getElementById('recording-duration').textContent = '00:00';
        this.recordingStartTime = null;
        const badgeTime = document.getElementById('rec-badge-time');
        if (badgeTime) badgeTime.textContent = '00:00';

    }

    beginStatusPolling() {
        this.endStatusPolling();
        this.statusInterval = setInterval(() => this.updateCameraStatus(), 1000);
    }
    endStatusPolling() {
        if (this.statusInterval) {
            clearInterval(this.statusInterval);
            this.statusInterval = null;
        }
    }

    async applySizeOnly(width, height) {
        const btn = document.getElementById('apply-resolution');
        try {
            if (btn) btn.disabled = true;
            this.showNotification('正在设置分辨率...', 'info');
            
            const params = new URLSearchParams({ width: String(width), height: String(height) });
            const url = `/api/debug/camera/size?${params.toString()}`;
            console.debug('[applySizeOnly] POST', url);
            
            // 先停止预览，避免浏览器持有旧图像源导致卡死
            try { await this.stopPreview(); } catch(_){}
            
            const resp = await fetch(url, { method: 'POST' });
            if (!resp.ok) {
                let detail = '设置分辨率失败';
                try {
                    const err = await resp.json();
                    detail = err.detail || detail;
                } catch (_) {
                    try { detail = await resp.text(); } catch(_){}
                }
                throw new Error(detail);
            }
            const data = await resp.json();
            const info = data?.info || {};
            const applied = info?.width && info?.height ? `${info.width}x${info.height}` : `${width}x${height}`;
            this.showNotification(`分辨率已应用: ${applied}`, 'success');
            
            // 重新启动预览，确保新分辨率生效
            await this.updateCameraStatus();
            await this.startPreview();
            
            // 重置网络监控，确保新的分辨率设置后的数据传输被正确统计
            this.resetNetworkStatsForResolutionChange();
        } catch (e) {
            console.error('[applySizeOnly] error:', e);
            this.showNotification(`设置分辨率失败: ${e.message}`, 'error');
            // 尝试恢复预览
            try {
                await this.updateCameraStatus();
                if (this.cameraStatus.streaming) {
                    await this.startPreview();
                }
            } catch (recoveryError) {
                console.error('[applySizeOnly] recovery failed:', recoveryError);
            }
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    setRecOverlay(isRecording) {
        const container = document.getElementById('video-container');
        const badge = document.getElementById('rec-badge');
        if (!container || !badge) return;
        container.classList.toggle('recording-border', !!isRecording);
        badge.classList.toggle('show', !!isRecording);
    }
    
    /**
     * 更新曝光显示
     */
    updateExposureDisplay(value) {
        document.getElementById('exposure-value').textContent = value;
        this.currentSettings.exposure = value;
    }
    
    /**
     * 更新增益显示
     */
    updateGainDisplay(value) {
        document.getElementById('gain-value').textContent = value.toFixed(1);
        this.currentSettings.gain = value;
    }
    
    /**
     * 更新数字增益显示
     */
    updateDigitalGainDisplay(value) {
        document.getElementById('digital-gain-value').textContent = value.toFixed(1);
        this.currentSettings.digitalGain = value;
    }
    
    /**
     * 应用设置
     */
    async applySettings() {
        try {
            const response = await fetch('/api/debug/camera/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    exposure: this.currentSettings.exposure,
                    gain: this.currentSettings.gain
                })
            });
            
            if (response.ok) {
                this.showNotification('相机设置已应用', 'success');
            } else {
                const error = await response.json();
                throw new Error(error.detail || '应用设置失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 应用设置失败:', error);
            this.showNotification(`应用设置失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 重置设置
     */
    async resetSettings() {
        try {
            const response = await fetch('/api/debug/camera/reset', {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification('相机已重置到默认设置', 'success');
                
                // 重新加载相机状态以获取默认值
                await this.updateCameraStatus();
                
                // 更新UI显示
                if (this.cameraStatus.info) {
                    this.updateExposureDisplay(this.cameraStatus.info.exposure_us);
                    this.updateGainDisplay(this.cameraStatus.info.analogue_gain);
                    this.updateDigitalGainDisplay(this.cameraStatus.info.digital_gain || 1.0);
                }
            } else {
                const error = await response.json();
                throw new Error(error.detail || '重置设置失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 重置设置失败:', error);
            this.showNotification(`重置设置失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 加载预设
     */
    async loadPresets() {
        try {
            const response = await fetch('/api/debug/camera/presets');
            const data = await response.json();
            
            this.presets = data.presets || [];
            this.renderPresets();
            
        } catch (error) {
            console.error('[DebugConsole] 加载预设失败:', error);
            this.showNotification('加载预设失败', 'error');
        }
    }
    
    /**
     * 渲染预设列表
     */
    renderPresets() {
        const presetsGrid = document.getElementById('presets-grid');
        
        if (this.presets.length === 0) {
            presetsGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">💾</div>
                    <div class="empty-state-text">暂无预设</div>
                    <div class="empty-state-subtext">保存当前设置作为预设</div>
                </div>
            `;
            return;
        }
        
        presetsGrid.innerHTML = this.presets.map(preset => `
            <div class="preset-item">
                <div class="preset-name">${preset.name}</div>
                <div class="preset-description">${preset.description || '无描述'}</div>
                <div class="preset-params">
                    曝光: ${preset.exposure_us}μs | 增益: ${preset.analogue_gain}x
                </div>
                <div class="preset-actions">
                    <button class="btn btn-primary" onclick="window.debugConsole.applyPreset('${preset.name}')">
                        应用
                    </button>
                    <button class="btn btn-error" onclick="window.debugConsole.deletePreset('${preset.name}')">
                        删除
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    /**
     * 保存预设
     */
    async savePreset() {
        const name = document.getElementById('preset-name').value.trim();
        const description = document.getElementById('preset-description').value.trim();
        
        if (!name) {
            this.showNotification('请输入预设名称', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/debug/camera/presets', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: name,
                    description: description,
                    exposure_us: this.currentSettings.exposure,
                    analogue_gain: this.currentSettings.gain,
                    digital_gain: this.currentSettings.digitalGain
                })
            });
            
            if (response.ok) {
                this.showNotification('预设保存成功', 'success');
                
                // 清空表单
                document.getElementById('preset-name').value = '';
                document.getElementById('preset-description').value = '';
                
                // 重新加载预设
                await this.loadPresets();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '保存预设失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 保存预设失败:', error);
            this.showNotification(`保存预设失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 应用预设
     */
    async applyPreset(presetName) {
        try {
            const response = await fetch(`/api/debug/camera/presets/${encodeURIComponent(presetName)}/apply`, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showNotification(`预设 '${presetName}' 已应用`, 'success');
                
                // 重新加载相机状态
                await this.updateCameraStatus();
                
                // 更新UI显示
                if (this.cameraStatus.info) {
                    this.updateExposureDisplay(this.cameraStatus.info.exposure_us);
                    this.updateGainDisplay(this.cameraStatus.info.analogue_gain);
                    this.updateDigitalGainDisplay(this.cameraStatus.info.digital_gain || 1.0);
                }
            } else {
                const error = await response.json();
                throw new Error(error.detail || '应用预设失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 应用预设失败:', error);
            this.showNotification(`应用预设失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 删除预设
     */
    async deletePreset(presetName) {
        if (!confirm(`确定要删除预设 '${presetName}' 吗？`)) {
            return;
        }
        
        try {
            const response = await fetch(`/api/debug/camera/presets/${encodeURIComponent(presetName)}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                this.showNotification(`预设 '${presetName}' 已删除`, 'success');
                await this.loadPresets();
            } else {
                const error = await response.json();
                throw new Error(error.detail || '删除预设失败');
            }
        } catch (error) {
            console.error('[DebugConsole] 删除预设失败:', error);
            this.showNotification(`删除预设失败: ${error.message}`, 'error');
        }
    }
    
    /**
     * 加载文件列表
     */
    async loadFiles() {
        try {
            const response = await fetch('/api/debug/files');
            const data = await response.json();
            
            this.files = data.files || [];
            this.renderFiles();
            
        } catch (error) {
            console.error('[DebugConsole] 加载文件列表失败:', error);
            this.showNotification('加载文件列表失败', 'error');
        }
    }
    
    /**
     * 渲染文件列表
     */
    renderFiles() {
        const filesList = document.getElementById('files-list');
        
        if (this.files.length === 0) {
            filesList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📁</div>
                    <div class="empty-state-text">暂无文件</div>
                    <div class="empty-state-subtext">开始拍摄或录制视频</div>
                </div>
            `;
            return;
        }
        
        filesList.innerHTML = this.files.map(file => {
            const icon = file.type === 'image' ? '📷' : '🎥';
            const size = this.formatFileSize(file.size);
            const modified = new Date(file.modified).toLocaleString();
            
            return `
                <div class="file-item">
                    <div class="file-icon">${icon}</div>
                    <div class="file-info">
                        <div class="file-name">${file.name}</div>
                        <div class="file-meta">${size} • ${modified}</div>
                    </div>
                    <div class="file-actions">
                        <button class="btn btn-info" onclick="window.debugConsole.downloadFile('${file.name}')">
                            下载
                        </button>
                        <button class="btn btn-secondary" onclick="window.debugConsole.showFileInfo('${file.name}')">
                            详情
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    /**
     * 下载文件
     */
    downloadFile(filename) {
        const link = document.createElement('a');
        link.href = `/api/debug/files/${encodeURIComponent(filename)}`;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        this.showNotification(`开始下载: ${filename}`, 'info');
    }
    
    /**
     * 显示文件信息
     */
    async showFileInfo(filename) {
        try {
            const response = await fetch(`/api/debug/files/${encodeURIComponent(filename)}/info`);
            const info = await response.json();
            
            const infoHtml = `
                <div class="file-info-detail">
                    <h3>📄 ${info.filename}</h3>
                    <div class="info-grid">
                        <div class="info-item">
                            <span class="info-label">文件大小:</span>
                            <span class="info-value">${this.formatFileSize(info.size)}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">修改时间:</span>
                            <span class="info-value">${new Date(info.modified).toLocaleString()}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">文件类型:</span>
                            <span class="info-value">${info.type === 'image' ? '图片' : '视频'}</span>
                        </div>
                        ${info.exposure_us ? `
                        <div class="info-item">
                            <span class="info-label">曝光时间:</span>
                            <span class="info-value">${info.exposure_us}μs</span>
                        </div>
                        ` : ''}
                        ${info.analogue_gain ? `
                        <div class="info-item">
                            <span class="info-label">模拟增益:</span>
                            <span class="info-value">${info.analogue_gain}x</span>
                        </div>
                        ` : ''}
                        ${info.resolution ? `
                        <div class="info-item">
                            <span class="info-label">分辨率:</span>
                            <span class="info-value">${info.resolution}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>
            `;
            
            this.showModal('文件信息', infoHtml);
            
        } catch (error) {
            console.error('[DebugConsole] 获取文件信息失败:', error);
            this.showNotification('获取文件信息失败', 'error');
        }
    }
    
    /**
     * 格式化文件大小
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    /**
     * 更新按钮状态
     */
    updateButtonStates() {
        const startBtn = document.getElementById('start-preview');
        const stopBtn = document.getElementById('stop-preview');
        
        if (startBtn) {
            startBtn.disabled = this.cameraStatus.streaming;
            if (this.cameraStatus.streaming) {
                startBtn.classList.add('disabled');
            } else {
                startBtn.classList.remove('disabled');
            }
        }
        
        if (stopBtn) {
            stopBtn.disabled = !this.cameraStatus.streaming;
            if (!this.cameraStatus.streaming) {
                stopBtn.classList.add('disabled');
            } else {
                stopBtn.classList.remove('disabled');
            }
        }
    }
    
    /**
     * 更新录制按钮状态
     */
    updateRecordingButtons(isRecording) {
        const startBtn = document.getElementById('start-recording');
        const stopBtn = document.getElementById('stop-recording');
        
        if (startBtn) startBtn.disabled = isRecording;
        if (stopBtn) stopBtn.disabled = !isRecording;
    }
    
    /**
     * 处理键盘快捷键
     */
    handleKeyboardShortcuts(e) {
        // 防止在输入框中触发快捷键
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        
        switch(e.key) {
            case '1':
                this.switchTab('preview');
                break;
            case '2':
                this.switchTab('capture');
                break;
            case '3':
                this.switchTab('settings');
                break;
            case '4':
                this.switchTab('presets');
                break;
            case '5':
                this.switchTab('files');
                break;
            case ' ':
                e.preventDefault();
                if (this.cameraStatus.streaming) {
                    this.stopPreview();
                } else {
                    this.startPreview();
                }
                break;
            case 'c':
                if (this.cameraStatus.streaming) {
                    this.captureImage();
                }
                break;
            case 'r':
                if (this.cameraStatus.recording) {
                    this.stopRecording();
                } else if (this.cameraStatus.streaming) {
                    this.startRecording();
                }
                break;
            case 'Escape':
                if (this.cameraStatus.recording) {
                    this.stopRecording();
                }
                break;
        }
    }
    
    /**
     * 显示通知
     */
    showNotification(message, type = 'info') {
        const notifications = document.getElementById('notifications');
        
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        notifications.appendChild(notification);
        
        // 显示动画
        setTimeout(() => {
            notification.classList.add('show');
        }, 100);
        
        // 自动隐藏
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
    
    /**
     * 显示模态框
     */
    showModal(title, content) {
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>${title}</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    ${content}
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // 显示动画
        setTimeout(() => {
            modal.classList.add('show');
        }, 100);
        
        // 关闭事件
        modal.querySelector('.modal-close').addEventListener('click', () => {
            this.closeModal(modal);
        });
        
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeModal(modal);
            }
        });
    }
    
    /**
     * 关闭模态框
     */
    closeModal(modal) {
        modal.classList.remove('show');
        setTimeout(() => {
            if (modal.parentNode) {
                modal.parentNode.removeChild(modal);
            }
        }, 300);
    }
}

// 页面加载完成后初始化调试控制台
document.addEventListener('DOMContentLoaded', () => {
    window.debugConsole = new DebugConsole();
});

// 添加模态框样式
const modalStyles = `
.modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    opacity: 0;
    transition: opacity 0.3s ease;
}

.modal.show {
    opacity: 1;
}

.modal-content {
    background: var(--debug-surface);
    border-radius: var(--debug-radius);
    padding: 24px;
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    transform: scale(0.9);
    transition: transform 0.3s ease;
}

.modal.show .modal-content {
    transform: scale(1);
}

.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--debug-border);
}

.modal-header h3 {
    margin: 0;
    color: var(--debug-text);
    font-size: 1.2rem;
}

.modal-close {
    background: none;
    border: none;
    color: var(--debug-text-secondary);
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    transition: all 0.3s ease;
}

.modal-close:hover {
    background: var(--debug-border);
    color: var(--debug-text);
}

.info-grid {
    display: grid;
    gap: 12px;
}

.touch-feedback {
    transition: transform 0.2s ease;
}

.touch-feedback:active {
    transform: scale(0.95);
}
`;

// 添加样式到页面
const styleSheet = document.createElement('style');
styleSheet.textContent = modalStyles;
document.head.appendChild(styleSheet);

// 在DebugConsole类中添加直方图相关方法
DebugConsole.prototype.initHistogram = function() {
    console.log('[DebugConsole] 初始化直方图...');
    
    this.histogramCanvas = document.getElementById('histogram-canvas');
    this.histogramOverlay = document.getElementById('histogram-overlay');
    this.histogramPanel = document.getElementById('histogram-panel');
    
    if (this.histogramCanvas) {
        this.histogramContext = this.histogramCanvas.getContext('2d');
        this.setupHistogramCanvas();
    }
    
    // 初始化直方图状态
    this.updateHistogramVisibility();
};

DebugConsole.prototype.setupHistogramCanvas = function() {
    if (!this.histogramCanvas || !this.histogramContext) return;
    
    // 设置canvas尺寸
    const rect = this.histogramCanvas.getBoundingClientRect();
    this.histogramCanvas.width = rect.width * window.devicePixelRatio;
    this.histogramCanvas.height = rect.height * window.devicePixelRatio;
    this.histogramContext.scale(window.devicePixelRatio, window.devicePixelRatio);
    
    // 设置canvas样式
    this.histogramCanvas.style.width = rect.width + 'px';
    this.histogramCanvas.style.height = rect.height + 'px';
};

DebugConsole.prototype.toggleHistogram = function() {
    this.histogramSettings.visible = !this.histogramSettings.visible;
    this.updateHistogramVisibility();
    
    const toggleBtn = document.getElementById('histogram-toggle');
    if (toggleBtn) {
        toggleBtn.classList.toggle('active', this.histogramSettings.visible);
    }
    
    this.showNotification(
        this.histogramSettings.visible ? '直方图已显示' : '直方图已隐藏', 
        'info'
    );
};

DebugConsole.prototype.toggleHistogramPanel = function() {
    this.histogramSettings.panelVisible = !this.histogramSettings.panelVisible;
    
    if (this.histogramPanel) {
        this.histogramPanel.classList.toggle('visible', this.histogramSettings.panelVisible);
    }
};

DebugConsole.prototype.updateHistogramVisibility = function() {
    if (this.histogramOverlay) {
        this.histogramOverlay.classList.toggle('visible', this.histogramSettings.visible);
    }
    
    // 如果直方图可见且有预览图像，则更新直方图
    if (this.histogramSettings.visible && this.previewActive) {
        this.updateHistogramFromImage();
    }
};

DebugConsole.prototype.updateHistogramDisplay = function() {
    if (this.histogramSettings.visible && this.previewActive) {
        this.updateHistogramFromImage();
    }
};

DebugConsole.prototype.updateHistogramFromImage = function() {
    const previewImg = document.getElementById('preview-image');
    if (!previewImg || !this.histogramCanvas || !this.histogramContext) return;
    
    try {
        // 创建临时canvas来分析图像
        const tempCanvas = document.createElement('canvas');
        const tempContext = tempCanvas.getContext('2d');
        
        // 设置临时canvas尺寸
        tempCanvas.width = previewImg.naturalWidth || previewImg.width;
        tempCanvas.height = previewImg.naturalHeight || previewImg.height;
        
        // 绘制图像到临时canvas
        tempContext.drawImage(previewImg, 0, 0);
        
        // 获取图像数据
        const imageData = tempContext.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
        const data = imageData.data;
        
        // 计算直方图
        const histogram = this.calculateHistogram(data);
        
        // 绘制直方图
        this.drawHistogram(histogram);
        
        // 更新统计信息
        this.updateHistogramStats(histogram);
        
    } catch (error) {
        console.error('[DebugConsole] 更新直方图失败:', error);
    }
};

DebugConsole.prototype.calculateHistogram = function(imageData) {
    const histogram = {
        red: new Array(256).fill(0),
        green: new Array(256).fill(0),
        blue: new Array(256).fill(0),
        luminance: new Array(256).fill(0)
    };
    
    for (let i = 0; i < imageData.length; i += 4) {
        const r = imageData[i];
        const g = imageData[i + 1];
        const b = imageData[i + 2];
        
        // 计算亮度 (使用标准的亮度公式)
        const luminance = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
        
        histogram.red[r]++;
        histogram.green[g]++;
        histogram.blue[b]++;
        histogram.luminance[luminance]++;
    }
    
    return histogram;
};

DebugConsole.prototype.drawHistogram = function(histogram) {
    if (!this.histogramCanvas || !this.histogramContext) return;
    
    const canvas = this.histogramCanvas;
    const ctx = this.histogramContext;
    const width = canvas.width / window.devicePixelRatio;
    const height = canvas.height / window.devicePixelRatio;
    
    // 清除canvas
    ctx.clearRect(0, 0, width, height);
    
    // 设置背景
    ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
    ctx.fillRect(0, 0, width, height);
    
    // 找到最大计数值用于归一化
    const maxCount = Math.max(
        ...histogram.red,
        ...histogram.green,
        ...histogram.blue,
        ...histogram.luminance
    );
    
    if (maxCount === 0) return;
    
    // 绘制直方图
    const barWidth = width / 256;
    
    for (let i = 0; i < 256; i++) {
        const x = i * barWidth;
        
        // 绘制RGB通道
        if (this.histogramSettings.showRGB) {
            const redHeight = (histogram.red[i] / maxCount) * height;
            const greenHeight = (histogram.green[i] / maxCount) * height;
            const blueHeight = (histogram.blue[i] / maxCount) * height;
            
            // 红色通道
            ctx.fillStyle = 'rgba(255, 0, 0, 0.6)';
            ctx.fillRect(x, height - redHeight, barWidth, redHeight);
            
            // 绿色通道
            ctx.fillStyle = 'rgba(0, 255, 0, 0.6)';
            ctx.fillRect(x, height - greenHeight, barWidth, greenHeight);
            
            // 蓝色通道
            ctx.fillStyle = 'rgba(0, 0, 255, 0.6)';
            ctx.fillRect(x, height - blueHeight, barWidth, blueHeight);
        }
        
        // 绘制亮度通道
        if (this.histogramSettings.showLuminance) {
            const luminanceHeight = (histogram.luminance[i] / maxCount) * height;
            ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
            ctx.fillRect(x, height - luminanceHeight, barWidth, luminanceHeight);
        }
        
        // 过曝警告
        if (this.histogramSettings.showOverexposure && i >= 250) {
            const overexposedHeight = (histogram.luminance[i] / maxCount) * height;
            if (overexposedHeight > 0) {
                ctx.fillStyle = 'rgba(255, 0, 0, 0.9)';
                ctx.fillRect(x, height - overexposedHeight, barWidth, overexposedHeight);
            }
        }
    }
    
    // 绘制网格线
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.lineWidth = 1;
    
    // 垂直线
    for (let i = 0; i <= 4; i++) {
        const x = (i * width) / 4;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
    }
    
    // 水平线
    for (let i = 0; i <= 4; i++) {
        const y = (i * height) / 4;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }
};

DebugConsole.prototype.updateHistogramStats = function(histogram) {
    // 计算统计信息
    const totalPixels = histogram.luminance.reduce((sum, count) => sum + count, 0);
    
    if (totalPixels === 0) return;
    
    // 计算平均值
    let mean = 0;
    for (let i = 0; i < 256; i++) {
        mean += i * histogram.luminance[i];
    }
    mean /= totalPixels;
    
    // 计算标准差
    let variance = 0;
    for (let i = 0; i < 256; i++) {
        variance += Math.pow(i - mean, 2) * histogram.luminance[i];
    }
    variance /= totalPixels;
    const stdDev = Math.sqrt(variance);
    
    // 计算过曝像素数量
    let overexposedPixels = 0;
    for (let i = 250; i < 256; i++) {
        overexposedPixels += histogram.luminance[i];
    }
    const overexposedPercent = (overexposedPixels / totalPixels) * 100;
    
    // 更新UI
    const meanElement = document.getElementById('histogram-mean');
    const stdElement = document.getElementById('histogram-std');
    const overexposedElement = document.getElementById('histogram-overexposed');
    
    if (meanElement) meanElement.textContent = mean.toFixed(1);
    if (stdElement) stdElement.textContent = stdDev.toFixed(1);
    if (overexposedElement) overexposedElement.textContent = `${overexposedPercent.toFixed(1)}%`;
};

// 重写analyzeStreamData方法以包含直方图更新
const originalAnalyzeStreamData = DebugConsole.prototype.analyzeStreamData;
DebugConsole.prototype.analyzeStreamData = function(imageElement) {
    // 调用原始方法
    originalAnalyzeStreamData.call(this, imageElement);
    
    // 更新直方图
    if (this.histogramSettings.visible) {
        this.updateHistogramFromImage();
    }
};
