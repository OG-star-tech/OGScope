/* OGScope - UI控制模块 / OGScope - UI control module */
/**
 * UI控制器类 / UI controller class
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
     * 初始化UI控制器 / Initialize UI controller
     */
    init() {
        this.cacheElements();
        this.setupEventListeners();
        this.setupKeyboardShortcuts();
        this.loadSettings();
    }

    /**
     * 缓存DOM元素 / Caching DOM elements
     */
    cacheElements() {
        this.elements = {
            // 主要容器 / main container
            app: document.getElementById(OGScopeConstants.ELEMENT_IDS.APP),
            loadingScreen: document.getElementById(OGScopeConstants.ELEMENT_IDS.LOADING_SCREEN),
            videoStream: document.getElementById(OGScopeConstants.ELEMENT_IDS.VIDEO_STREAM),
            
            // 加载相关 / Loading related
            progressBar: document.getElementById(OGScopeConstants.ELEMENT_IDS.PROGRESS_BAR),
            loadingStatus: document.getElementById(OGScopeConstants.ELEMENT_IDS.LOADING_STATUS),
            
            // 菜单相关 / Menu related
            menuButton: document.getElementById(OGScopeConstants.ELEMENT_IDS.MENU_BUTTON),
            menuPanel: document.getElementById(OGScopeConstants.ELEMENT_IDS.MENU_PANEL),
            menuClose: document.getElementById(OGScopeConstants.ELEMENT_IDS.MENU_CLOSE),
            
            // 缩放相关 / Zoom related
            zoomIn: document.getElementById(OGScopeConstants.ELEMENT_IDS.ZOOM_IN),
            zoomOut: document.getElementById(OGScopeConstants.ELEMENT_IDS.ZOOM_OUT),
            zoomThumb: document.getElementById(OGScopeConstants.ELEMENT_IDS.ZOOM_THUMB),
            
            // 快门相关 / Shutter related
            shutterToggle: document.getElementById(OGScopeConstants.ELEMENT_IDS.SHUTTER_TOGGLE),
            shutterTools: document.getElementById(OGScopeConstants.ELEMENT_IDS.SHUTTER_TOOLS),
            shutterButton: document.getElementById(OGScopeConstants.ELEMENT_IDS.SHUTTER_BUTTON),
            shutterTimer: document.getElementById(OGScopeConstants.ELEMENT_IDS.SHUTTER_TIMER),
            
            // 数据显示 / Data display
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
     * 设置事件监听器 / Set event listener
     */
    setupEventListeners() {
        // 菜单控制 / Menu control
        this.addEventListener(this.elements.menuButton, 'click', () => this.toggleMenu());
        this.addEventListener(this.elements.menuClose, 'click', () => this.closeMenu());
        
        // 缩放控制 / Zoom control
        this.addEventListener(this.elements.zoomIn, 'click', () => this.zoomIn());
        this.addEventListener(this.elements.zoomOut, 'click', () => this.zoomOut());
        this.setupZoomSlider();
        
        // 模式切换 / Mode switching
        this.setupModeSwitcher();
        
        // 快门控制 / shutter control
        this.setupShutterControl();
        
        // 高级模式 / Advanced mode
        this.setupAdvancedMode();
        
        // 窗口事件 / window events
        this.addEventListener(window, 'resize', () => this.handleResize());
        this.addEventListener(window, 'orientationchange', () => this.handleOrientationChange());
        
        // 触摸事件 / touch event
        this.setupTouchEvents();
    }

    /**
     * 设置键盘快捷键 / Set keyboard shortcuts
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
     * 设置缩放滑块 / Set the zoom slider
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
     * 设置模式切换 / Setting mode switch
     */
    setupModeSwitcher() {
        const modeButtons = document.querySelectorAll('.mode-button');
        
        modeButtons.forEach(button => {
            this.addEventListener(button, 'click', () => {
                if (button.classList.contains(OGScopeConstants.CSS_CLASSES.ACTIVE)) {
                    // 点击当前模式，展开 / Click on the current mode to expand
                    const switcher = button.parentElement;
                    switcher.classList.toggle(OGScopeConstants.CSS_CLASSES.EXPANDED);
                } else {
                    // 点击其他模式，切换模式并折叠 / Click on other modes to switch modes and collapse
                    const mode = button.dataset.mode;
                    this.setMode(mode);
                }
            });
        });
    }

    /**
     * 设置快门控制 / Set shutter control
     */
    setupShutterControl() {
        // 快门切换按钮 / Shutter switch button
        this.addEventListener(this.elements.shutterToggle, 'click', () => {
            this.toggleShutterTools();
        });

        // 快门模式切换 / Shutter mode switching
        const shutterModes = document.querySelectorAll('.shutter-mode');
        shutterModes.forEach(mode => {
            this.addEventListener(mode, 'click', () => {
                shutterModes.forEach(m => m.classList.remove(OGScopeConstants.CSS_CLASSES.ACTIVE));
                mode.classList.add(OGScopeConstants.CSS_CLASSES.ACTIVE);
            });
        });

        // 快门按钮 / shutter button
        this.setupShutterButton();
    }

    /**
     * 设置快门按钮 / Set the shutter button
     */
    setupShutterButton() {
        if (!this.elements.shutterButton) return;

        // 桌面端：鼠标事件 / Desktop: Mouse events
        this.addEventListener(this.elements.shutterButton, 'mousedown', () => this.startShutter());
        this.addEventListener(this.elements.shutterButton, 'mouseup', () => this.stopShutter());
        this.addEventListener(this.elements.shutterButton, 'mouseleave', () => this.stopShutter());

        // 移动端：触摸事件 / Mobile: touch events
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
     * 设置高级模式 / Set advanced mode
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
     * 设置触摸事件 / Set touch events
     */
    setupTouchEvents() {
        // 阻止默认手势 / Block default gestures
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
     * 添加事件监听器 / Add event listener
     * @param {Element} element - DOM元素 / DOM element
     * @param {string} event - 事件名 / event name
     * @param {Function} handler - 处理函数 / processing function
     * @param {Object} options - 选项 / options
     */
    addEventListener(element, event, handler, options = {}) {
        if (element) {
            element.addEventListener(event, handler, options);
            
            // 保存监听器引用以便后续移除 / Save the listener reference for later removal
            const key = `${element.id || element.tagName}_${event}`;
            if (!this.eventListeners.has(key)) {
                this.eventListeners.set(key, []);
            }
            this.eventListeners.get(key).push({ element, event, handler, options });
        }
    }

    /**
     * 切换菜单 / Toggle menu
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
     * 打开菜单 / Open menu
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
     * 关闭菜单 / Close menu
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
     * 放大 / enlarge
     */
    zoomIn() {
        this.setZoomLevel(Math.min(this.state.zoomLevel + 0.1, 3.0));
    }

    /**
     * 缩小 / zoom out
     */
    zoomOut() {
        this.setZoomLevel(Math.max(this.state.zoomLevel - 0.1, 1.0));
    }

    /**
     * 切换缩放 / Toggle zoom
     */
    toggleZoom() {
        if (this.state.zoomLevel > 1.0) {
            this.setZoomLevel(1.0);
        } else {
            this.setZoomLevel(2.0);
        }
    }

    /**
     * 设置缩放级别 / Set zoom level
     * @param {number} level - 缩放级别 / zoom level
     */
    setZoomLevel(level) {
        this.state.zoomLevel = OGScopeUtils.clamp(level, 1.0, 3.0);
        this.updateZoomUI();
        
        // 应用缩放到视频 / Apply zoom to video
        if (this.elements.videoStream) {
            this.elements.videoStream.style.transform = `scale(${this.state.zoomLevel})`;
        }
    }

    /**
     * 更新缩放UI / Update zoom UI
     */
    updateZoomUI() {
        if (this.elements.zoomThumb) {
            const percentage = ((this.state.zoomLevel - 1.0) / 2.0) * 100;
            this.elements.zoomThumb.style.top = (100 - percentage) + '%';
        }
    }

    /**
     * 设置模式 / Setup mode
     * @param {string} mode - 模式 / mode
     */
    setMode(mode) {
        this.state.currentMode = mode;
        
        // 更新按钮状态 / Update button state
        document.querySelectorAll('.mode-button').forEach(btn => {
            btn.classList.remove(OGScopeConstants.CSS_CLASSES.ACTIVE);
        });
        
        const activeButton = document.querySelector(`[data-mode="${mode}"]`);
        if (activeButton) {
            activeButton.classList.add(OGScopeConstants.CSS_CLASSES.ACTIVE);
        }
        
        // 折叠模式切换器 / Folding mode switch
        const switcher = document.querySelector('.mode-switcher');
        if (switcher) {
            switcher.classList.remove(OGScopeConstants.CSS_CLASSES.EXPANDED);
        }
        
        console.log('模式切换到:', mode);
    }

    /**
     * 切换快门工具 / Switch shutter tool
     */
    toggleShutterTools() {
        if (this.elements.shutterTools) {
            const isExpanded = this.elements.shutterTools.classList.toggle(OGScopeConstants.CSS_CLASSES.EXPANDED);
            this.elements.shutterToggle.classList.toggle(OGScopeConstants.CSS_CLASSES.ACTIVE, isExpanded);
        }
    }

    /**
     * 开始快门 / Start shutter
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
     * 停止快门 / Stop shutter
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
     * 处理快门模式 / Handling shutter modes
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
     * 处理单次快门 / Process single shutter
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
     * 处理B门快门 / Handling B shutter
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
     * 处理连拍快门 / Handling burst shutter
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
     * 清除快门间隔 / Clear shutter interval
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
     * 切换高级模式 / Switch to advanced mode
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
     * 处理窗口大小变化 / Handling window size changes
     */
    handleResize() {
        // 重新计算布局 / Recalculate layout
        this.updateLayout();
    }

    /**
     * 处理方向变化 / Handling direction changes
     */
    handleOrientationChange() {
        // 延迟处理以确保尺寸已更新 / Delay processing to ensure dimensions are updated
        setTimeout(() => {
            this.updateLayout();
        }, 100);
    }

    /**
     * 更新布局 / Update layout
     */
    updateLayout() {
        // 检查是否为横屏 / Check if it is landscape orientation
        if (OGScopeUtils.isPortrait()) {
            // 显示横屏提示 / Show landscape tips
            this.showOrientationWarning();
        } else {
            // 隐藏横屏提示 / Hide landscape tips
            this.hideOrientationWarning();
        }
    }

    /**
     * 显示横屏提示 / Show landscape tips
     */
    showOrientationWarning() {
        // 这里可以添加横屏提示逻辑 / Here you can add horizontal screen prompt logic
        console.log('需要横屏使用');
    }

    /**
     * 隐藏横屏提示 / Hide landscape tips
     */
    hideOrientationWarning() {
        // 这里可以添加隐藏横屏提示的逻辑 / Here you can add logic to hide horizontal screen prompts
    }

    /**
     * 加载设置 / Load settings
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
     * 保存设置 / Save settings
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
     * 应用设置 / Apply settings
     * @param {Object} settings - 设置对象 / settings object
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
     * 销毁UI控制器 / Destroy UI controller
     */
    destroy() {
        // 移除所有事件监听器 / Remove all event listeners
        this.eventListeners.forEach((listeners, key) => {
            listeners.forEach(({ element, event, handler, options }) => {
                element.removeEventListener(event, handler, options);
            });
        });
        this.eventListeners.clear();
        
        // 保存设置 / Save settings
        this.saveSettings();
    }
}

// 创建UI控制器实例 / Create UI controller instance
const uiController = new UIController();

// 导出UI控制器 / Export UI controller
window.OGScopeUI = {
    UIController,
    uiController
};