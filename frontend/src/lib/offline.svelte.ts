import { browser } from '$app/environment';
import type { Track } from './api';

// Descargas offline: guardamos el blob de audio (+ carátula) de cada pista en
// IndexedDB. El player reproduce desde el objectURL del blob, así que funciona
// sin conexión sin tener que pelearse con los Range del service worker.

const DB_NAME = 'bbeat-offline';
const STORE = 'tracks';
const VERSION = 1;

type Rec = { id: number; track: Track; audio: Blob; cover: Blob | null; savedAt: number };

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx<T>(db: IDBDatabase, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction(STORE, mode).objectStore(STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

class OfflineStore {
  /** ids de pistas descargadas (reactivo). */
  ids = $state<Set<number>>(new Set());
  /** ids descargándose ahora mismo (reactivo). */
  downloading = $state<Set<number>>(new Set());
  ready = $state(false);

  private audioUrls = new Map<number, string>();
  private coverUrls = new Map<number, string>();
  private metas = new Map<number, Track>();

  async init() {
    if (!browser || !('indexedDB' in window)) return;
    try {
      const db = await openDB();
      const recs = await tx<Rec[]>(db, 'readonly', (s) => s.getAll());
      for (const r of recs) {
        this.audioUrls.set(r.id, URL.createObjectURL(r.audio));
        if (r.cover) this.coverUrls.set(r.id, URL.createObjectURL(r.cover));
        this.metas.set(r.id, r.track);
      }
      this.ids = new Set(recs.map((r) => r.id));
    } catch (e) {
      console.warn('[bbeat] offline init falló:', e);
    } finally {
      this.ready = true;
    }
  }

  has(id: number): boolean {
    return this.ids.has(id);
  }

  audioUrl(id: number): string | null {
    return this.audioUrls.get(id) ?? null;
  }

  coverUrl(id: number): string | null {
    return this.coverUrls.get(id) ?? null;
  }

  /** Pistas descargadas, con cover_url apuntando al blob local (para verlas offline). */
  downloadedTracks(): Track[] {
    return [...this.metas.values()].map((t) => ({
      ...t,
      cover_url: this.coverUrls.get(t.id) ?? t.cover_url
    }));
  }

  async download(t: Track) {
    if (!browser || this.ids.has(t.id) || this.downloading.has(t.id)) return;
    this.downloading = new Set(this.downloading).add(t.id);
    try {
      const res = await fetch(t.stream_url);
      if (!res.ok) throw new Error('stream ' + res.status);
      const audio = await res.blob();
      let cover: Blob | null = null;
      if (t.cover_url) {
        cover = await fetch(t.cover_url).then((r) => (r.ok ? r.blob() : null)).catch(() => null);
      }
      const db = await openDB();
      await tx(db, 'readwrite', (s) =>
        s.put({ id: t.id, track: { ...t }, audio, cover, savedAt: Date.now() } as Rec)
      );
      this.audioUrls.set(t.id, URL.createObjectURL(audio));
      if (cover) this.coverUrls.set(t.id, URL.createObjectURL(cover));
      this.metas.set(t.id, { ...t });
      this.ids = new Set(this.ids).add(t.id);
      navigator.storage?.persist?.().catch(() => {});
    } catch (e) {
      console.warn('[bbeat] descarga falló:', e);
    } finally {
      const d = new Set(this.downloading);
      d.delete(t.id);
      this.downloading = d;
    }
  }

  async remove(id: number) {
    if (!browser) return;
    try {
      const db = await openDB();
      await tx(db, 'readwrite', (s) => s.delete(id));
    } catch (e) {
      console.warn('[bbeat] borrar descarga falló:', e);
    }
    const a = this.audioUrls.get(id);
    if (a) {
      URL.revokeObjectURL(a);
      this.audioUrls.delete(id);
    }
    const c = this.coverUrls.get(id);
    if (c) {
      URL.revokeObjectURL(c);
      this.coverUrls.delete(id);
    }
    this.metas.delete(id);
    const s = new Set(this.ids);
    s.delete(id);
    this.ids = s;
  }
}

export const offline = new OfflineStore();
