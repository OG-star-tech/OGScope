/* OGScope - 常量定义 / OGScope - constant definition */
/**
 * 应用常量 / application constants
 */
const APP_CONSTANTS = {
    // 应用信息 / Application information
    APP_NAME: 'OGScope',
    APP_VERSION: '1.0.0',
    APP_DESCRIPTION: '电子极轴镜系统',
    
    // 默认配置 / Default configuration
    DEFAULT_CONFIG: {
        video: {
            width: 1920,
            height: 1080,
            fps: 30,
            quality: 85
        },
        alignment: {
            tolerance: 0.1,
            maxOffset: 5.0,
            autoCalibration: true
        },
        ui: {
            theme: 'dark',
            language: 'zh-CN',
            showCrosshair: true,
            showGuides: true
        }
    },
    
    // API端点 / API endpoint
    API_ENDPOINTS: {
        CAMERA_PREVIEW: '/api/dev/debug/camera/preview',
        ALIGNMENT_STATUS: '/api/alignment/status',
        SYSTEM_INFO: '/api/system/info'
    },
    
    // 事件类型 / event type
    EVENTS: {
        // 视频相关 / Video related
        VIDEO_LOADED: 'video:loaded',
        VIDEO_ERROR: 'video:error',
        VIDEO_PAUSED: 'video:paused',
        VIDEO_RESUMED: 'video:resumed',
        
        // 校准相关 / Calibration related
        ALIGNMENT_START: 'alignment:start',
        ALIGNMENT_PROGRESS: 'alignment:progress',
        ALIGNMENT_COMPLETE: 'alignment:complete',
        ALIGNMENT_ERROR: 'alignment:error',
        
        // UI相关 / UI related
        UI_MODE_CHANGE: 'ui:mode:change',
        UI_SETTINGS_OPEN: 'ui:settings:open',
        UI_SETTINGS_CLOSE: 'ui:settings:close',
        
        // 系统相关 / System related
        SYSTEM_CONNECTED: 'system:connected',
        SYSTEM_DISCONNECTED: 'system:disconnected',
        SYSTEM_ERROR: 'system:error'
    },
    
    // 模式类型 / Mode type
    MODES: {
        POLAR: 'polar',
        STAR: 'star',
        GUIDE: 'guide'
    },
    
    // 快门模式 / shutter mode
    SHUTTER_MODES: {
        SINGLE: 'single',
        BULB: 'bulb',
        CONTINUOUS: 'continuous'
    },
    
    // 状态类型 / status type
    STATUS: {
        IDLE: 'idle',
        LOADING: 'loading',
        ACTIVE: 'active',
        ERROR: 'error',
        SUCCESS: 'success',
        WARNING: 'warning'
    },
    
    // 动画持续时间 / animation duration
    ANIMATION_DURATION: {
        FAST: 150,
        NORMAL: 300,
        SLOW: 500
    },
    
    // 响应式断点 / Responsive breakpoints
    BREAKPOINTS: {
        MOBILE: 480,
        TABLET: 768,
        DESKTOP: 1024,
        LARGE: 1366
    },
    
    // 颜色主题 / color theme
    THEMES: {
        DARK: {
            primary: '#ff3333',
            secondary: '#8B0000',
            accent: '#ff6666',
            background: '#0a0000',
            surface: '#1a0000',
            text: '#ffffff',
            textSecondary: '#cccccc'
        },
        BLUE: {
            primary: '#0066ff',
            secondary: '#003d99',
            accent: '#3399ff',
            background: '#000a0a',
            surface: '#001a1a',
            text: '#ffffff',
            textSecondary: '#cccccc'
        },
        GREEN: {
            primary: '#00ff66',
            secondary: '#009933',
            accent: '#33ff99',
            background: '#000a00',
            surface: '#001a00',
            text: '#ffffff',
            textSecondary: '#cccccc'
        }
    },
    
    // 语言配置 / Language configuration
    LANGUAGES: {
        'zh-CN': {
            name: '简体中文',
            direction: 'ltr'
        },
        'en-US': {
            name: 'English',
            direction: 'ltr'
        }
    },
    
    // 单位系统 / unit system
    UNITS: {
        METRIC: 'metric',
        IMPERIAL: 'imperial'
    },
    
    // 精度设置 / Precision settings
    PRECISION: {
        COORDINATES: 4,
        OFFSET: 1,
        QUALITY: 0,
        BATTERY: 0
    },
    
    // 更新间隔 / update interval
    UPDATE_INTERVALS: {
        GPS: 2000,
        BATTERY: 5000,
        SIGNAL: 1500,
        QUALITY: 800,
        OFFSET: 1000
    },
    
    // 错误代码 / error code
    ERROR_CODES: {
        CAMERA_NOT_FOUND: 'CAMERA_NOT_FOUND',
        CAMERA_PERMISSION_DENIED: 'CAMERA_PERMISSION_DENIED',
        NETWORK_ERROR: 'NETWORK_ERROR',
        ALIGNMENT_FAILED: 'ALIGNMENT_FAILED',
        SYSTEM_ERROR: 'SYSTEM_ERROR'
    },
    
    // 错误消息 / error message
    ERROR_MESSAGES: {
        CAMERA_NOT_FOUND: '未找到摄像头设备',
        CAMERA_PERMISSION_DENIED: '摄像头权限被拒绝',
        NETWORK_ERROR: '网络连接错误',
        ALIGNMENT_FAILED: '校准失败',
        SYSTEM_ERROR: '系统错误'
    },
    
    // 成功消息 / success message
    SUCCESS_MESSAGES: {
        CAMERA_CONNECTED: '摄像头连接成功',
        ALIGNMENT_COMPLETE: '校准完成',
        SETTINGS_SAVED: '设置已保存',
        SYSTEM_READY: '系统就绪'
    },
    
    // 警告消息 / warning message
    WARNING_MESSAGES: {
        LOW_BATTERY: '电量不足',
        WEAK_SIGNAL: '信号较弱',
        POOR_QUALITY: '图像质量较差',
        HIGH_OFFSET: '偏移量较大'
    }
};

