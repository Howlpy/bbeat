/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

import { build, files, version } from '$service-worker';

const sw = self as unknown as ServiceWorkerGlobalScope;
const CACHE = `bbeat-cache-${version}`;
const ASSETS = [...build, ...files];

// Precache assets del build (JS/CSS) e iconos al instalar.
sw.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      await cache.addAll(ASSETS);
      await sw.skipWaiting();
    })()
  );
});

// Limpia caches de versiones previas al activar.
sw.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
      await sw.clients.claim();
    })()
  );
});

sw.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Audio y covers: SIEMPRE pasar a red, nunca cachear (carátulas son livianas, audio es enorme).
  if (url.pathname.startsWith('/api/library/stream/')) return;
  if (url.pathname.startsWith('/api/library/cover/')) return;
  // Resto de /api: passthrough (lecturas dinámicas)
  if (url.pathname.startsWith('/api/')) return;

  // Solo same-origin para assets
  if (url.origin !== sw.location.origin) return;

  event.respondWith(
    (async () => {
      const cached = await caches.match(req);
      if (cached) return cached;
      try {
        return await fetch(req);
      } catch {
        // Si falla y no hay caché, devolvemos un 503 mínimo
        return new Response('offline', { status: 503 });
      }
    })()
  );
});
