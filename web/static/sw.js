/**
 * OGScope Service Worker
 * 实现PWA离线功能和缓存策略
 */

const CACHE_NAME = 'ogscope-v1.0.0';
const STATIC_CACHE = 'ogscope-static-v1';
const DYNAMIC_CACHE = 'ogscope-dynamic-v1';

// 需要缓存的静态资源
const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/images/icon-192x192.png',
  '/static/images/icon-512x512.png',
  '/manifest.json'
];

// 需要缓存的API路径模式
const API_CACHE_PATTERNS = [
  /^\/api\/camera\/preview/,
  /^\/api\/camera\/config/,
  /^\/api\/status/
];

// 不需要缓存的路径
const NO_CACHE_PATTERNS = [
  /^\/api\/camera\/stream/,
  /^\/api\/websocket/
];

/**
 * 安装事件 - 缓存静态资源
 */
self.addEventListener('install', event => {
  console.log('[SW] Installing Service Worker...');
  
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => {
        console.log('[SW] Caching static assets...');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log('[SW] Static assets cached successfully');
        return self.skipWaiting();
      })
      .catch(error => {
        console.error('[SW] Failed to cache static assets:', error);
      })
  );
});

/**
 * 激活事件 - 清理旧缓存
 */
self.addEventListener('activate', event => {
  console.log('[SW] Activating Service Worker...');
  
  event.waitUntil(
    caches.keys()
      .then(cacheNames => {
        return Promise.all(
          cacheNames.map(cacheName => {
            if (cacheName !== STATIC_CACHE && cacheName !== DYNAMIC_CACHE) {
              console.log('[SW] Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log('[SW] Service Worker activated');
        return self.clients.claim();
      })
  );
});

/**
 * 获取事件 - 实现缓存策略
 */
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);
  
  // 跳过非HTTP请求
  if (!url.protocol.startsWith('http')) {
    return;
  }
  
  // 跳过不需要缓存的路径
  if (NO_CACHE_PATTERNS.some(pattern => pattern.test(url.pathname))) {
    return;
  }
  
  // 静态资源缓存优先策略
  if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  
  // API请求网络优先策略
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }
  
  // 页面请求缓存优先策略
  if (request.mode === 'navigate') {
    event.respondWith(cacheFirst(request));
    return;
  }
  
  // 其他请求网络优先
  event.respondWith(networkFirst(request));
});

/**
 * 缓存优先策略
 */
async function cacheFirst(request) {
  try {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.error('[SW] Cache first failed:', error);
    return new Response('离线模式 - 资源不可用', { 
      status: 503,
      statusText: 'Service Unavailable'
    });
  }
}

/**
 * 网络优先策略
 */
async function networkFirst(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', error);
    
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // 返回离线页面或错误响应
    if (request.mode === 'navigate') {
      return caches.match('/offline.html');
    }
    
    return new Response(JSON.stringify({
      error: '网络连接失败',
      offline: true,
      message: '请检查网络连接或稍后重试'
    }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

/**
 * 推送通知事件
 */
self.addEventListener('push', event => {
  console.log('[SW] Push message received');
  
  const options = {
    body: event.data ? event.data.text() : 'OGScope通知',
    icon: '/static/images/icon-192x192.png',
    badge: '/static/images/badge-72x72.png',
    vibrate: [200, 100, 200],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'explore',
        title: '查看详情',
        icon: '/static/images/checkmark.png'
      },
      {
        action: 'close',
        title: '关闭',
        icon: '/static/images/xmark.png'
      }
    ]
  };
  
  event.waitUntil(
    self.registration.showNotification('OGScope', options)
  );
});

/**
 * 通知点击事件
 */
self.addEventListener('notificationclick', event => {
  console.log('[SW] Notification clicked:', event.notification.tag);
  
  event.notification.close();
  
  if (event.action === 'explore') {
    event.waitUntil(
      clients.openWindow('/')
    );
  } else if (event.action === 'close') {
    // 关闭通知，不做任何操作
  } else {
    // 默认行为：打开应用
    event.waitUntil(
      clients.matchAll().then(clientList => {
        for (const client of clientList) {
          if (client.url === '/' && 'focus' in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) {
          return clients.openWindow('/');
        }
      })
    );
  }
});

/**
 * 后台同步事件
 */
self.addEventListener('sync', event => {
  console.log('[SW] Background sync:', event.tag);
  
  if (event.tag === 'background-sync') {
    event.waitUntil(doBackgroundSync());
  }
});

/**
 * 执行后台同步
 */
async function doBackgroundSync() {
  try {
    // 同步相机配置
    await syncCameraConfig();
    
    // 同步校准数据
    await syncAlignmentData();
    
    console.log('[SW] Background sync completed');
  } catch (error) {
    console.error('[SW] Background sync failed:', error);
  }
}

/**
 * 同步相机配置
 */
async function syncCameraConfig() {
  // 从IndexedDB获取待同步的配置
  // 发送到服务器
  // 清理本地数据
}

/**
 * 同步校准数据
 */
async function syncAlignmentData() {
  // 从IndexedDB获取待同步的校准数据
  // 发送到服务器
  // 清理本地数据
}

/**
 * 消息事件处理
 */
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'GET_VERSION') {
    event.ports[0].postMessage({ version: CACHE_NAME });
  }
});