/**
 * 本地存储键名 / local storage key name
 */
const STORAGE_KEYS = {
    SETTINGS: 'ogscope_settings',
    THEME: 'ogscope_theme',
    LANGUAGE: 'ogscope_language',
    MODE: 'ogscope_mode',
    RECENT_POSITIONS: 'ogscope_recent_positions',
    CALIBRATION_DATA: 'ogscope_calibration_data'
};

/**
 * CSS类名 / CSS class name
 */
const CSS_CLASSES = {
    // 状态类 / Status class
    LOADING: 'loading',
    LOADED: 'loaded',
    HIDDEN: 'hidden',
    VISIBLE: 'visible',
    ACTIVE: 'active',
    DISABLED: 'disabled',
    ERROR: 'error',
    SUCCESS: 'success',
    WARNING: 'warning',
    
    // 动画类 / Animation
    FADE_IN: 'fade-in',
    FADE_OUT: 'fade-out',
    SLIDE_UP: 'slide-up',
    SLIDE_DOWN: 'slide-down',
    SLIDE_LEFT: 'slide-left',
    SLIDE_RIGHT: 'slide-right',
    SCALE_IN: 'scale-in',
    SCALE_OUT: 'scale-out',
    
    // 组件类 / Component class
    MENU_OPEN: 'open',
    EXPANDED: 'expanded',
    PRESSING: 'pressing',
    DRAGGING: 'dragging'
};

/**
 * DOM元素ID / DOM element ID
 */
const ELEMENT_IDS = {
    // 主要容器 / main container
    APP: 'app',
    LOADING_SCREEN: 'loading-screen',
    VIDEO_STREAM: 'video-stream',
    
    // 加载相关 / Loading related
    PROGRESS_BAR: 'progress-bar',
    LOADING_STATUS: 'loading-status',
    
    // 菜单相关 / Menu related
    MENU_BUTTON: 'menu-button',
    MENU_PANEL: 'menu-panel',
    MENU_CLOSE: 'menu-close',
    
    // 缩放相关 / Zoom related
    ZOOM_IN: 'zoom-in',
    ZOOM_OUT: 'zoom-out',
    ZOOM_THUMB: 'zoom-thumb',
    
    // 快门相关 / Shutter related
    SHUTTER_TOGGLE: 'shutter-toggle',
    SHUTTER_TOOLS: 'shutter-tools',
    SHUTTER_BUTTON: 'shutter-button',
    SHUTTER_TIMER: 'shutter-timer',
    
    // 数据显示 / Data display
    GPS_COORD: 'gps-coord',
    ALTITUDE: 'altitude',
    WIFI_STRENGTH: 'wifi-strength',
    GPS_STRENGTH: 'gps-strength',
    BATTERY_LEVEL: 'battery-level',
    AZIMUTH_OFFSET: 'azimuth-offset',
    ALTITUDE_OFFSET: 'altitude-offset',
    QUALITY_FILL: 'quality-fill',
    QUALITY_VALUE: 'quality-value'
};

/**
 * 键盘快捷键 / keyboard shortcuts
 */
const KEYBOARD_SHORTCUTS = {
    // 功能键 / Function keys
    TOGGLE_MENU: 'Escape',
    TOGGLE_FULLSCREEN: 'F11',
    TOGGLE_ZOOM: 'z',
    CAPTURE_SCREEN: 'c',
    
    // 模式切换 / Mode switching
    POLAR_MODE: '1',
    STAR_MODE: '2',
    GUIDE_MODE: '3',
    
    // 快门控制 / shutter control
    SHUTTER_RELEASE: 'Space',
    SHUTTER_BULB: 'b',
    
    // 校准控制 / Calibration control
    START_ALIGNMENT: 'a',
    RESET_ALIGNMENT: 'r',
    
    // 设置 / Settings
    OPEN_SETTINGS: 's',
    TOGGLE_THEME: 't'
};

// 导出常量 / Export constants
window.OGScopeConstants = {
    APP_CONSTANTS,
    STORAGE_KEYS,
    CSS_CLASSES,
    ELEMENT_IDS,
    KEYBOARD_SHORTCUTS
};