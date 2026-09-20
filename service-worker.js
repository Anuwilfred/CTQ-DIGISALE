// C·TORQ Sales Command — service worker
// Caches the app shell so it opens instantly and still opens (read-only)
// with no signal. Bump CACHE_NAME whenever app files change so old
// installs pick up the new version instead of serving a stale copy.

const CACHE_NAME = 'ctorq-shell-v20';
const APP_SHELL = [
  './',
  './index.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png',
  './data/companies.json',
  './data/active_projects.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    ).then(() => self.clients.claim())
  );
});

// Network-first for navigation (so you always see the newest dashboard
// data when online), falling back to the cached shell when offline.
// Cache-first for the static shell files themselves.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => caches.match('./index.html'))
    );
    return;
  }

  // Data file: network-first, so a fresh companies.json (new leads, new
  // notes committed upstream) shows up without needing a hard refresh.
  // Falls back to the cached copy when offline.
  if (req.url.endsWith('/data/companies.json') || req.url.endsWith('/data/rss_signals.json') || req.url.endsWith('/data/active_projects.json')) {
    event.respondWith(
      fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
        }
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
        }
        return res;
      }).catch(() => cached);
    })
  );
});
