/* ================================================================
   AiDash Service Worker（B 部分）
   作用：把 App 外壳缓存到本机，离线也能打开；
   Vercel 接口和 GitHub 数据请求不做缓存（保证数据最新）。
   ================================================================ */
var CACHE_NAME = "aidash-shell-v1";

/* 需要缓存的静态文件（相对本文件路径） */
var ASSETS = [
  "./index.html",
  "./config.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png"
];

/* 安装：预缓存外壳文件 */
self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function (cache) { return cache.addAll(ASSETS); })
      .then(function () { return self.skipWaiting(); })
  );
});

/* 激活：清理旧版本缓存 */
self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        if (key !== CACHE_NAME) { return caches.delete(key); }
        return null;
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

/* 请求拦截 */
self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") { return; }
  var url = new URL(req.url);

  /* 只处理本站请求；Vercel 接口、GitHub raw 等跨域请求不缓存 */
  if (url.origin !== self.location.origin) { return; }

  /* 页面导航：网络优先（能拿到最新版本），失败时用缓存兜底 */
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).then(function (res) {
        var copy = res.clone();
        caches.open(CACHE_NAME).then(function (cache) { cache.put("./index.html", copy); });
        return res;
      }).catch(function () {
        return caches.match("./index.html");
      })
    );
    return;
  }

  /* 静态资源：先返回缓存，同时后台更新（stale-while-revalidate） */
  event.respondWith(
    caches.match(req).then(function (cached) {
      var network = fetch(req).then(function (res) {
        if (res && res.ok) {
          var copy = res.clone();
          caches.open(CACHE_NAME).then(function (cache) { cache.put(req, copy); });
        }
        return res;
      }).catch(function () { return cached; });
      return cached || network;
    })
  );
});
