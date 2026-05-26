import { browser } from '$app/environment';
import { Capacitor } from '@capacitor/core';
import { Directory, Filesystem } from '@capacitor/filesystem';
import type { Track } from './api';

// Descargas offline.
//
// - Web (PWA): el blob de audio (+ carátula) de cada pista vive en IndexedDB y
//   el player reproduce desde el objectURL del blob. Esquiva los Range del SW.
// - App nativa (Capacitor/Android): descargamos a FICHEROS en disco con
//   @capacitor/filesystem y reproducimos vía convertFileSrc(). Offline REAL:
//   los ficheros quedan en el almacenamiento de la app, no en caché del navegador.
//
// Ambas implementaciones exponen la MISMA interfaz pública, así que el player
// (offline.audioUrl(id) ?? stream_url) es idéntico en los dos mundos.

const DB_NAME = 'bbeat-offline';
const STORE = 'tracks';
const VERSION = 1;
const NATIVE = browser && Capacitor.isNativePlatform();

/** Carpeta y clave del índice de descargas en la app nativa. */
const NATIVE_DIR = 'offline';
const NATIVE_INDEX_KEY = 'bbeat:offline:index';

type Rec = { id: number; track: Track; audio: Blob; cover: Blob | null; savedAt: number };

// ─── Web: IndexedDB ──────────────────────────────────────────────
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

// ─── Nativo: índice en localStorage (los ficheros, en disco) ─────
type NativeEntry = { track: Track; audioPath: string; coverPath: string | null };

function readNativeIndex(): Record<number, NativeEntry> {
  try {
    return JSON.parse(localStorage.getItem(NATIVE_INDEX_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function writeNativeIndex(idx: Record<number, NativeEntry>) {
  try {
    localStorage.setItem(NATIVE_INDEX_KEY, JSON.stringify(idx));
  } catch {
    // ignorar
  }
}

/** Extensión de fichero razonable para el audio (define el content-type al servirlo). */
function audioExt(t: Track): string {
  const f = (t.file_format || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  if (['ogg', 'mp3', 'm4a', 'opus', 'flac', 'aac', 'wav', 'webm'].includes(f)) return f;
  return 'mp3';
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
    if (!browser) return;
    try {
      if (NATIVE) await this.initNative();
      else await this.initWeb();
    } catch (e) {
      console.warn('[bbeat] offline init falló:', e);
    } finally {
      this.ready = true;
    }
  }

  private async initWeb() {
    if (!('indexedDB' in window)) return;
    // Marca el almacenamiento como persistente para que el navegador no
    // desaloje la caché del shell ni las descargas por falta de espacio.
    navigator.storage?.persist?.().catch(() => {});
    const db = await openDB();
    const recs = await tx<Rec[]>(db, 'readonly', (s) => s.getAll());
    for (const r of recs) {
      this.audioUrls.set(r.id, URL.createObjectURL(r.audio));
      if (r.cover) this.coverUrls.set(r.id, URL.createObjectURL(r.cover));
      this.metas.set(r.id, r.track);
    }
    this.ids = new Set(recs.map((r) => r.id));
  }

  private async initNative() {
    const idx = readNativeIndex();
    for (const [idStr, entry] of Object.entries(idx)) {
      const id = Number(idStr);
      this.metas.set(id, entry.track);
      this.audioUrls.set(id, await this.nativeSrc(entry.audioPath));
      if (entry.coverPath) this.coverUrls.set(id, await this.nativeSrc(entry.coverPath));
    }
    this.ids = new Set(Object.keys(idx).map(Number));
  }

  /** URI local reproducible (http://localhost/_capacitor_file_/...) de un path en Directory.Data. */
  private async nativeSrc(path: string): Promise<string> {
    const { uri } = await Filesystem.getUri({ directory: Directory.Data, path });
    return Capacitor.convertFileSrc(uri);
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

  /** Pistas descargadas, con cover_url apuntando al fichero/blob local (para verlas offline). */
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
      if (NATIVE) await this.downloadNative(t);
      else await this.downloadWeb(t);
      this.ids = new Set(this.ids).add(t.id);
    } catch (e) {
      console.warn('[bbeat] descarga falló:', e);
    } finally {
      const d = new Set(this.downloading);
      d.delete(t.id);
      this.downloading = d;
    }
  }

  private async downloadWeb(t: Track) {
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
    navigator.storage?.persist?.().catch(() => {});
  }

  private async downloadNative(t: Track) {
    const audioPath = `${NATIVE_DIR}/audio-${t.id}.${audioExt(t)}`;
    // stream_url ya viene absoluto y con ?token=... (tokenizeUrls), así que el
    // descargador no necesita cabecera Authorization.
    await Filesystem.downloadFile({
      url: t.stream_url,
      path: audioPath,
      directory: Directory.Data,
      recursive: true
    });

    let coverPath: string | null = null;
    if (t.cover_url) {
      coverPath = `${NATIVE_DIR}/cover-${t.id}.jpg`;
      try {
        await Filesystem.downloadFile({
          url: t.cover_url,
          path: coverPath,
          directory: Directory.Data,
          recursive: true
        });
      } catch {
        coverPath = null;
      }
    }

    const idx = readNativeIndex();
    idx[t.id] = { track: { ...t }, audioPath, coverPath };
    writeNativeIndex(idx);

    this.audioUrls.set(t.id, await this.nativeSrc(audioPath));
    if (coverPath) this.coverUrls.set(t.id, await this.nativeSrc(coverPath));
    this.metas.set(t.id, { ...t });
  }

  async remove(id: number) {
    if (!browser) return;
    try {
      if (NATIVE) await this.removeNative(id);
      else await this.removeWeb(id);
    } catch (e) {
      console.warn('[bbeat] borrar descarga falló:', e);
    }
    const a = this.audioUrls.get(id);
    if (a && !NATIVE) URL.revokeObjectURL(a);
    this.audioUrls.delete(id);
    const c = this.coverUrls.get(id);
    if (c && !NATIVE) URL.revokeObjectURL(c);
    this.coverUrls.delete(id);
    this.metas.delete(id);
    const s = new Set(this.ids);
    s.delete(id);
    this.ids = s;
  }

  private async removeWeb(id: number) {
    const db = await openDB();
    await tx(db, 'readwrite', (s) => s.delete(id));
  }

  private async removeNative(id: number) {
    const idx = readNativeIndex();
    const entry = idx[id];
    if (entry) {
      await Filesystem.deleteFile({ directory: Directory.Data, path: entry.audioPath }).catch(() => {});
      if (entry.coverPath) {
        await Filesystem.deleteFile({ directory: Directory.Data, path: entry.coverPath }).catch(() => {});
      }
      delete idx[id];
      writeNativeIndex(idx);
    }
  }
}

export const offline = new OfflineStore();
