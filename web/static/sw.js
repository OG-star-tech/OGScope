/**
 * OGScope Service Worker
 * 实现PWA离线功能和缓存策略 / Implement PWA offline functions and caching strategies
 */

const CACHE_NAME = 'ogscope-v1.0.0';
const STATIC_CACHE = 'ogscope-static-v1';
const DYNAMIC_CACHE = 'ogscope-dynamic-v1';

// 需要缓存的静态资源 / Static resources that need to be cached
const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/images/icon-192x192.png',
  '/static/images/icon-512x512.png',
  '/manifest.json'
];

// 需要缓存的API路径模式 / API path patterns that need to be cached
const API_CACHE_PATTERNS = [
  /^\/api\/camera\/config/,
  /^\/api\/status/
];

// 不需要缓存的路径 / No cached path is required
// MJPEG（multipart/x-mixed-replace）为长连接无限流，禁止走 networkFirst 的 cache.put，
// 否则第二路流可能黑屏/异常且不易报错（与打开顺序相关）/ Infinite MJPEG must bypass SW cache.put.
const NO_CACHE_PATTERNS = [
  /^\/api\/websocket/,
  /^\/api\/camera\/stream/,
  /^\/api\/debug\/camera\/stream/,
  /^\/api\/dev\/debug\/camera\/stream/,
];

/**
 * 安装事件 - 缓存静态资源 / Installation events - caching static resources
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
 * 激活事件 - 清理旧缓存 / Activation event - clean old cache
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
 * 获取事件 - 实现缓存策略 / Get events - implement caching strategy
 */
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);
  
  // 跳过非HTTP请求 / Skip non-HTTP requests
  if (!url.protocol.startsWith('http')) {
    return;
  }
  
  // 跳过不需要缓存的路径 / Skip paths that don't need to be cached
  if (NO_CACHE_PATTERNS.some(pattern => pattern.test(url.pathname))) {
    return;
  }
  
  // 静态资源缓存优先策略 / Static resource cache priority strategy
  if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  
  // API请求网络优先策略 / API request network priority policy
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }
  
  // 页面请求缓存优先策略 / Page request cache priority strategy
  if (request.mode === 'navigate') {
    event.respondWith(cacheFirst(request));
    return;
  }
  
  // 其他请求网络优先 / Other requests network priority
  event.respondWith(networkFirst(request));
});

/**
 * 缓存优先策略 / Cache priority strategy
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
 * 网络优先策略 / network first policy
 */
async function networkFirst(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const ct = (networkResponse.headers.get('content-type') || '').toLowerCase();
      if (!ct.includes('multipart/x-mixed-replace')) {
        const cache = await caches.open(DYNAMIC_CACHE);
        cache.put(request, networkResponse.clone());
      }
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', error);
    
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // 返回离线页面或错误响应 / Return offline page or error response
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
 * 推送通知事件 / Push notification events
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
 * 通知点击事件 / Notification click event
 */
self.addEventListener('notificationclick', event => {
  console.log('[SW] Notification clicked:', event.notification.tag);
  
  event.notification.close();
  
  if (event.action === 'explore') {
    event.waitUntil(
      clients.openWindow('/')
    );
  } else if (event.action === 'close') {
    // 关闭通知，不做任何操作 / Turn off notifications and do nothing
  } else {
    // 默认行为：打开应用 / Default behavior: Open app
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
 * 后台同步事件 / Background sync events
 */
self.addEventListener('sync', event => {
  console.log('[SW] Background sync:', event.tag);
  
  if (event.tag === 'background-sync') {
    event.waitUntil(doBackgroundSync());
  }
});

/**
 * 执行后台同步 / Perform background sync
 */
async function doBackgroundSync() {
  try {
    // 同步相机配置 / Sync camera configuration
    await syncCameraConfig();
    
    // 同步校准数据 / Synchronize calibration data
    await syncAlignmentData();
    
    console.log('[SW] Background sync completed');
  } catch (error) {
    console.error('[SW] Background sync failed:', error);
  }
}

/**
 * 同步相机配置 / Sync camera configuration
 */
async function syncCameraConfig() {
  // 从IndexedDB获取待同步的配置 / Get the configuration to be synchronized from IndexedDB
  // 发送到服务器 / Send to server
  // 清理本地数据 / Clean local data
}

/**
 * 同步校准数据 / Synchronize calibration data
 */
async function syncAlignmentData() {
  // 从IndexedDB获取待同步的校准数据 / Get calibration data to be synchronized from IndexedDB
  // 发送到服务器 / Send to server
  // 清理本地数据 / Clean local data
}

/**
 * 消息事件处理 / Message event handling
 */
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'GET_VERSION') {
    event.ports[0].postMessage({ version: CACHE_NAME });
  }
});
