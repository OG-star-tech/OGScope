/**
 * OGScope 粒子背景效果模块 / OGScope particle background effect module
 * 创建动态粒子背景效果 / Create dynamic particle background effects
 */

import { Utils, EventEmitter } from '../shared/utils.js';
import { APP_CONFIG } from '../shared/constants.js';

export class ParticleSystem extends EventEmitter {
    constructor() {
        super();
        this.particles = [];
        this.maxParticles = APP_CONFIG.UI.MAX_PARTICLES;
        this.canvas = null;
        this.ctx = null;
        this.animationId = null;
        this.isRunning = false;
        this.init();
    }

    /**
     * 初始化粒子系统 / Initialize particle system
     */
    init() {
        this.createCanvas();
        this.setupEventListeners();
    }

    /**
     * 创建画布 / Create canvas
     */
    createCanvas() {
        // 查找或创建粒子容器 / Find or create a particle container
        let container = document.getElementById('particles-bg');
        if (!container) {
            container = document.createElement('div');
            container.id = 'particles-bg';
            container.className = 'particles-background';
            document.body.appendChild(container);
        }

        // 创建画布 / Create canvas
        this.canvas = document.createElement('canvas');
        this.canvas.className = 'particles-canvas';
        this.canvas.style.position = 'fixed';
        this.canvas.style.top = '0';
        this.canvas.style.left = '0';
        this.canvas.style.width = '100%';
        this.canvas.style.height = '100%';
        this.canvas.style.pointerEvents = 'none';
        this.canvas.style.zIndex = '-1';
        
        container.appendChild(this.canvas);
        this.ctx = this.canvas.getContext('2d');
        
        this.resizeCanvas();
    }

