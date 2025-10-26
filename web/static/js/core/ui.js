/* OGScope - UI控制模块 */

/**
 * UI控制器类
 */
class UIController {
    constructor() {
        this.elements = {};
        this.state = {
            isMenuOpen: false,
            isAdvancedMode: false,
            currentMode: OGScopeConstants.APP_CONSTANTS.MODES.POLAR,
            zoomLevel: 1.0,
            isShutterPressed: false
        };
        this.eventListeners = new Map();
        this.init();
    }

    /**
     * 初始化UI控制器
     */
    init() {
        this.cacheElements();
        this.setupEventListeners();
        this.setupKeyboardShortcuts();
        this.loadSettings();
    }

    /**
     * 缓存DOM元素
     */
    cacheElements() {
        this.elements = {
            // 主要容器
            app: document.getElementById(OGScopeConstants.ELEMENT_IDS.APP),
            loadingScreen: document.getElementById(OGScopeConstants.ELEMENT_IDS.LOADING_SCREEN),
            videoStream: document.getElementById(OGScopeConstants.ELEMENT_IDS.VIDEO_STREAM),
            
            // 加载相关
            progressBar: document.getElementById(OGScopeConstants.ELEMENT_IDS.PROGRESS_BAR),
            loadingStatus: document.getElementById(OGScopeConstants.ELEMENT_IDS.LOADING_STATUS),
            
            // 菜单相关
            menuButton: document.getElementById(OGScopeConstants.ELEMENT_IDS.MENU_BUTTON),
            menuPanel: document.getElementById(OGScopeConstants.ELEMENT_IDS.MENU_PANEL),
            menuClose: document.getElementById(OGScopeConstants.ELEMENT_IDS.MENU_CLOSE),
            
            // 缩放相关
            zoomIn: document.getElementById(OGScopeConstants.ELEMENT_IDS.ZOOM_IN),
            zoomOut: document.getElementById(OGScopeConstants.ELEMENT_IDS.ZOOM_OUT),
            zoomThumb: document.getElementById(OGScopeConstants.ELEMENT_IDS.ZOOM_THUMB),
            
            // 快门相关
            shutterToggle: document.getElementById(OGScopeConstants.ELEMENT_IDS.SHUTTER_TOGGLE),
            shutterTools: document.getElementById(OGScopeConstants.ELEMENT_IDS.SHUTTER_TOOLS),
            shutterButton: document.getElementById(OGScopeConstants.ELEMENT_IDS.SHUTTER_BUTTON),
            shutterTimer: document.getElementById(OGScopeConstants.ELEMENT_IDS.SHUTTER_TIMER),
            
            // 数据显示
            gpsCoord: document.getElementById(OGScopeConstants.ELEMENT_IDS.GPS_COORD),
            altitude: document.getElementById(OGScopeConstants.ELEMENT_IDS.ALTITUDE),
            wifiStrength: document.getElementById(OGScopeConstants.ELEMENT_IDS.WIFI_STRENGTH),
            gpsStrength: document.getElementById(OGScopeConstants.ELEMENT_IDS.GPS_STRENGTH),
            batteryLevel: document.getElementById(OGScopeConstants.ELEMENT_IDS.BATTERY_LEVEL),
            azimuthOffset: document.getElementById(OGScopeConstants.ELEMENT_IDS.AZIMUTH_OFFSET),
            altitudeOffset: document.getElementById(OGScopeConstants.ELEMENT_IDS.ALTITUDE_OFFSET),
            qualityFill: document.getElementById(OGScopeConstants.ELEMENT_IDS.QUALITY_FILL),
            qualityValue: document.getElementById(OGScopeConstants.ELEMENT_IDS.QUALITY_VALUE)
        };
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 菜单控制
        this.addEventListener(this.elements.menuButton, 'click', () => this.toggleMenu());
        this.addEventListener(this.elements.menuClose, 'click', () => this.closeMenu());
        
        // 缩放控制
        this.addEventListener(this.elements.zoomIn, 'click', () => this.zoomIn());
        this.addEventListener(this.elements.zoomOut, 'click', () => this.zoomOut());
        this.setupZoomSlider();
        
        // 模式切换
        this.setupModeSwitcher();
        
        // 快门控制
        this.setupShutterControl();
        
        // 高级模式
        this.setupAdvancedMode();
        
        // 窗口事件
        this.addEventListener(window, 'resize', () => this.handleResize());
        this.addEventListener(window, 'orientationchange', () => this.handleOrientationChange());
        
        // 触摸事件
        this.setupTouchEvents();
    }

