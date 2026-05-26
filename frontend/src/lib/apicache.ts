import { browser } from '$app/environment';

// Caché de respuestas GET de la API en IndexedDB. Sirve para que, al quedarse
// sin conexión, la interfaz siga mostrando lo último que se vio (como Spotify)
// en vez de pantallas de error. Cada URL guarda su último JSON.

const DB = 'bbeat-apicache';
const STORE = 'get';

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: 'url' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Guarda (o actualiza) la respuesta de una URL GET. No bloquea ni lanza. */
export async function cachePut(url: string, data: unknown): Promise<void> {
  if (!browser || !('indexedDB' in window)) return;
  try {
    const db = await openDB();
    await new Promise<void>((res, rej) => {
      const r = db.transaction(STORE, 'readwrite').objectStore(STORE).put({ url, data, ts: Date.now() });
      r.onsuccess = () => res();
      r.onerror = () => rej(r.error);
    });
  } catch {
    // ignorar (quota, etc.)
  }
}

/** Lee la última respuesta cacheada de una URL (o undefined si no hay). */
export async function cacheGet(url: string): Promise<unknown | undefined> {
  if (!browser || !('indexedDB' in window)) return undefined;
  try {
    const db = await openDB();
    return await new Promise((res, rej) => {
      const r = db.transaction(STORE, 'readonly').objectStore(STORE).get(url);
      r.onsuccess = () => res((r.result as { data?: unknown } | undefined)?.data);
      r.onerror = () => rej(r.error);
    });
  } catch {
    return undefined;
  }
}
