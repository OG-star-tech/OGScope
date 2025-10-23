/**
 * OGScope 常量定义
 * 包含应用中的所有常量配置
 */

export const APP_CONFIG = {
    // 应用信息
    APP_NAME: 'OGScope',
    APP_VERSION: '1.0.0',
    APP_DESCRIPTION: '革命性电子极轴镜',
    
    // API端点
    API_BASE_URL: '/api',
    CAMERA_PREVIEW_URL: '/api/camera/preview',
    CAMERA_STREAM_URL: '/api/camera/stream',
    ALIGNMENT_URL: '/api/alignment',
    
    // 相机设置
    CAMERA: {
        DEFAULT_EXPOSURE: 10000,
        DEFAULT_GAIN: 1.0,
        DEFAULT_BRIGHTNESS: 1.0,
        MIN_EXPOSURE: 1000,
        MAX_EXPOSURE: 100000,
        MIN_GAIN: 1.0,
        MAX_GAIN: 16.0
    },
    
    // UI设置
    UI: {
        MAX_PARTICLES: 30,
        LOADING_STEPS: [
            { progress: 20, text: '正在初始化系统...' },
            { progress: 40, text: '正在连接摄像头...' },
            { progress: 60, text: '正在加载星图数据库...' },
            { progress: 80, text: '正在校准系统...' },
            { progress: 100, text: '系统就绪' }
        ]
    },
    
    // 校准设置
    ALIGNMENT: {
        PRECISION_THRESHOLD: 0.1, // 精度阈值（度）
        MAX_ERROR_DISPLAY: 999,   // 最大误差显示值
        UPDATE_INTERVAL: 100      // 更新间隔（毫秒）
    },
    
    // 网络设置
    NETWORK: {
        RETRY_ATTEMPTS: 3,
        RETRY_DELAY: 1000,
        TIMEOUT: 10000
    }
};

export const CSS_CLASSES = {
    // 状态类
    HIDDEN: 'hidden',
    ACTIVE: 'active',
    DISABLED: 'disabled',
    LOADING: 'loading',
    
    // 组件类
    BUTTON: 'btn',
    BUTTON_PRIMARY: 'btn-primary',
    BUTTON_SECONDARY: 'btn-secondary',
    BUTTON_SUCCESS: 'btn-success',
    BUTTON_ERROR: 'btn-error',
    
    // 布局类
    CONTAINER: 'container',
    CARD: 'card',
    MODAL: 'modal',
    
    // 状态指示器
    STATUS_ONLINE: 'online',
    STATUS_OFFLINE: 'offline',
    STATUS_CONNECTING: 'connecting'
};

export const EVENTS = {
    // 相机事件
    CAMERA_STREAM_START: 'camera:stream:start',
    CAMERA_STREAM_STOP: 'camera:stream:stop',
    CAMERA_STREAM_ERROR: 'camera:stream:error',
    
    // 校准事件
    ALIGNMENT_START: 'alignment:start',
    ALIGNMENT_STOP: 'alignment:stop',
    ALIGNMENT_PROGRESS: 'alignment:progress',
    ALIGNMENT_COMPLETE: 'alignment:complete',
    
    // UI事件
    UI_READY: 'ui:ready',
    UI_ERROR: 'ui:error',
    
    // 网络事件
    NETWORK_ONLINE: 'network:online',
    NETWORK_OFFLINE: 'network:offline',
    
    // PWA事件
    PWA_INSTALL_PROMPT: 'pwa:install:prompt',
    PWA_INSTALLED: 'pwa:installed'
};

export const ERROR_MESSAGES = {
    CAMERA_CONNECTION_FAILED: '相机连接失败',
    STREAM_START_FAILED: '视频流启动失败',
    ALIGNMENT_FAILED: '校准失败',
    NETWORK_ERROR: '网络连接错误',
    UNKNOWN_ERROR: '未知错误'
};
