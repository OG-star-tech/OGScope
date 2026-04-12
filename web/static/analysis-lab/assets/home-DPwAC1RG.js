import{r as m,j as h,c as b}from"./client-D1ZVDB-N.js";const v=`    <!-- 加载屏 / Loading screen -->
    <div id="loading-screen">
                <div class="loading-logo font-headline text-5xl text-primary mb-6 tracking-[0.3em]">⊕</div>
        <div class="loading-text font-headline text-sm text-primary uppercase tracking-[0.35em] mb-8">OGScope</div>
        <div class="w-48 max-w-[70vw] h-1 bg-surface-container-high rounded-none mb-4 overflow-hidden">
            <div class="progress-bar h-full bg-primary transition-all duration-300" id="progress-bar" style="width: 0%"></div>
        </div>
        <div class="loading-status font-body text-xs text-on-surface-variant" id="loading-status">正在初始化… / Initializing…</div>
    </div>

    <div id="app">
        <!-- 顶栏 / Top bar -->
        <header class="pointer-events-none fixed top-0 left-0 right-0 z-[60] box-border flex h-[calc(var(--hud-header-h)+env(safe-area-inset-top,0px))] flex-shrink-0 flex-col items-center justify-center gap-1 bg-transparent pl-[var(--hud-left-rail)] pr-[var(--hud-right-rail)] pt-[env(safe-area-inset-top,0px)] pb-0.5 sm:grid sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center sm:gap-x-2">
            <div class="pointer-events-auto min-w-0 justify-self-start sm:leading-tight">
                <h1 class="hud-brand-title flex min-w-0 items-center gap-1 truncate text-[10px] font-bold uppercase tracking-widest text-red-600 sm:text-xs">
                    <span class="shrink-0 font-headline leading-none">OGScope</span>
                    <span class="hud-brand-version shrink-0 font-headline text-[9px] font-medium normal-case leading-none tracking-normal text-stone-500 sm:text-[10px]"><span id="hud-app-version"></span></span>
                </h1>
            </div>
            <div class="hud-telemetry-strip pointer-events-auto flex min-h-0 w-full flex-nowrap items-center justify-center gap-x-1 overflow-x-auto overscroll-x-contain text-[9px] leading-tight sm:w-auto sm:max-w-[min(100%,52vw)] sm:gap-x-2 sm:text-[10px] sm:justify-center">
                <span class="shrink-0 font-headline text-red-400/95">定位</span>
                <span class="shrink-0 font-body text-stone-400 tabular-nums whitespace-nowrap" id="gps-coord">—</span>
                <span class="shrink-0 text-stone-700 px-0.5" aria-hidden="true">|</span>
                <span class="shrink-0 font-headline text-red-400/95">海拔</span>
                <span class="shrink-0 font-body text-stone-400 tabular-nums" id="altitude">—</span>
                <span class="shrink-0 text-stone-700 px-0.5" aria-hidden="true">|</span>
                <span class="shrink-0 text-stone-500">WiFi</span>
                <span class="shrink-0 tabular-nums text-stone-400" id="wifi-strength">—</span>
                <span class="shrink-0 text-stone-700 px-0.5" aria-hidden="true">|</span>
                <span class="shrink-0 text-stone-500">GPS</span>
                <span class="shrink-0 tabular-nums text-stone-400" id="gps-strength">—</span>
                <span class="shrink-0 text-stone-700 px-0.5" aria-hidden="true">|</span>
                <span class="hud-battery-wrap shrink-0 text-stone-400">
                    <span class="material-symbols-outlined hud-battery-icon text-red-500" aria-hidden="true">battery_horiz_050</span>
                    <span class="tabular-nums leading-none" id="battery-level">—</span>
                </span>
            </div>
            <div class="hidden min-w-0 sm:block" aria-hidden="true"></div>
        </header>

        <!-- 左侧仅缩放，纵向居中，避让安全区 / Left rail: zoom only, centered, safe-area aware -->
        <div class="fixed left-0 top-0 bottom-0 z-40 flex w-[var(--hud-left-rail)] flex-col items-center justify-center border-r border-stone-800/50 bg-stone-900/40 px-1.5 pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)] backdrop-blur-md" aria-label="缩放 / Zoom">
            <div class="flex flex-col items-center gap-6 sm:gap-8">
                <button type="button" id="zoom-in" class="flex h-11 w-11 items-center justify-center border border-outline-variant/30 transition-all hover:bg-surface-bright active:scale-90 sm:h-12 sm:w-12" aria-label="放大 / Zoom in">
                    <span class="material-symbols-outlined text-lg text-on-surface-variant" aria-hidden="true">add</span>
                </button>
                <div class="relative h-16 w-px bg-outline-variant/30 sm:h-20">
                    <div id="zoom-thumb" class="absolute left-1/2 w-4 -translate-x-1/2 bg-primary" style="top: 100%; height: 2px"></div>
                </div>
                <button type="button" id="zoom-out" class="flex h-11 w-11 items-center justify-center border border-outline-variant/30 transition-all hover:bg-surface-bright active:scale-90 sm:h-12 sm:w-12" aria-label="缩小 / Zoom out">
                    <span class="material-symbols-outlined text-lg text-on-surface-variant" aria-hidden="true">remove</span>
                </button>
                <span class="font-headline text-[7px] text-stone-600 sm:text-[8px]">缩放 / ZOOM</span>
            </div>
        </div>

        <!-- 右侧：调节、图层、可折叠模式 / Right rail: ADJ, layers, collapsible modes -->
        <nav class="fixed right-0 top-0 bottom-0 z-40 flex w-[var(--hud-right-rail)] flex-col items-center justify-center overflow-visible border-l border-stone-800/50 bg-stone-900/40 px-1.5 pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)] backdrop-blur-md" aria-label="HUD 工具与模式 / HUD tools and modes">
            <!-- 模式 + 调节 + 图层 + 设置（模式与设置已对调）/ Mode, ADJ, MOD, Settings -->
            <div class="flex w-full flex-col items-center gap-3 sm:gap-4">
                <!-- 模式：与 ADJ/MOD 同风格；列表向画面内侧（左）飞出 / Mode flyout toward viewport -->
                <div class="relative flex w-full flex-col items-center">
                <button type="button" id="mode-rail-toggle" class="group flex flex-col items-center gap-1" aria-expanded="false" aria-controls="mode-rail-panel" aria-haspopup="true">
                    <div class="relative flex h-11 w-11 items-center justify-center border border-stone-700 transition-colors duration-100 group-hover:border-primary/60 group-active:scale-95 sm:h-12 sm:w-12">
                        <span class="material-symbols-outlined text-xl text-stone-500 transition-colors group-hover:text-primary sm:text-[22px]" aria-hidden="true">view_cozy</span>
                        <span class="material-symbols-outlined pointer-events-none absolute bottom-0.5 right-0.5 text-[14px] text-stone-500 transition-transform group-hover:text-primary" id="mode-rail-chevron" aria-hidden="true">expand_more</span>
                    </div>
                    <span class="font-headline text-[8px] tracking-widest text-stone-500 transition-colors group-hover:text-primary sm:text-[9px]">模式 / MODE</span>
                </button>
                <div id="mode-rail-panel" class="hud-mode-flyout pointer-events-auto hidden flex flex-col items-stretch gap-0 overflow-y-auto overscroll-contain border border-outline-variant/30 bg-stone-900/90 backdrop-blur-md" role="menu" aria-label="工作模式 / Work modes">
                    <button type="button" class="mode-button active flex flex-col items-center gap-0.5 border-b border-stone-800/60 py-2.5 text-stone-500 transition-all duration-300 hover:text-red-300" data-mode="polar" role="menuitem">
                        <span class="material-symbols-outlined text-[22px]" aria-hidden="true">visibility</span>
                        <span class="font-headline text-center text-[8px] leading-tight tracking-widest">观测</span>
                        <span class="hidden font-headline text-[6px] tracking-widest text-stone-500 opacity-80 sm:block">SIGHT</span>
                    </button>
                    <button type="button" class="mode-button flex flex-col items-center gap-0.5 border-b border-stone-800/60 py-2.5 text-stone-500 transition-all duration-300 hover:text-red-300" data-mode="star" role="menuitem">
                        <span class="material-symbols-outlined text-[22px]" aria-hidden="true">flare</span>
                        <span class="font-headline text-center text-[8px] leading-tight tracking-widest">寻星</span>
                        <span class="hidden font-headline text-[6px] tracking-widest text-stone-500 opacity-80 sm:block">STAR</span>
                    </button>
                    <button type="button" class="mode-button flex flex-col items-center gap-0.5 py-2.5 text-stone-500 transition-all duration-300 hover:text-red-300" data-mode="guide" role="menuitem">
                        <span class="material-symbols-outlined text-[22px]" aria-hidden="true">architecture</span>
                        <span class="font-headline text-center text-[8px] leading-tight tracking-widest">导星</span>
                        <span class="hidden font-headline text-[6px] tracking-widest text-stone-500 opacity-80 sm:block">GUIDE</span>
                    </button>
                </div>
                </div>
                <div class="relative flex w-full flex-col items-center">
                <button type="button" id="adj-rail-toggle" class="group flex flex-col items-center gap-1" aria-expanded="false" aria-controls="adj-rail-panel" aria-haspopup="true">
                    <div class="flex h-11 w-11 items-center justify-center border border-primary/40 transition-colors duration-100 group-hover:bg-primary/20 group-active:scale-95 sm:h-12 sm:w-12">
                        <span class="material-symbols-outlined text-xl text-primary sm:text-[22px]" aria-hidden="true">tune</span>
                    </div>
                    <span class="font-headline text-[8px] font-bold tracking-widest text-primary sm:text-[9px]">调节 / ADJ</span>
                </button>
                <div id="adj-rail-panel" class="hud-mode-flyout pointer-events-auto hidden flex flex-col items-stretch gap-1 overflow-y-auto overscroll-contain border border-outline-variant/30 bg-stone-900/90 p-2 backdrop-blur-md" role="menu" aria-label="用户调节 / User adjustment">
                    <label class="flex items-center justify-between gap-2 text-[10px] text-stone-300" for="adj-stream-quality">
                        <span class="font-headline text-[8px] tracking-widest text-stone-500">视频质量 / STREAM</span>
                        <span class="tabular-nums text-stone-400" id="adj-stream-quality-value">60</span>
                    </label>
                    <input id="adj-stream-quality" type="range" min="35" max="95" step="1" value="60" class="w-full accent-[rgb(248,113,113)]">
                    <label class="mt-1 flex items-center justify-between gap-2 text-[10px] text-stone-300" for="adj-solve-interval">
                        <span class="font-headline text-[8px] tracking-widest text-stone-500">解算间隔 / SOLVE</span>
                        <span class="tabular-nums text-stone-400" id="adj-solve-interval-value">1500 ms</span>
                    </label>
                    <input id="adj-solve-interval" type="range" min="500" max="10000" step="100" value="1500" class="w-full accent-[rgb(248,113,113)]">
                    <div class="mt-1 flex items-center justify-between gap-1">
                        <button type="button" id="adj-auto-exposure" class="flex-1 border border-stone-700 px-2 py-1 text-[10px] text-stone-300 transition-colors hover:border-primary/60 hover:text-primary">自动曝光</button>
                        <button type="button" id="adj-night-mode" class="flex-1 border border-stone-700 px-2 py-1 text-[10px] text-stone-300 transition-colors hover:border-primary/60 hover:text-primary">夜间模式</button>
                    </div>
                </div>
                </div>
                <div class="relative flex w-full flex-col items-center">
                <button type="button" id="layer-rail-toggle" class="group flex flex-col items-center gap-1" aria-expanded="false" aria-controls="layer-rail-panel" aria-haspopup="true">
                    <div class="flex h-11 w-11 items-center justify-center border border-stone-700 transition-colors duration-100 group-hover:border-primary/60 group-active:scale-95 sm:h-12 sm:w-12">
                        <span class="material-symbols-outlined text-xl text-stone-500 transition-colors group-hover:text-primary sm:text-[22px]" aria-hidden="true">layers</span>
                    </div>
                    <span class="font-headline text-[8px] tracking-widest text-stone-500 transition-colors group-hover:text-primary sm:text-[9px]">图层 / MOD</span>
                </button>
                <div id="layer-rail-panel" class="hud-mode-flyout pointer-events-auto hidden flex flex-col items-stretch gap-1 overflow-y-auto overscroll-contain border border-outline-variant/30 bg-stone-900/90 p-2 backdrop-blur-md" role="menu" aria-label="图层控制 / Layer controls">
                    <label class="flex items-center gap-2 text-[10px] text-stone-300"><input id="layer-video" type="checkbox" checked> 视频流 / Stream</label>
                    <label class="flex items-center gap-2 text-[10px] text-stone-300"><input id="layer-all" type="checkbox" checked> 全部质心 / All centroids</label>
                    <label class="flex items-center gap-2 text-[10px] text-stone-300"><input id="layer-matched" type="checkbox" checked> 匹配星 / Matched stars</label>
                    <label class="flex items-center gap-2 text-[10px] text-stone-300"><input id="layer-pattern" type="checkbox" checked> 图案星 / Pattern stars</label>
                    <label class="flex items-center gap-2 text-[10px] text-stone-300"><input id="layer-rejected" type="checkbox" checked> 排除质心 / Rejected</label>
                </div>
                </div>
                <a href="/debug" class="group flex flex-col items-center gap-1 no-underline">
                    <div class="flex h-11 w-11 items-center justify-center border border-stone-700 transition-colors duration-100 group-hover:border-primary/60 group-active:scale-95 sm:h-12 sm:w-12">
                        <span class="material-symbols-outlined text-xl text-stone-500 transition-colors group-hover:text-primary sm:text-[22px]" aria-hidden="true">settings</span>
                    </div>
                    <span class="font-headline text-[8px] tracking-widest text-stone-500 transition-colors group-hover:text-primary sm:text-[9px]">设置 / SET</span>
                </a>
            </div>
        </nav>

        <!-- 主画面全屏铺满，顶底栏仅悬浮叠在上面 / Main viewport full-bleed; top/bottom bars float above -->
        <main class="fixed inset-0 z-10 flex flex-col overflow-hidden">
            <div class="hud-viewport-host">
                <div class="hud-viewport-center">
                    <div class="relative hud-viewport-frame border border-outline-variant/20 bg-surface-container-lowest overflow-hidden">
                <img id="video-stream" class="absolute inset-0 w-full h-full object-cover z-0" alt="实时视频流 / Live stream">
                <canvas id="analysis-overlay-canvas" class="absolute inset-0 w-full h-full pointer-events-none z-[18]"></canvas>
                <div class="absolute inset-0 hud-corner-mask z-10 pointer-events-none"></div>

                <div class="absolute inset-0 z-20 flex items-center justify-center pointer-events-none">
                    <div class="absolute w-[30%] aspect-square border border-outline/20 rounded-full"></div>
                    <div class="absolute w-[46%] aspect-square border border-outline/10 rounded-full"></div>
                    <div class="absolute w-[15%] aspect-square border border-outline/40 rounded-full"></div>
                    <div class="absolute w-full h-[0.5px] bg-outline/20"></div>
                    <div class="absolute h-full w-[0.5px] bg-outline/20"></div>
                    <div id="polar-reference" class="absolute hidden flex -translate-x-1/2 -translate-y-1/2 flex-col items-center">
                        <div class="w-3 h-3 bg-primary border border-on-primary-container shadow-[0_0_12px_rgba(255,85,64,0.6)]"></div>
                        <span class="font-headline text-[9px] sm:text-[10px] text-primary mt-2 glow-red">北极星参考 / POLARIS</span>
                    </div>
                    <div id="polar-guide-line" class="guide-line hidden z-30"></div>
                </div>

                <div class="absolute inset-0 hud-scanline pointer-events-none opacity-20 z-[25]"></div>
                <div id="solve-radar-scan" class="absolute inset-0 pointer-events-none z-[26] opacity-0"></div>

                <!-- 左右内缩避让侧栏；上下 padding 不变 / Horizontal inset clears side rails; vertical padding unchanged -->
                <div class="pointer-events-none absolute inset-0 z-[30] flex flex-col justify-between pt-4 pb-4 pl-[calc(var(--hud-left-rail)+1.5rem)] pr-[calc(var(--hud-right-rail)+1.5rem)] sm:pt-8 sm:pb-8 sm:pl-[calc(var(--hud-left-rail)+2.25rem)] sm:pr-[calc(var(--hud-right-rail)+2.25rem)]">
                    <div class="flex justify-end items-start">
                        <div class="flex flex-col gap-1 text-right">
                            <span class="font-headline text-[9px] sm:text-[10px] tracking-[0.15rem] text-primary/60">FOV 6.5°</span>
                            <span class="font-headline text-[9px] sm:text-[10px] tracking-[0.15rem] text-primary/60">MAG 14.2×</span>
                        </div>
                    </div>
                    <div class="flex justify-between items-end gap-2 sm:gap-3">
                        <div class="max-w-[38%] border-l-2 border-primary/80 bg-primary/5 p-2 backdrop-blur-sm sm:max-w-[210px] sm:p-2.5">
                            <div class="mb-0.5 font-headline text-[8px] uppercase tracking-widest text-primary/90 sm:text-[9px]">星点质量 / Stars</div>
                            <div class="mb-0.5 h-0.5 w-full overflow-hidden bg-primary/20">
                                <div id="quality-fill" class="h-full bg-primary" style="width:72%"></div>
                            </div>
                            <span class="font-body text-[9px] text-on-surface-variant sm:text-[10px]" id="quality-value">0%</span>
                        </div>
                        <div class="min-w-0 max-w-[55%] text-right sm:max-w-[48%]">
                            <div class="font-headline text-[8px] uppercase tracking-widest text-primary/90 sm:text-[9px]">对准误差 / Error</div>
                            <div class="font-headline text-lg tabular-nums tracking-tight text-primary glow-red sm:text-xl" id="alignment-error">--</div>
                            <div class="text-[7px] uppercase text-stone-500 sm:text-[8px]">角秒 RMS / arcsec</div>
                            <div class="mt-1 font-mono text-[8px] text-stone-400 sm:mt-1.5 sm:text-[9px]">
                                <span id="azimuth-offset">+0.0°</span> <span class="text-stone-600">|</span> <span id="altitude-offset">+0.0°</span>
                            </div>
                        </div>
                    </div>
                </div>
                    </div>
                </div>
            </div>
        </main>

        <!-- 底栏 / Footer（四项居中，贴底；版本号已移至顶栏） -->
        <footer class="pointer-events-none fixed bottom-0 left-0 right-0 z-50 box-border flex h-[calc(var(--hud-footer-h)+env(safe-area-inset-bottom,0px))] items-center bg-transparent pl-[var(--hud-left-rail)] pr-[var(--hud-right-rail)] pb-[env(safe-area-inset-bottom,0px)] pt-1 sm:px-6">
            <div class="pointer-events-auto mx-auto flex w-full max-w-full flex-wrap items-center justify-center gap-x-5 gap-y-1 sm:gap-x-8 lg:gap-x-12">
                <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-red-500 drop-shadow-[0_0_8px_rgba(255,85,64,0.4)]" aria-hidden="true">gps_fixed</span>
                    <span class="font-headline text-[9px] sm:text-[10px] text-red-400 tracking-widest">极轴锁定 / LOCK</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-stone-600" aria-hidden="true">height</span>
                    <span class="font-headline text-[9px] sm:text-[10px] text-stone-600 tracking-widest">赤纬 / DEC <span class="tabular-nums">--</span></span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-stone-600" aria-hidden="true">adjust</span>
                    <span class="font-headline text-[9px] sm:text-[10px] text-stone-600 tracking-widest">ISO --</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="material-symbols-outlined text-stone-600" aria-hidden="true">stars</span>
                    <span class="font-headline text-[9px] sm:text-[10px] text-stone-600 tracking-widest">曝光 / EXP --</span>
                </div>
            </div>
        </footer>

        <!-- 景深遮罩（低于顶栏/侧栏，避免挡交互）/ Vignette below chrome -->
        <div class="pointer-events-none fixed inset-0 z-[15] hud-corner-vignette"></div>

        <!-- 保留旧版菜单与快门 DOM id，供后续接线 / Legacy menu & shutter hooks -->
        <button type="button" class="menu-button hidden fixed w-px h-px overflow-hidden opacity-0" id="menu-button" tabindex="-1" aria-hidden="true">☰</button>
        <div class="menu-panel hidden fixed w-px h-px overflow-hidden opacity-0 pointer-events-none" id="menu-panel" aria-hidden="true">
            <button type="button" id="menu-close" tabindex="-1">×</button>
        </div>
        <div class="hidden fixed w-px h-px overflow-hidden opacity-0 pointer-events-none" id="shutter-tools" aria-hidden="true">
            <button type="button" class="shutter-mode" data-mode="single"></button>
            <button type="button" id="shutter-button"></button>
            <div id="shutter-timer"></div>
        </div>
        <button type="button" class="hidden" id="shutter-toggle" tabindex="-1" aria-hidden="true"></button>
        <button type="button" class="advanced-button hidden fixed w-px h-px overflow-hidden opacity-0" tabindex="-1" aria-hidden="true">高级</button>
    </div>
`;function f(){function s(p,n,u){const r=document.getElementById(p),a=document.getElementById(n),o=u?document.getElementById(u):null;if(!r||!a)return null;function c(){if(a.classList.contains("hidden"))return;const l=r.getBoundingClientRect();a.style.top=`${l.top}px`,a.style.right=`${Math.max(0,window.innerWidth-l.left+6)}px`,a.style.left="auto",a.style.maxHeight=`${Math.min(window.innerHeight-l.top-8,window.innerHeight*.65)}px`}function x(){a.classList.add("hidden"),r.setAttribute("aria-expanded","false"),o&&(o.style.transform="")}return r.addEventListener("click",()=>{a.classList.toggle("hidden");const l=!a.classList.contains("hidden");r.setAttribute("aria-expanded",l?"true":"false"),o&&(o.style.transform=l?"rotate(180deg)":""),l&&requestAnimationFrame(c)}),window.addEventListener("resize",c),window.addEventListener("orientationchange",()=>{setTimeout(c,100)}),{closeFlyout:x}}const e=s("mode-rail-toggle","mode-rail-panel","mode-rail-chevron"),t=s("adj-rail-toggle","adj-rail-panel"),i=s("layer-rail-toggle","layer-rail-panel"),d=document.getElementById("mode-rail-panel");d&&e&&d.querySelectorAll(".mode-button").forEach(p=>{p.addEventListener("click",()=>{e.closeFlyout()})}),document.addEventListener("click",p=>{const n=p.target;if(!(n instanceof Element))return;const u=[["mode-rail-toggle","mode-rail-panel",e],["adj-rail-toggle","adj-rail-panel",t],["layer-rail-toggle","layer-rail-panel",i]];for(const[r,a,o]of u){const c=document.getElementById(r),x=document.getElementById(a);!c||!x||!o||c.contains(n)||x.contains(n)||o.closeFlyout()}})}const g=["/static/js/shared/utils.js","/static/js/shared/constants.js","/static/js/shared/api.js","/static/js/core/ui.js","/static/js/core/camera.js","/static/js/core/alignment.js","/static/js/app-home-analysis.js"];function y(s){return s.reduce((e,t)=>e.then(()=>new Promise((i,d)=>{if(document.querySelector(`script[src="${t}"]`)){i();return}const n=document.createElement("script");n.src=t,n.async=!1,n.onload=()=>i(),n.onerror=()=>d(new Error(`Failed to load ${t}`)),document.body.appendChild(n)})),Promise.resolve())}function w(){const s=m.useRef(null);return m.useLayoutEffect(()=>{const e=s.current;if(!e)return;e.innerHTML="";const t=document.createElement("template");t.innerHTML=v.trim(),e.appendChild(t.content.cloneNode(!0));let i=!1;return y(g).then(()=>{i||f()}).catch(d=>{console.error(d)}),()=>{i=!0,e.innerHTML=""}},[]),m.useEffect(()=>{fetch("/api").then(e=>e.json()).then(e=>{const t=document.getElementById("hud-app-version");t&&(t.textContent=e.version??"—")}).catch(()=>{const e=document.getElementById("hud-app-version");e&&(e.textContent="—")})},[]),h.jsx("div",{className:"h-dvh max-h-dvh overflow-hidden bg-background text-on-background font-body select-none",ref:s})}b(document.getElementById("root")).render(h.jsx(w,{}));
