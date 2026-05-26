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
type NativeEntry = { track: Track; audioPath: string; coverPath: string | null; bytes?: number };

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

/** Blob → base64 sin el prefijo `data:...;base64,` (lo que espera Filesystem.writeFile). */
function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onloadend = () => {
      const s = String(r.result);
      const i = s.indexOf(',');
      resolve(i >= 0 ? s.slice(i + 1) : s);
    };
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

/** Descarga una URL como Blob. Lanza si la respuesta no es OK. */
async function fetchBlob(url: string): Promise<Blob> {
  const res = await fetch(url);
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.blob();
}

class OfflineStore {
  /** ids de pistas descargadas (reactivo). */
  ids = $state<Set<number>>(new Set());
  /** ids descargándose ahora mismo (reactivo). */
  downloading = $state<Set<number>>(new Set());
  /** ids cuya última descarga falló (reactivo) — para mostrar reintento. */
  failed = $state<Set<number>>(new Set());
  /** Mensaje del último error de descarga (para diagnóstico/feedback). */
  lastError = $state<string | null>(null);
  /** Bytes totales ocupados por las descargas (reactivo). */
  totalBytes = $state(0);
  ready = $state(false);

  private audioUrls = new Map<number, string>();
  private coverUrls = new Map<number, string>();
  private metas = new Map<number, Track>();
  private byteMap = new Map<number, number>();

  private recountBytes() {
    let s = 0;
    for (const v of this.byteMap.values()) s += v;
    this.totalBytes = s;
  }

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
      this.byteMap.set(r.id, (r.audio?.size ?? 0) + (r.cover?.size ?? 0));
    }
    this.ids = new Set(recs.map((r) => r.id));
    this.recountBytes();
  }

  private async initNative() {
    const idx = readNativeIndex();
    for (const [idStr, entry] of Object.entries(idx)) {
      const id = Number(idStr);
      this.metas.set(id, entry.track);
      this.audioUrls.set(id, await this.nativeSrc(entry.audioPath));
      if (entry.coverPath) this.coverUrls.set(id, await this.nativeSrc(entry.coverPath));
      this.byteMap.set(id, entry.bytes ?? 0);
    }
    this.ids = new Set(Object.keys(idx).map(Number));
    this.recountBytes();
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
    if (this.failed.has(t.id)) {
      const f = new Set(this.failed);
      f.delete(t.id);
      this.failed = f;
    }
    try {
      if (NATIVE) await this.downloadNative(t);
      else await this.downloadWeb(t);
      this.ids = new Set(this.ids).add(t.id);
    } catch (e) {
      console.warn('[bbeat] descarga falló:', e);
      this.lastError = e instanceof Error ? e.message : String(e);
      this.failed = new Set(this.failed).add(t.id);
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
    this.byteMap.set(t.id, audio.size + (cover?.size ?? 0));
    this.recountBytes();
    navigator.storage?.persist?.().catch(() => {});
  }

  private async downloadNative(t: Track) {
    const dir = Directory.Data;
    // Asegura la carpeta (writeFile recursive no siempre crea el padre).
    await Filesystem.mkdir({ directory: dir, path: NATIVE_DIR, recursive: true }).catch(() => {});

    // stream_url/cover_url ya vienen absolutos y con ?token=... (tokenizeUrls).
    // Usamos fetch + writeFile(base64) en vez de Filesystem.downloadFile (deprecado
    // desde 7.1.0 y roto en Cap 8). CORS permite el origen del WebView.
    const audioBlob = await fetchBlob(t.stream_url);
    const audioPath = `${NATIVE_DIR}/audio-${t.id}.${audioExt(t)}`;
    await Filesystem.writeFile({
      directory: dir,
      path: audioPath,
      data: await blobToBase64(audioBlob),
      recursive: true
    });
    let bytes = audioBlob.size;

    let coverPath: string | null = null;
    if (t.cover_url) {
      try {
        const coverBlob = await fetchBlob(t.cover_url);
        coverPath = `${NATIVE_DIR}/cover-${t.id}.jpg`;
        await Filesystem.writeFile({
          directory: dir,
          path: coverPath,
          data: await blobToBase64(coverBlob),
          recursive: true
        });
        bytes += coverBlob.size;
      } catch {
        coverPath = null;
      }
    }

    const idx = readNativeIndex();
    idx[t.id] = { track: { ...t }, audioPath, coverPath, bytes };
    writeNativeIndex(idx);

    this.audioUrls.set(t.id, await this.nativeSrc(audioPath));
    if (coverPath) this.coverUrls.set(t.id, await this.nativeSrc(coverPath));
    this.metas.set(t.id, { ...t });
    this.byteMap.set(t.id, bytes);
    this.recountBytes();
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
    this.byteMap.delete(id);
    this.recountBytes();
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