    /**
     * 设置键盘快捷键
     */
    setupKeyboardShortcuts() {
        this.addEventListener(document, 'keydown', (event) => {
            const key = event.key;
            
            switch (key) {
                case OGScopeConstants.KEYBOARD_SHORTCUTS.TOGGLE_MENU:
                    this.toggleMenu();
                    break;
                case OGScopeConstants.KEYBOARD_SHORTCUTS.TOGGLE_ZOOM:
                    this.toggleZoom();
                    break;
                case OGScopeConstants.KEYBOARD_SHORTCUTS.SHUTTER_RELEASE:
                    if (!event.repeat) {
                        this.startShutter();
                    }
                    break;
                case OGScopeConstants.KEYBOARD_SHORTCUTS.POLAR_MODE:
                    this.setMode(OGScopeConstants.APP_CONSTANTS.MODES.POLAR);
                    break;
                case OGScopeConstants.KEYBOARD_SHORTCUTS.STAR_MODE:
                    this.setMode(OGScopeConstants.APP_CONSTANTS.MODES.STAR);
                    break;
                case OGScopeConstants.KEYBOARD_SHORTCUTS.GUIDE_MODE:
                    this.setMode(OGScopeConstants.APP_CONSTANTS.MODES.GUIDE);
                    break;
            }
        });

        this.addEventListener(document, 'keyup', (event) => {
            if (event.key === OGScopeConstants.KEYBOARD_SHORTCUTS.SHUTTER_RELEASE) {
                this.stopShutter();
            }
        });
    }

    /**
     * 设置缩放滑块
     */
    setupZoomSlider() {
        if (!this.elements.zoomThumb) return;

        let isDragging = false;
        
        this.addEventListener(this.elements.zoomThumb, 'touchstart', (e) => {
            e.preventDefault();
            isDragging = true;
        });

        this.addEventListener(document, 'touchend', () => {
            isDragging = false;
        });

        this.addEventListener(document, 'touchmove', (e) => {
            if (isDragging) {
                e.preventDefault();
                const slider = this.elements.zoomThumb.parentElement;
                const rect = slider.getBoundingClientRect();
                const y = e.touches[0].clientY - rect.top;
                const percentage = Math.max(0, Math.min(100, (1 - y / rect.height) * 100));
                this.setZoomLevel(1.0 + (percentage / 100) * 2.0);
            }
        });
    }

    /**
     * 设置模式切换
     */
    setupModeSwitcher() {
        const modeButtons = document.querySelectorAll('.mode-button');
        
        modeButtons.forEach(button => {
            this.addEventListener(button, 'click', () => {
                if (button.classList.contains(OGScopeConstants.CSS_CLASSES.ACTIVE)) {
                    // 点击当前模式，展开/折叠
                    const switcher = button.parentElement;
                    switcher.classList.toggle(OGScopeConstants.CSS_CLASSES.EXPANDED);
                } else {
                    // 点击其他模式，切换模式并折叠
                    const mode = button.dataset.mode;
                    this.setMode(mode);
                }
            });
        });
    }

    /**
     * 设置快门控制
     */
    setupShutterControl() {
        // 快门切换按钮
        this.addEventListener(this.elements.shutterToggle, 'click', () => {
            this.toggleShutterTools();
        });

        // 快门模式切换
        const shutterModes = document.querySelectorAll('.shutter-mode');
        shutterModes.forEach(mode => {
            this.addEventListener(mode, 'click', () => {
                shutterModes.forEach(m => m.classList.remove(OGScopeConstants.CSS_CLASSES.ACTIVE));
                mode.classList.add(OGScopeConstants.CSS_CLASSES.ACTIVE);
            });
        });

        // 快门按钮
        this.setupShutterButton();
    }

