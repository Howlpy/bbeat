/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

import { build, files, prerendered, version } from '$service-worker';

const sw = self as unknown as ServiceWorkerGlobalScope;
const CACHE = `bbeat-cache-${version}`;
// El shell HTML es el fallback SPA: el backend lo sirve en cualquier ruta. NO
// está en build/files, así que hay que cachearlo aparte o la app no arranca offline.
const SHELL = '/';
const ASSETS = [...build, ...files, ...prerendered];

// Precache assets del build (JS/CSS), estáticos y el shell HTML al instalar.
sw.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      await cache.addAll(ASSETS);
      try {
        await cache.add(SHELL);
      } catch {
        // si falla (raro), seguimos: al menos los assets quedan cacheados
      }
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
  if (url.origin !== sw.location.origin) return;

  // Navegación (cargar la app): red primero; si no hay (offline), servir el shell
  // cacheado para que la SPA arranque y pueda ir a Descargas sin conexión.
  if (req.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          return await fetch(req);
        } catch {
          const cache = await caches.open(CACHE);
          return (
            (await cache.match(SHELL)) ||
            (await cache.match(req)) ||
            new Response('offline', { status: 503 })
          );
        }
      })()
    );
    return;
  }

  // Audio, carátulas y resto de /api: passthrough (datos dinámicos / enormes).
  if (url.pathname.startsWith('/api/')) return;

  // Assets estáticos: cache-first.
  event.respondWith(
    (async () => {
      const cached = await caches.match(req);
      if (cached) return cached;
      try {
        return await fetch(req);
      } catch {
        return new Response('offline', { status: 503 });
      }
    })()
  );
});
