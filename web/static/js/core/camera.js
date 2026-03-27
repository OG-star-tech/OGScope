/* OGScope - 相机控制模块 / OGScope - Camera Control Module */
/**
 * 相机控制器类 / Camera controller class
 */
class CameraController {
    constructor() {
        this.videoElement = null;
        this.stream = null;
        this.isInitialized = false;
        this.isStreaming = false;
        this.currentSettings = {
            width: 1920,
            height: 1080,
            fps: 30,
            quality: 85
        };
        this.eventListeners = new Map();
        this.init();
    }

    /**
     * 初始化相机控制器 / Initialize camera controller
     */
    init() {
        this.videoElement = document.getElementById(OGScopeConstants.ELEMENT_IDS.VIDEO_STREAM);
        if (this.videoElement) {
            this.setupVideoElement();
        }
    }

    /**
     * 设置视频元素 / Set up video elements
     */
    setupVideoElement() {
        this.videoElement.addEventListener('loadedmetadata', () => {
            console.log('视频元数据已加载');
            this.emit('metadataLoaded');
        });

        this.videoElement.addEventListener('canplay', () => {
            console.log('视频可以播放');
            this.emit('canPlay');
        });

        this.videoElement.addEventListener('play', () => {
            console.log('视频开始播放');
            this.isStreaming = true;
            this.emit('play');
        });

        this.videoElement.addEventListener('pause', () => {
            console.log('视频暂停');
            this.isStreaming = false;
            this.emit('pause');
        });

        this.videoElement.addEventListener('error', (event) => {
            console.error('视频错误:', event);
            this.emit('error', event);
        });

        this.videoElement.addEventListener('ended', () => {
            console.log('视频播放结束');
            this.isStreaming = false;
            this.emit('ended');
        });
    }

    /**
     * 初始化视频流 / Initialize video stream
     */
    async initVideoStream() {
        try {
            console.log('正在初始化视频流...');
            
            // 尝试获取用户媒体 / Try to get user media
            const constraints = {
                video: {
                    width: { ideal: this.currentSettings.width },
                    height: { ideal: this.currentSettings.height },
                    frameRate: { ideal: this.currentSettings.fps }
                }
            };

            this.stream = await navigator.mediaDevices.getUserMedia(constraints);
            
            if (this.videoElement) {
                this.videoElement.srcObject = this.stream;
                this.videoElement.play();
            }
            
            this.isInitialized = true;
            this.emit('streamInitialized');
            
            console.log('视频流初始化成功');
            return true;
        } catch (error) {
            console.error('视频流初始化失败:', error);
            this.emit('streamError', error);
            
            // 使用占位符 / Use placeholders
            this.usePlaceholder();
            return false;
        }
    }

    /**
     * 使用占位符 / Use placeholders
     */
    usePlaceholder() {
        if (this.videoElement) {
            this.videoElement.style.background = 'radial-gradient(circle at 50% 50%, #1a1a1a 0%, #000000 100%)';
            this.videoElement.style.display = 'block';
        }
        this.isInitialized = true;
        this.emit('placeholderUsed');
    }

    /**
     * 开始流媒体 / Start streaming
     */
    async startStream() {
        if (!this.isInitialized) {
            await this.initVideoStream();
        }
        
        if (this.videoElement && this.stream) {
            try {
                await this.videoElement.play();
                this.isStreaming = true;
                this.emit('streamStarted');
                return true;
            } catch (error) {
                console.error('开始流媒体失败:', error);
                this.emit('streamError', error);
                return false;
            }
        }
        return false;
    }

    /**
     * 停止流媒体 / Stop streaming
     */
    stopStream() {
        if (this.videoElement) {
            this.videoElement.pause();
        }
        
        if (this.stream) {
            this.stream.getTracks().forEach(track => {
                track.stop();
            });
            this.stream = null;
        }
        
        this.isStreaming = false;
        this.emit('streamStopped');
    }

    /**
     * 设置相机参数 / Set camera parameters
     * @param {Object} settings - 相机设置 / camera settings
     */
    async setCameraSettings(settings) {
        this.currentSettings = { ...this.currentSettings, ...settings };
        
        if (this.stream) {
            const videoTrack = this.stream.getVideoTracks()[0];
            if (videoTrack) {
                try {
                    await videoTrack.applyConstraints({
                        width: { ideal: this.currentSettings.width },
                        height: { ideal: this.currentSettings.height },
                        frameRate: { ideal: this.currentSettings.fps }
                    });
                    this.emit('settingsUpdated', this.currentSettings);
                } catch (error) {
                    console.error('设置相机参数失败:', error);
                    this.emit('settingsError', error);
                }
            }
        }
    }