    /**
     * 设置快门按钮
     */
    setupShutterButton() {
        if (!this.elements.shutterButton) return;

        // 桌面端：鼠标事件
        this.addEventListener(this.elements.shutterButton, 'mousedown', () => this.startShutter());
        this.addEventListener(this.elements.shutterButton, 'mouseup', () => this.stopShutter());
        this.addEventListener(this.elements.shutterButton, 'mouseleave', () => this.stopShutter());

        // 移动端：触摸事件
        this.addEventListener(this.elements.shutterButton, 'touchstart', (e) => {
            e.preventDefault();
            this.startShutter();
        });
        this.addEventListener(this.elements.shutterButton, 'touchend', (e) => {
            e.preventDefault();
            this.stopShutter();
        });
        this.addEventListener(this.elements.shutterButton, 'touchcancel', (e) => {
            e.preventDefault();
            this.stopShutter();
        });
    }

    /**
     * 设置高级模式
     */
    setupAdvancedMode() {
        const advancedButton = document.querySelector('.advanced-button');
        if (advancedButton) {
            this.addEventListener(advancedButton, 'click', () => {
                this.toggleAdvancedMode();
            });
        }
    }

    /**
     * 设置触摸事件
     */
    setupTouchEvents() {
        // 阻止默认手势
        this.addEventListener(document, 'touchmove', (e) => {
            if (e.scale !== 1) {
                e.preventDefault();
            }
        }, { passive: false });

        this.addEventListener(document, 'gesturestart', (e) => {
            e.preventDefault();
        });
    }

    /**
     * 添加事件监听器
     * @param {Element} element - DOM元素
     * @param {string} event - 事件名
     * @param {Function} handler - 处理函数
     * @param {Object} options - 选项
     */
    addEventListener(element, event, handler, options = {}) {
        if (element) {
            element.addEventListener(event, handler, options);
            
            // 保存监听器引用以便后续移除
            const key = `${element.id || element.tagName}_${event}`;
            if (!this.eventListeners.has(key)) {
                this.eventListeners.set(key, []);
            }
            this.eventListeners.get(key).push({ element, event, handler, options });
        }
    }

    /**
     * 切换菜单
     */
    toggleMenu() {
        this.state.isMenuOpen = !this.state.isMenuOpen;
        
        if (this.state.isMenuOpen) {
            this.openMenu();
        } else {
            this.closeMenu();
        }
    }

    /**
     * 打开菜单
     */
    openMenu() {
        if (this.elements.menuPanel) {
            this.elements.menuPanel.classList.add(OGScopeConstants.CSS_CLASSES.MENU_OPEN);
        }
        if (this.elements.menuButton) {
            this.elements.menuButton.classList.add(OGScopeConstants.CSS_CLASSES.HIDDEN);
        }
        this.state.isMenuOpen = true;
    }

    /**
     * 关闭菜单
     */
    closeMenu() {
        if (this.elements.menuPanel) {
            this.elements.menuPanel.classList.remove(OGScopeConstants.CSS_CLASSES.MENU_OPEN);
        }
        if (this.elements.menuButton) {
            this.elements.menuButton.classList.remove(OGScopeConstants.CSS_CLASSES.HIDDEN);
        }
        this.state.isMenuOpen = false;
    }

    /**
     * 放大
     */
    zoomIn() {
        this.setZoomLevel(Math.min(this.state.zoomLevel + 0.1, 3.0));
    }

    /**
     * 缩小
     */
    zoomOut() {
        this.setZoomLevel(Math.max(this.state.zoomLevel - 0.1, 1.0));
    }

    /**
     * 切换缩放
     */
    toggleZoom() {
        if (this.state.zoomLevel > 1.0) {
            this.setZoomLevel(1.0);
        } else {
            this.setZoomLevel(2.0);
        }
    }

    /**
     * 设置缩放级别
     * @param {number} level - 缩放级别
     */
    setZoomLevel(level) {
        this.state.zoomLevel = OGScopeUtils.clamp(level, 1.0, 3.0);
        this.updateZoomUI();
        
        // 应用缩放到视频
        if (this.elements.videoStream) {
            this.elements.videoStream.style.transform = `scale(${this.state.zoomLevel})`;
        }
    }

