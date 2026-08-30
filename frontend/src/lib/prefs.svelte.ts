import { browser } from '$app/environment';
import { api } from './api';

const CACHE_KEY = 'bbeat:prefs';
const FLUSH_MS = 400;

/**
 * Preferencias de UI del usuario (orden de cada lista, de momento).
 *
 * El servidor manda —así el orden viaja entre el navegador y la app— pero
 * mantenemos un espejo en localStorage para pintar la lista ya ordenada en el
 * primer frame, sin esperar al fetch y sin el salto visual.
 */
class PrefsStore {
  private map = $state<Record<string, string>>({});
  loaded = $state(false);

  /** Escrituras pendientes de mandar, agrupadas por clave. */
  private pending = new Map<string, string>();
  private flushTimer: ReturnType<typeof setTimeout> | null = null;

  init() {
    if (!browser) return;
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (raw) this.map = JSON.parse(raw) as Record<string, string>;
    } catch {}
    // El servidor puede tener cambios hechos desde otro dispositivo.
    api
      .prefs()
      .then((r) => {
        // No pisamos lo que el usuario acabe de tocar mientras volaba el GET.
        const fresh = { ...r.items };
        for (const [k, v] of this.pending) fresh[k] = v;
        this.map = fresh;
        this.persistLocal();
      })
      .catch(() => {})
      .finally(() => (this.loaded = true));
  }

  get(key: string, fallback = ''): string {
    return this.map[key] ?? fallback;
  }

  set(key: string, value: string) {
    if (this.map[key] === value) return;
    this.map = { ...this.map, [key]: value };
    this.persistLocal();
    this.pending.set(key, value);
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.flushTimer = setTimeout(() => this.flush(), FLUSH_MS);
  }

  private flush() {
    this.flushTimer = null;
    const batch = [...this.pending];
    this.pending.clear();
    for (const [key, value] of batch) {
      // Si falla, se queda guardado en local: la próxima vez que lo toque se
      // reenvía. No merece la pena molestar al usuario por esto.
      api.setPref(key, value).catch(() => {});
    }
  }

  clear() {
    this.map = {};
    this.pending.clear();
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.flushTimer = null;
    this.loaded = false;
    if (browser) localStorage.removeItem(CACHE_KEY);
  }

  private persistLocal() {
    if (!browser) return;
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(this.map));
    } catch {}
  }
}

export const prefs = new PrefsStore();