    /**
     * 获取相机信息 / Get camera information
     * @returns {Object} 相机信息 / camera information
     */
    getCameraInfo() {
        if (!this.stream) return null;
        
        const videoTrack = this.stream.getVideoTracks()[0];
        if (!videoTrack) return null;
        
        const settings = videoTrack.getSettings();
        const capabilities = videoTrack.getCapabilities();
        
        return {
            deviceId: settings.deviceId,
            label: videoTrack.label,
            settings: settings,
            capabilities: capabilities,
            currentSettings: this.currentSettings
        };
    }

    /**
     * 拍照 / Photograph
     * @returns {Promise<Blob>} 图片数据 / image data
     */
    async capturePhoto() {
        if (!this.videoElement || !this.isStreaming) {
            throw new Error('相机未初始化或未在流媒体状态');
        }
        
        return new Promise((resolve, reject) => {
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            
            canvas.width = this.videoElement.videoWidth;
            canvas.height = this.videoElement.videoHeight;
            
            context.drawImage(this.videoElement, 0, 0, canvas.width, canvas.height);
            
            canvas.toBlob((blob) => {
                if (blob) {
                    resolve(blob);
                } else {
                    reject(new Error('拍照失败'));
                }
            }, 'image/jpeg', this.currentSettings.quality / 100);
        });
    }

