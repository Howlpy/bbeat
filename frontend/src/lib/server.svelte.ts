import { browser } from '$app/environment';
import { Capacitor } from '@capacitor/core';

// Selección de servidor bbeat (para la app nativa multi-servidor).
//
// En web la app la sirve un bbeat concreto (mismo origen) → base vacía, sin
// selector. En la app nativa no hay servidor de origen, así que el usuario
// elige a qué bbeat conectarse y puede guardar varios como favoritos.

const NATIVE = browser && Capacitor.isNativePlatform();
const CURRENT_KEY = 'bbeat:server';
const FAVS_KEY = 'bbeat:servers';
// Servidor por defecto horneado en el build (VITE_API_BASE). Semilla inicial.
const DEFAULT_SERVER = ((import.meta.env.VITE_API_BASE as string | undefined) ?? '').replace(/\/+$/, '');

/** Normaliza una URL de servidor: añade https:// si falta el esquema, quita la barra final. */
export function normalizeServer(url: string): string {
  let u = (url || '').trim();
  if (!u) return '';
  if (!/^https?:\/\//i.test(u)) u = 'https://' + u;
  return u.replace(/\/+$/, '');
}

class ServerStore {
  /** URL base del servidor seleccionado (vacío = ninguno todavía). */
  current = $state('');
  /** Servidores guardados como favoritos. */
  favorites = $state<string[]>([]);
  initialized = $state(false);

  /** Base para las llamadas a la API: en web (mismo origen) vacía; en nativo, la elegida. */
  get base(): string {
    return NATIVE ? this.current : '';
  }

  /** En nativo hay que elegir servidor antes de poder entrar. */
  get needsPick(): boolean {
    return NATIVE && !this.current;
  }

  /** ¿Mostramos el selector de servidor? Solo en la app nativa. */
  get pickable(): boolean {
    return NATIVE;
  }

  init() {
    if (!browser || this.initialized) return;
    this.initialized = true;
    try {
      this.favorites = JSON.parse(localStorage.getItem(FAVS_KEY) || '[]');
    } catch {
      this.favorites = [];
    }
    this.current = localStorage.getItem(CURRENT_KEY) || '';
    // Semilla: en nativo, si no hay nada guardado, arranca con el servidor del build.
    if (NATIVE && !this.current && DEFAULT_SERVER) {
      this.current = DEFAULT_SERVER;
      this.persistCurrent();
      if (!this.favorites.includes(DEFAULT_SERVER)) {
        this.favorites = [DEFAULT_SERVER, ...this.favorites];
        this.persistFavs();
      }
    }
  }

  /** Selecciona un servidor (lo normaliza). */
  select(url: string) {
    const u = normalizeServer(url);
    if (!u) return;
    this.current = u;
    this.persistCurrent();
  }

  /** Añade a favoritos y lo selecciona. */
  addFavorite(url: string) {
    const u = normalizeServer(url);
    if (!u) return;
    if (!this.favorites.includes(u)) {
      this.favorites = [...this.favorites, u];
      this.persistFavs();
    }
    this.select(u);
  }

  removeFavorite(url: string) {
    this.favorites = this.favorites.filter((f) => f !== url);
    this.persistFavs();
  }

  private persistCurrent() {
    if (browser) localStorage.setItem(CURRENT_KEY, this.current);
  }
  private persistFavs() {
    if (browser) localStorage.setItem(FAVS_KEY, JSON.stringify(this.favorites));
  }
}

export const server = new ServerStore();