    /**
     * 更新缩放UI
     */
    updateZoomUI() {
        if (this.elements.zoomThumb) {
            const percentage = ((this.state.zoomLevel - 1.0) / 2.0) * 100;
            this.elements.zoomThumb.style.top = (100 - percentage) + '%';
        }
    }

    /**
     * 设置模式
     * @param {string} mode - 模式
     */
    setMode(mode) {
        this.state.currentMode = mode;
        
        // 更新按钮状态
        document.querySelectorAll('.mode-button').forEach(btn => {
            btn.classList.remove(OGScopeConstants.CSS_CLASSES.ACTIVE);
        });
        
        const activeButton = document.querySelector(`[data-mode="${mode}"]`);
        if (activeButton) {
            activeButton.classList.add(OGScopeConstants.CSS_CLASSES.ACTIVE);
        }
        
        // 折叠模式切换器
        const switcher = document.querySelector('.mode-switcher');
        if (switcher) {
            switcher.classList.remove(OGScopeConstants.CSS_CLASSES.EXPANDED);
        }
        
        console.log('模式切换到:', mode);
    }

    /**
     * 切换快门工具
     */
    toggleShutterTools() {
        if (this.elements.shutterTools) {
            const isExpanded = this.elements.shutterTools.classList.toggle(OGScopeConstants.CSS_CLASSES.EXPANDED);
            this.elements.shutterToggle.classList.toggle(OGScopeConstants.CSS_CLASSES.ACTIVE, isExpanded);
        }
    }

    /**
     * 开始快门
     */
    startShutter() {
        if (this.state.isShutterPressed) return;
        
        this.state.isShutterPressed = true;
        if (this.elements.shutterButton) {
            this.elements.shutterButton.classList.add(OGScopeConstants.CSS_CLASSES.PRESSING);
        }
        
        this.shutterStartTime = Date.now();
        this.handleShutterMode();
    }

    /**
     * 停止快门
     */
    stopShutter() {
        if (!this.state.isShutterPressed) return;
        
        this.state.isShutterPressed = false;
        if (this.elements.shutterButton) {
            this.elements.shutterButton.classList.remove(OGScopeConstants.CSS_CLASSES.PRESSING);
        }
        
        this.clearShutterIntervals();
    }

    /**
     * 处理快门模式
     */
    handleShutterMode() {
        const activeMode = document.querySelector('.shutter-mode.active');
        const mode = activeMode ? activeMode.dataset.mode : 'single';
        
        switch (mode) {
            case OGScopeConstants.APP_CONSTANTS.SHUTTER_MODES.SINGLE:
                this.handleSingleShutter();
                break;
            case OGScopeConstants.APP_CONSTANTS.SHUTTER_MODES.BULB:
                this.handleBulbShutter();
                break;
            case OGScopeConstants.APP_CONSTANTS.SHUTTER_MODES.CONTINUOUS:
                this.handleContinuousShutter();
                break;
        }
    }

    /**
     * 处理单次快门
     */
    handleSingleShutter() {
        if (this.elements.shutterTimer) {
            this.elements.shutterTimer.textContent = '拍摄中...';
        }
        
        setTimeout(() => {
            if (this.elements.shutterTimer) {
                this.elements.shutterTimer.textContent = '完成';
                setTimeout(() => {
                    if (this.elements.shutterTimer) {
                        this.elements.shutterTimer.textContent = '';
                    }
                }, 1000);
            }
        }, 300);
    }

    /**
     * 处理B门快门
     */
    handleBulbShutter() {
        if (this.elements.shutterTimer) {
            this.elements.shutterTimer.textContent = '0.0s';
        }
        
        this.shutterInterval = setInterval(() => {
            const elapsed = (Date.now() - this.shutterStartTime) / 1000;
            if (this.elements.shutterTimer) {
                this.elements.shutterTimer.textContent = OGScopeUtils.formatTime(elapsed);
            }
        }, 100);
    }