    /**
     * 开始录制 / Start recording
     * @returns {Promise<MediaRecorder>} 录制器 / recorder
     */
    async startRecording() {
        if (!this.stream) {
            throw new Error('没有可用的视频流');
        }
        
        const options = {
            mimeType: 'video/webm;codecs=vp9',
            videoBitsPerSecond: 2500000
        };
        
        const recorder = new MediaRecorder(this.stream, options);
        const chunks = [];
        
        recorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                chunks.push(event.data);
            }
        };
        
        recorder.onstop = () => {
            const blob = new Blob(chunks, { type: 'video/webm' });
            this.emit('recordingStopped', blob);
        };
        
        recorder.start();
        this.emit('recordingStarted', recorder);
        
        return recorder;
    }

    /**
     * 停止录制 / Stop recording
     * @param {MediaRecorder} recorder - 录制器 / recorder
     */
    stopRecording(recorder) {
        if (recorder && recorder.state === 'recording') {
            recorder.stop();
        }
    }

    /**
     * 获取视频帧 / Get video frames
     * @returns {ImageData|null} 视频帧数据 / video frame data
     */
    getVideoFrame() {
        if (!this.videoElement || !this.isStreaming) {
            return null;
        }
        
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        
        canvas.width = this.videoElement.videoWidth;
        canvas.height = this.videoElement.videoHeight;
        
        context.drawImage(this.videoElement, 0, 0, canvas.width, canvas.height);
        
        return context.getImageData(0, 0, canvas.width, canvas.height);
    }

    /**
     * 分析图像质量 / Analyze image quality
     * @returns {Object} 质量分析结果 / quality analysis results
     */
    analyzeImageQuality() {
        const frameData = this.getVideoFrame();
        if (!frameData) {
            return { quality: 0, sharpness: 0, brightness: 0, contrast: 0 };
        }
        
        const data = frameData.data;
        const width = frameData.width;
        const height = frameData.height;
        
        let totalBrightness = 0;
        let totalContrast = 0;
        let edgeCount = 0;
        
        // 计算亮度和对比度 / Calculate brightness and contrast
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            const brightness = (r + g + b) / 3;
            totalBrightness += brightness;
        }
        
        const avgBrightness = totalBrightness / (data.length / 4);
        
        // 计算对比度 / Calculate contrast
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            const brightness = (r + g + b) / 3;
            totalContrast += Math.pow(brightness - avgBrightness, 2);
        }
        
        const contrast = Math.sqrt(totalContrast / (data.length / 4));
        
        // 计算锐度（边缘检测） / Compute sharpness (edge ​​detection)
        for (let y = 1; y < height - 1; y++) {
            for (let x = 1; x < width - 1; x++) {
                const idx = (y * width + x) * 4;
                const r = data[idx];
                const g = data[idx + 1];
                const b = data[idx + 2];
                const brightness = (r + g + b) / 3;
                
                // Sobel算子 / Sobel operator
                const gx = Math.abs(
                    -data[idx - 4] + data[idx + 4] +
                    -2 * data[idx - width * 4] + 2 * data[idx + width * 4] +
                    -data[idx - (width + 1) * 4] + data[idx + (width + 1) * 4]
                );
                
                const gy = Math.abs(
                    -data[idx - width * 4] + data[idx + width * 4] +
                    -2 * data[idx - 4] + 2 * data[idx + 4] +
                    -data[idx - (width - 1) * 4] + data[idx + (width - 1) * 4]
                );
                
                const gradient = Math.sqrt(gx * gx + gy * gy);
                if (gradient > 50) {
                    edgeCount++;
                }
            }
        }
        
        const sharpness = edgeCount / ((width - 2) * (height - 2));
        const quality = Math.min(100, (sharpness * 1000 + contrast * 10 + avgBrightness / 2.55) / 3);
        
        return {
            quality: Math.round(quality),
            sharpness: Math.round(sharpness * 100),
            brightness: Math.round(avgBrightness / 2.55),
            contrast: Math.round(contrast)
        };
    }

    /**
     * 检测星点 / Detect star point
     * @returns {Array} 星点列表 / star point list
     */
    detectStars() {
        const frameData = this.getVideoFrame();
        if (!frameData) {
            return [];
        }
        
        const data = frameData.data;
        const width = frameData.width;
        const height = frameData.height;
        const stars = [];
        
        // 简单的星点检测算法 / Simple star point detection algorithm
        for (let y = 2; y < height - 2; y++) {
            for (let x = 2; x < width - 2; x++) {
                const idx = (y * width + x) * 4;
                const r = data[idx];
                const g = data[idx + 1];
                const b = data[idx + 2];
                const brightness = (r + g + b) / 3;
                
                // 检查是否为亮点 / Check if it is a highlight
                if (brightness > 200) {
                    let isStar = true;
                    
                    // 检查周围像素 / Check surrounding pixels
                    for (let dy = -2; dy <= 2 && isStar; dy++) {
                        for (let dx = -2; dx <= 2 && isStar; dx++) {
                            if (dx === 0 && dy === 0) continue;
                            
                            const checkIdx = ((y + dy) * width + (x + dx)) * 4;
                            const checkR = data[checkIdx];
                            const checkG = data[checkIdx + 1];
                            const checkB = data[checkIdx + 2];
                            const checkBrightness = (checkR + checkG + checkB) / 3;
                            
                            if (checkBrightness >= brightness) {
                                isStar = false;
                            }
                        }
                    }
                    
                    if (isStar) {
                        stars.push({
                            x: x,
                            y: y,
                            brightness: brightness,
                            size: 1
                        });
                    }
                }
            }
        }
        
        return stars;
    }

    /**
     * 添加事件监听器 / Add event listener
     * @param {string} event - 事件名 / event name
     * @param {Function} callback - 回调函数 / callback function
     */
    on(event, callback) {
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, []);
        }
        this.eventListeners.get(event).push(callback);
    }

    /**
     * 移除事件监听器 / Remove event listener
     * @param {string} event - 事件名 / event name
     * @param {Function} callback - 回调函数 / callback function
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
     * 触发事件 / trigger event
     * @param {string} event - 事件名 / event name
     * @param {...any} args - 参数 / parameters
     */
    emit(event, ...args) {
        if (this.eventListeners.has(event)) {
            this.eventListeners.get(event).forEach(callback => {
                try {
                    callback(...args);
                } catch (error) {
                    console.error('相机事件回调执行失败:', error);
                }
            });
        }
    }

    /**
     * 销毁相机控制器 / Destroy camera controller
     */
    destroy() {
        this.stopStream();
        this.eventListeners.clear();
        this.isInitialized = false;
    }
}

// 创建相机控制器实例 / Create camera controller instance
const cameraController = new CameraController();

// 导出相机控制器 / Export camera controller
window.OGScopeCamera = {
    CameraController,
    cameraController
};