self.addEventListener("install", e => {
  e.waitUntil(
    caches.open("mms-cache").then(cache => {
      return cache.addAll(["/", "/static/manifest.json"]);
    })
  );
});

self.addEventListener("fetch", e => {
  e.respondWith(
    caches.match(e.request).then(response => {
      return response || fetch(e.request);
    })
  );
});
