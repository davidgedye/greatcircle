const CACHE_NAME = 'greatcircle-v16';

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll([
      '/greatcircle/',
      '/greatcircle/index.html',
    ]))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  // Only handle same-origin requests (the HTML shell).
  // Mapbox CDN and data JSON are fetched directly by the page.
  if (!event.request.url.startsWith(self.location.origin)) return;

  // Network-first: always try to get a fresh copy; fall back to cache if offline.
  event.respondWith(
    fetch(event.request).then(response => {
      const copy = response.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
      return response;
    }).catch(() => caches.match(event.request))
  );
});