    /**
     * 设置事件监听器 / Set event listener
     */
    setupEventListeners() {
        // 窗口大小变化 / Window size changes
        window.addEventListener('resize', Utils.debounce(() => {
            this.resizeCanvas();
        }, 100));

        // 页面可见性变化 / Page visibility changes
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.pause();
            } else {
                this.resume();
            }
        });
    }

    /**
     * 调整画布大小 / Resize canvas
     */
    resizeCanvas() {
        if (!this.canvas) return;

        const rect = this.canvas.getBoundingClientRect();
        this.canvas.width = rect.width * window.devicePixelRatio;
        this.canvas.height = rect.height * window.devicePixelRatio;
        
        this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
        
        // 重新创建粒子以适应新尺寸 / Recreate particles to fit new dimensions
        this.createParticles();
    }

    /**
     * 创建粒子 / Create particles
     */
    createParticles() {
        this.particles = [];
        
        for (let i = 0; i < this.maxParticles; i++) {
            this.particles.push(this.createParticle());
        }
    }

    /**
     * 创建单个粒子 / Create a single particle
     * @returns {Object} 粒子对象 / particle object
     */
    createParticle() {
        const canvas = this.canvas;
        const rect = canvas.getBoundingClientRect();
        
        return {
            x: Math.random() * rect.width,
            y: Math.random() * rect.height,
            vx: (Math.random() - 0.5) * 0.5,
            vy: (Math.random() - 0.5) * 0.5,
            size: Math.random() * 2 + 1,
            opacity: Math.random() * 0.5 + 0.2,
            color: this.getRandomColor(),
            life: 1.0,
            maxLife: Math.random() * 200 + 100
        };
    }

    /**
     * 获取随机颜色 / Get a random color
     * @returns {string} 颜色值 / color value
     */
    getRandomColor() {
        const colors = [
            '#FF4500', // 橙红色 / orange red
            '#FF6B35', // 亮橙红 / bright orange red
            '#8B0000', // 深红色 / deep red
            '#FFB800', // 黄色 / yellow
            '#00FFFF', // 青色 / blue
            '#FFFFFF'  // 白色 / White
        ];
        return colors[Math.floor(Math.random() * colors.length)];
    }

    /**
     * 开始粒子动画 / Start particle animation
     */
    start() {
        if (this.isRunning) return;
        
        this.isRunning = true;
        this.animate();
        console.log('[Particles] 粒子系统启动');
    }

    /**
     * 停止粒子动画 / Stop particle animation
     */
    stop() {
        this.isRunning = false;
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
        console.log('[Particles] 粒子系统停止');
    }

    /**
     * 暂停粒子动画 / Pause particle animation
     */
    pause() {
        this.isRunning = false;
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
    }

    /**
     * 恢复粒子动画 / Resume particle animation
     */
    resume() {
        if (!this.isRunning) {
            this.isRunning = true;
            this.animate();
        }
    }

    /**
     * 动画循环 / animation loop
     */
    animate() {
        if (!this.isRunning) return;

        this.update();
        this.render();
        
        this.animationId = requestAnimationFrame(() => this.animate());
    }

    /**
     * 更新粒子状态 / Update particle status
     */
    update() {
        const canvas = this.canvas;
        const rect = canvas.getBoundingClientRect();
        
        this.particles.forEach((particle, index) => {
            // 更新位置 / Update location
            particle.x += particle.vx;
            particle.y += particle.vy;
            
            // 更新生命周期 / Update life cycle
            particle.life -= 1 / particle.maxLife;
            
            // 边界检查 / Boundary checking
            if (particle.x < 0 || particle.x > rect.width) {
                particle.vx *= -1;
                particle.x = Utils.clamp(particle.x, 0, rect.width);
            }
            
            if (particle.y < 0 || particle.y > rect.height) {
                particle.vy *= -1;
                particle.y = Utils.clamp(particle.y, 0, rect.height);
            }
            
            // 重新生成死亡粒子 / Regenerate dead particles
            if (particle.life <= 0) {
                this.particles[index] = this.createParticle();
            }
        });
    }

    /**
     * 渲染粒子 / render particles
     */
    render() {
        if (!this.ctx || !this.canvas) return;

        const canvas = this.canvas;
        const rect = canvas.getBoundingClientRect();
        
        // 清除画布 / clear canvas
        this.ctx.clearRect(0, 0, rect.width, rect.height);
        
        // 绘制粒子 / Draw particles
        this.particles.forEach(particle => {
            this.ctx.save();
            this.ctx.globalAlpha = particle.opacity * particle.life;
            this.ctx.fillStyle = particle.color;
            this.ctx.beginPath();
            this.ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.restore();
        });
        
        // 绘制连接线 / Draw connecting lines
        this.drawConnections();
    }

    /**
     * 绘制粒子连接线 / Draw particle connection lines
     */
    drawConnections() {
        const canvas = this.canvas;
        const rect = canvas.getBoundingClientRect();
        const maxDistance = 100;
        
        for (let i = 0; i < this.particles.length; i++) {
            for (let j = i + 1; j < this.particles.length; j++) {
                const particle1 = this.particles[i];
                const particle2 = this.particles[j];
                
                const distance = Utils.calculateDistance(
                    { x: particle1.x, y: particle1.y },
                    { x: particle2.x, y: particle2.y }
                );
                
                if (distance < maxDistance) {
                    const opacity = (1 - distance / maxDistance) * 0.1;
                    
                    this.ctx.save();
                    this.ctx.globalAlpha = opacity;
                    this.ctx.strokeStyle = '#FF4500';
                    this.ctx.lineWidth = 1;
                    this.ctx.beginPath();
                    this.ctx.moveTo(particle1.x, particle1.y);
                    this.ctx.lineTo(particle2.x, particle2.y);
                    this.ctx.stroke();
                    this.ctx.restore();
                }
            }
        }
    }

    /**
     * 设置粒子数量 / Set the number of particles
     * @param {number} count - 粒子数量 / number of particles
     */
    setParticleCount(count) {
        this.maxParticles = Utils.clamp(count, 10, 100);
        this.createParticles();
    }

    /**
     * 获取粒子数量 / Get the number of particles
     * @returns {number} 当前粒子数量 / current number of particles
     */
    getParticleCount() {
        return this.maxParticles;
    }

    /**
     * 销毁粒子系统 / Destroy particle system
     */
    destroy() {
        this.stop();
        
        if (this.canvas && this.canvas.parentNode) {
            this.canvas.parentNode.removeChild(this.canvas);
        }
        
        this.particles = [];
        this.canvas = null;
        this.ctx = null;
        this.removeAllListeners();
    }
}