    /**
     * 处理连拍快门
     */
    handleContinuousShutter() {
        let shotCount = 0;
        if (this.elements.shutterTimer) {
            this.elements.shutterTimer.textContent = `连拍 ${shotCount}`;
        }
        
        this.continuousInterval = setInterval(() => {
            shotCount++;
            if (this.elements.shutterTimer) {
                this.elements.shutterTimer.textContent = `连拍 ${shotCount}`;
            }
        }, 500);
    }

    /**
     * 清除快门间隔
     */
    clearShutterIntervals() {
        if (this.shutterInterval) {
            clearInterval(this.shutterInterval);
            this.shutterInterval = null;
        }
        
        if (this.continuousInterval) {
            clearInterval(this.continuousInterval);
            this.continuousInterval = null;
        }
        
        if (this.elements.shutterTimer) {
            setTimeout(() => {
                this.elements.shutterTimer.textContent = '';
            }, 2000);
        }
    }

    /**
     * 切换高级模式
     */
    toggleAdvancedMode() {
        this.state.isAdvancedMode = !this.state.isAdvancedMode;
        
        const button = document.querySelector('.advanced-button');
        if (button) {
            button.classList.toggle(OGScopeConstants.CSS_CLASSES.ACTIVE, this.state.isAdvancedMode);
        }
        
        console.log('高级模式:', this.state.isAdvancedMode ? '开启' : '关闭');
    }

    /**
     * 处理窗口大小变化
     */
    handleResize() {
        // 重新计算布局
        this.updateLayout();
    }

    /**
     * 处理方向变化
     */
    handleOrientationChange() {
        // 延迟处理以确保尺寸已更新
        setTimeout(() => {
            this.updateLayout();
        }, 100);
    }

    /**
     * 更新布局
     */
    updateLayout() {
        // 检查是否为横屏
        if (OGScopeUtils.isPortrait()) {
            // 显示横屏提示
            this.showOrientationWarning();
        } else {
            // 隐藏横屏提示
            this.hideOrientationWarning();
        }
    }

    /**
     * 显示横屏提示
     */
    showOrientationWarning() {
        // 这里可以添加横屏提示逻辑
        console.log('需要横屏使用');
    }

    /**
     * 隐藏横屏提示
     */
    hideOrientationWarning() {
        // 这里可以添加隐藏横屏提示的逻辑
    }

    /**
     * 加载设置
     */
    loadSettings() {
        try {
            const savedSettings = localStorage.getItem(OGScopeConstants.STORAGE_KEYS.SETTINGS);
            if (savedSettings) {
                const settings = JSON.parse(savedSettings);
                this.applySettings(settings);
            }
        } catch (error) {
            console.error('加载设置失败:', error);
        }
    }

    /**
     * 保存设置
     */
    saveSettings() {
        try {
            const settings = {
                mode: this.state.currentMode,
                zoomLevel: this.state.zoomLevel,
                isAdvancedMode: this.state.isAdvancedMode
            };
            localStorage.setItem(OGScopeConstants.STORAGE_KEYS.SETTINGS, JSON.stringify(settings));
        } catch (error) {
            console.error('保存设置失败:', error);
        }
    }

    /**
     * 应用设置
     * @param {Object} settings - 设置对象
     */
    applySettings(settings) {
        if (settings.mode) {
            this.setMode(settings.mode);
        }
        if (settings.zoomLevel) {
            this.setZoomLevel(settings.zoomLevel);
        }
        if (settings.isAdvancedMode) {
            this.state.isAdvancedMode = settings.isAdvancedMode;
        }
    }

    /**
     * 销毁UI控制器
     */
    destroy() {
        // 移除所有事件监听器
        this.eventListeners.forEach((listeners, key) => {
            listeners.forEach(({ element, event, handler, options }) => {
                element.removeEventListener(event, handler, options);
            });
        });
        this.eventListeners.clear();
        
        // 保存设置
        this.saveSettings();
    }
}

// 创建UI控制器实例
const uiController = new UIController();

// 导出UI控制器
window.OGScopeUI = {
    UIController,
    uiController
};